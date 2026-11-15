"""Analizza e verifica tutti i siti; output compatti, senza GeoTIFF derivati."""
import argparse
from contextlib import ExitStack
import csv
import gc
import json
from pathlib import Path
import subprocess
import sys
import traceback
import numpy as np
import rasterio
from pyproj import Geod, Transformer
from horizon import LUNAR_CRS, RADIUS_M
from script import statistics
from dem_products import resolve_dem_path
from site_coordinates import preflight, describe_site

BASE = Path(__file__).resolve().parent.parent
OUT = BASE/'risultati topografia'
FAR_REFERENCE = BASE/'dati_regionali/LDSM_60S_240MPP_ADJ.tiff'
FAR_DEM = None
FALLBACK_DEMS = []
MAX_DISTANCE = 200000.0
SITE_CATALOG = BASE/'config/site_coordinates.json'
SITE_CATALOG_HASH = None


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def sample_bilinear(source, lons, lats):
    """Campionamento indipendente da scipy, sui quattro centri pixel."""
    converter = Transformer.from_crs(LUNAR_CRS,source.crs,always_xy=True)
    x,y = converter.transform(lons,lats)
    inv = ~source.transform
    col = inv.a*np.asarray(x)+inv.b*np.asarray(y)+inv.c-.5
    row = inv.d*np.asarray(x)+inv.e*np.asarray(y)+inv.f-.5
    result = np.full(row.shape,np.nan)
    ok=(row>=0)&(col>=0)&(row<source.height-1)&(col<source.width-1)
    if not ok.any():return result
    r,c=row[ok],col[ok]
    r0,c0=int(np.floor(r.min())),int(np.floor(c.min()))
    r1,c1=int(np.floor(r.max()))+2,int(np.floor(c.max()))+2
    patch=source.read(1,window=rasterio.windows.Window(c0,r0,c1-c0,r1-r0),masked=True).astype('float64').filled(np.nan)
    patch=patch*source.scales[0]+source.offsets[0]
    ri,ci=np.floor(r).astype(int)-r0,np.floor(c).astype(int)-c0
    wr,wc=r-np.floor(r),c-np.floor(c)
    result[ok]=((1-wr)*(1-wc)*patch[ri,ci]+wr*(1-wc)*patch[ri+1,ci]
        +(1-wr)*wc*patch[ri,ci+1]+wr*wc*patch[ri+1,ci+1])
    return result


def verify(dem, output, expected_site):
    h = json.loads((output/'horizon.json').read_text(encoding='utf-8'))
    s = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    report = {'status': 'PASS', 'files': {}, 'warnings': [], 'checks': []}
    with rasterio.open(dem) as src:
        shape, affine, crs, res = src.shape, src.transform, src.crs, src.res
        z = src.read(1, masked=True).astype('float64').filled(np.nan)*src.scales[0]+src.offsets[0]
    assert list(shape) == s['shape'] and Path(h['metadati']['dem_vicino']).resolve() == dem.resolve()
    position=describe_site(dem,expected_site['lat'],expected_site['lon'])
    np.testing.assert_allclose([h['lat'],h['lon']],[position['lat'],position['lon']],rtol=0,atol=1e-12)
    assert h['metadati'].get('coordinate_origin')=='explicit_site_coordinates'
    assert s.get('site') is not None and s['site']['lat']==position['lat'] and s['site']['lon']==position['lon']
    assert s['site']['pixel_row']==position['pixel_row'] and s['site']['pixel_col']==position['pixel_col']
    assert abs(h['metadati']['quota_sito_m']-position['ground_elevation_m'])<1e-6
    report['site_coordinates']={'position':position,'source':expected_site['source'],'catalog_sha256':SITE_CATALOG_HASH}
    report['statistics_scope']='entire_dem; site-specific metrics are in summary.site'
    horizon = np.asarray(h['orizzonte'])
    assert horizon.shape == (360,) and np.isfinite(horizon).all()
    prefix = dem.name.removesuffix('_surf.tif')
    rr, cc = np.arange(1,shape[0]-1,4)[:,None], np.arange(1,shape[1]-1,4)[None,:]
    gx = (z[rr,cc+1]-z[rr,cc-1])/(2*res[0])
    gy = (z[rr+1,cc]-z[rr-1,cc])/(2*res[1])
    calc = np.degrees(np.arctan(np.hypot(gx,gy)))
    del gx, gy
    for suffix in ('surf','slp','toterr','ldec'):
        path = dem.with_name(prefix+'_'+suffix+'.tif')
        with rasterio.open(path) as src:
            assert src.count == 1 and src.shape == shape and src.transform == affine, str(path)
            assert src.crs.to_dict() == crs.to_dict(), f'CRS non equivalente: {path}'
            a = src.read(1, masked=True).astype('float32').filled(np.nan)*src.scales[0]+src.offsets[0]
            a[~np.isfinite(a)] = np.nan
            valid = a[np.isfinite(a)]
            assert valid.size
            info = {'file': path.name, 'bytes': path.stat().st_size, 'shape': list(shape),
                'statistics': statistics(a), 'missing_pct': 100*(1-valid.size/a.size),
                'crs_labels_identical': src.crs == crs}
            if src.crs != crs:
                report['warnings'].append(f'{suffix}: etichette CRS diverse, parametri numerici e griglia identici.')
            if suffix == 'slp':
                assert np.all((valid >= 0) & (valid <= 90))
                ref = a[rr,cc]
                both = np.isfinite(calc) & np.isfinite(ref)
                delta = np.abs(calc[both]-ref[both])
                report['slope_comparison'] = {'sampling': 'un pixel ogni 4 righe e 4 colonne; gradienti calcolati sui vicini originali',
                    'sample_count': int(delta.size), 'mean_absolute_difference_deg': float(delta.mean()),
                    'max_absolute_difference_deg': float(delta.max())}
                del delta, ref
            if suffix in ('toterr','ldec'):
                assert np.all(valid >= 0)
            if suffix == 'ldec':
                info['zero_count_pct_of_valid'] = 100*int(np.count_nonzero(valid == 0))/valid.size
                info['fractional_values_pct'] = 100*int(np.count_nonzero(np.abs(valid-np.round(valid)) > 1e-5))/valid.size
                if info['fractional_values_pct'] > 0:
                    report['warnings'].append(f"LDEC contiene {info['fractional_values_pct']:.3f}% di valori frazionari: non interpretare come conteggio grezzo intero. Valori originali preservati.")
            report['files'][suffix] = info
            del a, valid
    del calc
    # Bilineare esplicita indipendente da scipy, su otto azimut.
    to_xy = Transformer.from_crs(LUNAR_CRS,crs,always_xy=True)
    inv = ~affine
    def sample(lons,lats):
        x,y = to_xy.transform(lons,lats)
        c = inv.a*np.asarray(x)+inv.b*np.asarray(y)+inv.c-.5
        r = inv.d*np.asarray(x)+inv.e*np.asarray(y)+inv.f-.5
        ans = np.full(r.shape,np.nan)
        ok = (r>=0)&(c>=0)&(r<shape[0]-1)&(c<shape[1]-1)
        ri,ci = np.floor(r[ok]).astype(int),np.floor(c[ok]).astype(int)
        wr,wc = r[ok]-ri,c[ok]-ci
        ans[ok] = (1-wr)*(1-wc)*z[ri,ci]+wr*(1-wc)*z[ri+1,ci]+(1-wr)*wc*z[ri,ci+1]+wr*wc*z[ri+1,ci+1]
        return ans
    meta = h['metadati']
    near_d = np.append(np.arange(meta['passo_vicino_m'],meta['distanza_vicina_m'],meta['passo_vicino_m']),meta['distanza_vicina_m'])
    d = np.concatenate((near_d,np.arange(meta['distanza_vicina_m']+meta['passo_lontano_m'],MAX_DISTANCE,meta['passo_lontano_m']),[MAX_DISTANCE])) if MAX_DISTANCE>meta['distanza_vicina_m'] else near_d
    ground = sample(np.array([h['lon']]),np.array([h['lat']]))[0]
    assert abs(ground-meta['quota_sito_m'])<1e-7
    assert Path(meta['dem_lontano']).resolve()==FAR_DEM.resolve()
    assert meta['distanza_massima_campionata_m']==MAX_DISTANCE
    np.testing.assert_array_less(np.asarray(h['orizzonte_locale'])-1e-8,horizon)
    for direction in meta['copertura_per_azimut']:
        assert sum(direction['campioni_per_fonte'].values())==direction['campioni_validi']
        assert direction['copertura_completa']==(direction['campioni_validi']==direction['campioni_totali'])
    errors=[]
    geod=Geod(a=RADIUS_M,b=RADIUS_M)
    with ExitStack() as stack:
        regional=[stack.enter_context(rasterio.open(path)) for path in [meta['dem_lontano']]+meta['dem_fallback']]
        for az in range(0,360,45):
            lon,lat,_=geod.fwd(np.full(d.size,h['lon']),np.full(d.size,h['lat']),np.full(d.size,az),d)
            heights=np.full(d.size,np.nan)
            local=d<=meta['distanza_vicina_m']
            heights[local]=sample(lon[local],lat[local])
            for source in regional:
                missing=~np.isfinite(heights)
                if missing.any():heights[missing]=sample_bilinear(source,lon[missing],lat[missing])
            angles=np.degrees(np.arctan((heights-ground-meta['altezza_osservatore_m']-d*d/(2*RADIUS_M))/d))
            error=abs(float(np.nanmax(angles))-horizon[az])
            assert error<1e-7,f'Orizzonte regionale incoerente a {az} gradi'
            errors.append(error)
    del z
    report['independent_horizon_max_difference_deg'] = max(errors)
    with (output/'site_cells.csv').open(encoding='utf-8',newline='') as handle:
        count = sum(1 for _ in csv.DictReader(handle))
    dx,dy = s['resolution_m']
    tw,th = s['tile_size_actual_m']
    expected = int(np.ceil(shape[0]/round(th/dy))*np.ceil(shape[1]/round(tw/dx)))
    assert 0<count<=expected
    if s['missing_elevation_pct']==0:
        assert count==expected
    report['cell_count'] = count
    report['checks'] = ['Quattro raster leggibili; griglie e parametri CRS numericamente identici',
        'Pendenze in [0,90], incertezze e LDEC non negativi; eventuali frazioni LDEC segnalate',
        '360 angoli finiti e coordinate coerenti', 'Otto azimut fino al raggio regionale confermati da bilineare indipendente',
        'Conteggio delle celle CSV verificato']
    report['regional_coverage']={'dem':meta['dem_lontano'],'distance_m':MAX_DISTANCE,'complete':meta['copertura_completa_entro_distanza_richiesta'],'sample_counts':meta['campioni_per_fonte']}
    if not meta['copertura_completa_entro_distanza_richiesta']:
        report['warnings'].append('Copertura regionale incompleta: vedere il dettaglio per azimut.')
    if report['warnings']:
        report['status']='PASS_WITH_NOTES'
    save(output/'validation.json',report)
    t = next(v for v in s['slope_filters'] if v['max_slope_deg']==10)
    row = {'sito':dem.parent.name,'lat':h['lat'],'lon':h['lon'],
        'quota_min_m':s['elevation_m']['min'],'quota_max_m':s['elevation_m']['max'],
        'pendenza_media_deg':s['slope_deg']['mean'],'area_proiettata_km2':s['extent_projected_km2'],
        'area_pendenza_le10_km2':t['area_projected_km2'],'pendenza_le10_pct':t['pct_of_valid_slope'],
        'incertezza_verticale_media_m':report['files']['toterr']['statistics']['mean'],
        'pixel_ldec_zero_pct':report['files']['ldec']['zero_count_pct_of_valid'],
        'orizzonte_min_deg':float(horizon.min()),'orizzonte_max_deg':float(horizon.max()),
        'direzioni_copertura_completa_200km':sum(v['copertura_completa'] for v in meta['copertura_per_azimut']),
        'copertura_completa_200km':meta['copertura_completa_entro_distanza_richiesta'],
        'dem_lontano':meta['dem_lontano'],
        'azimut_ostruzione_aumentata':int(np.count_nonzero(horizon-np.asarray(h['orizzonte_locale'])>1e-4)),
        'aumento_massimo_orizzonte_deg':float(np.max(horizon-np.asarray(h['orizzonte_locale']))),
        'dem_center_lat':position['dem_center']['lat'],'dem_center_lon':position['dem_center']['lon'],
        'distanza_sito_centro_dem_m':position['distance_from_dem_center_m'],
        'pixel_row':position['pixel_row'],'pixel_col':position['pixel_col'],
        'quota_sito_m':position['ground_elevation_m'],'pendenza_sito_pixel_deg':s['site']['slope_deg_at_pixel'],
        'fonte_coordinate':expected_site['source'],
        'celle':count,'verifica':report['status']}
    text = [f'# {dem.parent.name}','','Analisi dalle coordinate esplicite del sito; osservatore a 2 m.','',
        '| Metrica | Valore |','| --- | --- |',
        f"| Sito (lat, lon lunari) | {h['lat']:.6f}, {h['lon']:.6f} gradi |",
        f"| Quote min / max | {row['quota_min_m']:.2f} / {row['quota_max_m']:.2f} m |",
        f"| Pendenza media calcolata | {row['pendenza_media_deg']:.2f} gradi |",
        f"| Area con pendenza <=10 gradi | {row['area_pendenza_le10_km2']:.2f} km2 ({row['pendenza_le10_pct']:.2f}%) |",
        f"| Incertezza verticale media fornita | {row['incertezza_verticale_media_m']:.3f} m |",
        f"| Pixel con LDEC zero | {row['pixel_ldec_zero_pct']:.2f}% |",
        f"| Orizzonte minimo / massimo | {row['orizzonte_min_deg']:.3f} / {row['orizzonte_max_deg']:.3f} gradi |",
        f"| Celle | {count} |",f"| Verifica | {report['status']} |",'',
        '## Risultati','','- [Orizzonte regionale a 360 valori](horizon.json)','- [Orizzonte solo locale](horizon_local.json)','- [Mappa e profilo](horizon.png)',
        '- [Statistiche complete](summary.json)','- [Celle topografiche](site_cells.csv)',
        '- [Rapporto di verifica e qualita](validation.json)','',
        '## Interpretazione e limiti','',
        'Le statistiche generali descrivono tutto il DEM; il profilo orizzonte riguarda le coordinate esplicite del sito. summary.site contiene le metriche del punto.',
        f"Fonte coordinate: {expected_site['source']}. Distanza dal centro del DEM: {position['distance_from_dem_center_m']:.3f} m. Pixel: riga {position['pixel_row']}, colonna {position['pixel_col']}.",
        'Le percentuali sono riferite ai pixel con pendenza calcolabile; le aree sono proiettate.',
        'Le celle sono 100 x 100 m, piu piccole ai bordi quando necessario.',
        'LDEC zero non e NoData: il DEM contiene anche terreno interpolato.',
        'Il filtro di pendenza non certifica un sito sicuro e non impone aree connesse.',
        'Non sono stati calcolati luce, visibilita terrestre, temperatura o presenza di ghiaccio.',
        'Output compatti: nessun GeoTIFF derivato, per contenere lo spazio su disco.',
        f"Terreno lontano incluso fino a {MAX_DISTANCE/1000:.0f} km: {row['direzioni_copertura_completa_200km']}/360 direzioni con tutti i campioni disponibili.",
        f"Ostruzione aumentata in {row['azimut_ostruzione_aumentata']} direzioni; aumento massimo {row['aumento_massimo_orizzonte_deg']:.4f} gradi.",
        'Il LDSM identifica il prodotto LDEM: le quote regionali provengono dal LDEM 60S a 240 m/pixel.',
        'Il passo di campionamento regionale di 100 m non aumenta la risoluzione del DEM.',
        'La copertura completa riguarda i campioni; rimangono i limiti del dettaglio e del raggio scelto.',
        *['- '+w for w in meta['avvertenze']+report['warnings']], '']
    (output/'README.md').write_text('\n'.join(text),encoding='utf-8')
    for log in ('error.log',):
        if (output/log).exists():
            (output/log).unlink()
    gc.collect()
    return row


def index(rows,failures):
    save(OUT/'riepilogo.json',{'parametri':{'punto':'coordinate esplicite del sito dal catalogo','catalogo_coordinate':str(SITE_CATALOG),'catalogo_coordinate_sha256':SITE_CATALOG_HASH,'altezza_osservatore_m':2,
        'passo_orizzonte_m':5,'raggio_vicino_m':10000,'soglia_pendenza_deg':10,'lato_cella_m':100,
        'riferimento_ldsm':str(FAR_REFERENCE),'dem_lontano':str(FAR_DEM),'dem_fallback':[str(p) for p in FALLBACK_DEMS],'raggio_lontano_m':MAX_DISTANCE,'passo_lontano_m':100,'formato':'compatto: JSON, CSV, PNG'},'siti':rows,'errori':failures})
    if rows:
        try:
            csv_file = (OUT/'riepilogo.csv').open('w',newline='',encoding='utf-8')
        except PermissionError:
            csv_file = (OUT/'riepilogo_aggiornato.csv').open('w',newline='',encoding='utf-8')
        with csv_file as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['# Risultati topografia','',f'Siti analizzati e verificati: {len(rows)}. Errori: {len(failures)}.','',
        'Parametri comuni: coordinate esplicite dal catalogo, osservatore 2 m, 360 azimut geografici, passo 5 m fino a 10 km e 100 m fino a 200 km,',
        'celle 100 x 100 m e soglia di pendenza 10 gradi.','',
        '| Sito | Pendenza media (gradi) | Area <=10 gradi (%) | Incertezza media (m) | Esito |',
        '| --- | --- | --- | --- | --- |']
    if rows:
        lines[2:2] = [f'CSV corrente: [{Path(csv_file.name).name}]({Path(csv_file.name).name})', 'Se sono presenti due CSV, usare questo collegamento: l\'altro puo essere una versione precedente rimasta aperta.', '']
    for r in rows:
        lines.append(f"| [{r['sito']}]({r['sito']}/README.md) | {r['pendenza_media_deg']:.2f} | {r['pendenza_le10_pct']:.2f} | {r['incertezza_verticale_media_m']:.3f} | {r['verifica']} |")
    lines+=['','## File e limiti','',
        '`riepilogo.json` e il CSV corrente consentono il confronto; `confronto.png` mostra pendenza e frazione <=10 gradi. `confronto_orizzonti.png` mostra il contributo del terreno lontano.',
        'Se riepilogo.csv e aperto da un programma, il CSV corrente viene salvato come riepilogo_aggiornato.csv.',
        'Ogni sito ha JSON dell\'orizzonte, statistiche, celle CSV, mappa PNG e rapporto di verifica.',
        'Le percentuali sono riferite ai pixel con pendenza calcolabile; le aree sono proiettate.',
        'I raster hanno estensioni diverse: le sole aree assolute non sono un confronto omogeneo.',
        'I profili orizzonte riguardano le coordinate esplicite dei siti; le statistiche DEM restano riferite all\'intera superficie. Le metriche del punto sono separate in summary.site.',
        '**DEM lontano incluso:** il file LDSM 60S identifica il corrispondente LDEM 60S a 240 m/pixel. Le quote vengono dal LDEM.',
        'La copertura dei campioni fino a 200 km e riportata per sito; non elimina i limiti della risoluzione o del campionamento. Il passo di 100 m non migliora la risoluzione regionale di 240 m.',
        'La precisione non coincide con la risoluzione di 5 m; LDEC zero indica assenza di misure dirette, non necessariamente quota mancante.',
        'Non sono stati calcolati luce, comunicazioni, temperatura, ghiaccio o uno score complessivo di atterraggio.',
        'I GeoTIFF derivati sono omessi: il disco si e riempito durante la prima elaborazione. I dati originali sono preservati.',
        'Site23 presenta un CRS nominalmente diverso nel file di errore, ma con parametri numerici e griglia identici.',
        'Haworth presenta valori LDEC frazionari: nota nel rapporto; non sono interpretati come conteggi grezzi interi.','',
        '## Ripetere','', 'Dalla radice del repository:','', '```powershell',
        '.venv/Scripts/python.exe scripts/analyze_all.py','```','',
        'Gli output con gli stessi nomi vengono sovrascritti; i dati originali non sono modificati.',
        'Gli script e i test sono in `scripts/`. I controlli verificano anche la corrispondenza LDSM/LDEM e il campionamento regionale.','']
    if failures:
        lines+=['## Errori','',*[f"- {f['sito']}: {f['error']}" for f in failures]]
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    global FAR_REFERENCE,FAR_DEM,FALLBACK_DEMS,MAX_DISTANCE,SITE_CATALOG,SITE_CATALOG_HASH
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--far-dem',type=Path,default=FAR_REFERENCE)
    parser.add_argument('--fallback-dem',type=Path,action='append',default=[])
    parser.add_argument('--max-distance',type=float,default=200000)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--sites-file',type=Path,default=SITE_CATALOG)
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    SITE_CATALOG=args.sites_file.resolve()
    try:
        coordinate_check=preflight(BASE/'dati_siti_topografia',SITE_CATALOG,BASE/'controllo_coordinate')
    except (ValueError,OSError) as exc:parser.error(str(exc))
    if args.preflight_only:
        print(f"Coordinate verificate: {coordinate_check['ready_count']}/{coordinate_check['site_count']}; report in controllo_coordinate")
        return not coordinate_check['ready']
    if not coordinate_check['ready']:
        parser.error(f"Coordinate reali mancanti o non valide: {coordinate_check['ready_count']}/{coordinate_check['site_count']} siti pronti. Compilare {SITE_CATALOG}; nessun risultato sovrascritto.")
    SITE_CATALOG_HASH=coordinate_check['catalog_sha256']
    expected_sites={row['site_id'].casefold():row for row in coordinate_check['sites']}
    try:
        FAR_REFERENCE=args.far_dem.resolve()
        FAR_DEM=resolve_dem_path(FAR_REFERENCE).resolve()
        FALLBACK_DEMS=[resolve_dem_path(p).resolve() for p in args.fallback_dem]
        MAX_DISTANCE=args.max_distance
        if not np.isfinite(MAX_DISTANCE) or MAX_DISTANCE<10000:raise ValueError('Raggio massimo almeno 10000 m, finito.')
        for path in [FAR_DEM]+FALLBACK_DEMS:
            if not path.is_file():raise ValueError(f'DEM assente: {path}')
    except ValueError as exc:parser.error(str(exc))
    print(f'Riferimento: {FAR_REFERENCE.name} -> DEM: {FAR_DEM}',flush=True)
    OUT.mkdir(exist_ok=True)
    folders=sorted((p for p in (BASE/'dati_siti_topografia').iterdir() if p.is_dir()),key=lambda p:p.name.casefold())
    rows,failures=[],[]
    for i,folder in enumerate(folders,1):
        print(f'[{i}/{len(folders)}] {folder.name}',flush=True)
        output=OUT/folder.name;output.mkdir(exist_ok=True)
        try:
            matches=[p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.tif','.tiff') and p.stem.lower().endswith('_surf')]
            if len(matches)!=1:raise ValueError('Serve esattamente un DEM surf')
            dem=matches[0].resolve()
            expected_site=expected_sites[folder.name.casefold()]
            reuse=False
            if args.resume and all((output/f).is_file() for f in ('summary.json','horizon.json','site_cells.csv','horizon.png')):
                try:
                    existing=json.loads((output/'horizon.json').read_text(encoding='utf-8'))
                    metadata=existing['metadati']
                    reuse=(metadata.get('dem_lontano')==str(FAR_DEM) and metadata.get('distanza_massima_campionata_m')==MAX_DISTANCE and metadata.get('dem_fallback')==[str(p) for p in FALLBACK_DEMS] and metadata.get('coordinate_origin')=='explicit_site_coordinates' and metadata.get('coordinate_catalog_sha256')==SITE_CATALOG_HASH and abs(existing['lat']-expected_site['lat'])<1e-12 and abs(existing['lon']-expected_site['lon'])<1e-12)
                except (ValueError,KeyError,OSError):pass
            if not reuse:
                command=[sys.executable,str(Path(__file__).with_name('script.py')),'--input',str(dem),
                    '--output',str(output),'--name',folder.name,'--mode','all','--no-rasters',
                    '--far-dem',str(FAR_REFERENCE),'--max-distance',str(MAX_DISTANCE),'--lat',str(expected_site['lat']),'--lon',str(expected_site['lon']),'--coordinate-source',expected_site['source']]
                for path in FALLBACK_DEMS:command+=['--fallback-dem',str(path)]
                result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
                (output/'run.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
                if result.returncode:raise RuntimeError('Analisi fallita: vedere run.log')
            profile=json.loads((output/'horizon.json').read_text(encoding='utf-8'))
            profile['metadati']['coordinate_catalog_sha256']=SITE_CATALOG_HASH
            save(output/'horizon.json',profile)
            save(output/'horizon_local.json',{'nome':profile['nome'],'lat':profile['lat'],'lon':profile['lon'],
                'orizzonte':profile['orizzonte_locale'],'metadati':{'dem_vicino':str(dem),'dem_lontano':None,
                    'raggio_locale_m':profile['metadati']['distanza_vicina_m'],'altezza_osservatore_m':2,'coordinate_origin':'explicit_site_coordinates','coordinate_source':expected_site['source'],
                    'nota':'Massimo sui soli campioni validi del DEM locale; confronto con horizon.json.'}})
            row=verify(dem,output,expected_site);rows.append(row)
            print(f"  {row['verifica']}: copertura {row['direzioni_copertura_completa_200km']}/360; ostruzione aumentata in {row['azimut_ostruzione_aumentata']} direzioni",flush=True)
        except Exception as exc:
            failures.append({'sito':folder.name,'error':str(exc)})
            (output/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
            print(f'  ERRORE: {exc}',flush=True)
        index(rows,failures)
    if rows:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(12,max(5,len(rows)*.4)))
        names=[r['sito'] for r in rows]
        axes[0].barh(names,[r['pendenza_media_deg'] for r in rows],color='#455e83')
        axes[0].set(title='Pendenza media del DEM',xlabel='Gradi')
        axes[1].barh(names,[r['pendenza_le10_pct'] for r in rows],color='#378575')
        axes[1].set(title='Area con pendenza <=10 gradi',xlabel='% dei pixel con pendenza calcolabile',xlim=(0,100))
        for ax in axes:ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        fig.tight_layout();fig.savefig(OUT/'confronto.png',dpi=150);plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(13,max(6,len(rows)*.3)))
        axes[0].barh(names,[r['aumento_massimo_orizzonte_deg'] for r in rows],color='#ad6b3c')
        axes[0].set(title='Aumento massimo dell’orizzonte',xlabel='Gradi rispetto al solo DEM vicino')
        axes[1].barh(names,[r['azimut_ostruzione_aumentata'] for r in rows],color='#556c94')
        axes[1].set(title='Direzioni con ostruzione aumentata',xlabel='Azimut su 360 (incremento >0.0001 gradi)',xlim=(0,360))
        for ax in axes:ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        fig.tight_layout();fig.savefig(OUT/'confronto_orizzonti.png',dpi=150);plt.close(fig)
    print(f'Completati {len(rows)}/{len(folders)}; errori {len(failures)}.',flush=True)
    return bool(failures)

if __name__=='__main__':
    sys.exit(main())


