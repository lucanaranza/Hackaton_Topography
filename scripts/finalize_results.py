"""Controllo finale degli output regionali e grafico di confronto."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import analyze_all as batch


def main():
    root=batch.OUT
    report=json.loads((root/'riepilogo.json').read_text(encoding='utf-8'))
    rows=report['siti']
    if not report['parametri'].get('catalogo_coordinate_sha256'):
        raise ValueError('I risultati precedenti usano i centri DEM: mancano coordinate sito verificate. Non vengono finalizzati nuovamente.')
    expected={p.name for p in (batch.BASE/'dati_siti_topografia').iterdir() if p.is_dir()}
    assert not report['errori']
    assert expected=={r['sito'] for r in rows}
    cells=0
    max_error=0
    notes=[]
    def normalize(value):
        if isinstance(value,dict):return {('lontano' if k=='mosaico87S' else k):normalize(v) for k,v in value.items()}
        if isinstance(value,list):return [normalize(v) for v in value]
        return 'lontano' if value=='mosaico87S' else value
    for row in rows:
        folder=root/row['sito']
        for name in ('horizon.json','summary.json','site_cells.csv','horizon.png','horizon_local.json','validation.json','README.md','run.log'):
            assert (folder/name).is_file() and (folder/name).stat().st_size>0, str(folder/name)
        for name in ('horizon.json','validation.json'):
            p=folder/name
            value=json.loads(p.read_text(encoding='utf-8'))
            normalized=normalize(value)
            if normalized!=value:batch.save(p,normalized)
        h=json.loads((folder/'horizon.json').read_text(encoding='utf-8'))
        v=json.loads((folder/'validation.json').read_text(encoding='utf-8'))
        assert v['status'].startswith('PASS')
        assert h['metadati'].get('coordinate_origin')=='explicit_site_coordinates'
        assert h['metadati'].get('coordinate_catalog_sha256')==report['parametri']['catalogo_coordinate_sha256']
        position=v['site_coordinates']['position']
        np.testing.assert_allclose([h['lat'],h['lon']],[position['lat'],position['lon']],rtol=0,atol=1e-12)
        assert len(h['orizzonte'])==360 and np.isfinite(h['orizzonte']).all()
        assert np.all(np.asarray(h['orizzonte'])>=np.asarray(h['orizzonte_locale'])-1e-8)
        assert h['metadati']['copertura_completa_entro_distanza_richiesta']
        assert h['metadati']['distanza_massima_campionata_m']==200000
        assert Path(h['metadati']['dem_lontano']).name=='LDEM_60S_240MPP_ADJ.TIF'
        assert not any(Path(source['file']).name.upper().startswith('LDSM_') for source in h['metadati']['fonti'])
        assert any('LDSM_60S' in p['richiesto'] for p in h['metadati']['prodotti_risolti'])
        assert not (folder/'error.log').exists()
        cells+=v['cell_count']
        max_error=max(max_error,v['independent_horizon_max_difference_deg'])
        notes.extend({'sito':row['sito'],'nota':n} for n in v['warnings'])
    batch.SITE_CATALOG=Path(report['parametri']['catalogo_coordinate'])
    batch.SITE_CATALOG_HASH=report['parametri']['catalogo_coordinate_sha256']
    batch.FAR_REFERENCE=Path(report['parametri']['riferimento_ldsm'])
    batch.FAR_DEM=Path(report['parametri']['dem_lontano'])
    batch.FALLBACK_DEMS=[Path(p) for p in report['parametri']['dem_fallback']]
    batch.MAX_DISTANCE=report['parametri']['raggio_lontano_m']
    batch.index(rows,[])
    for csv_path in root.glob('riepilogo*.csv'):
        try:
            with csv_path.open('w',encoding='utf-8',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        except PermissionError:
            print(f'CSV aperto da altro programma, preservato: {csv_path.name}')
    names=[r['sito'] for r in rows]
    fig,axes=plt.subplots(1,2,figsize=(13,max(6,len(rows)*.3)))
    axes[0].barh(names,[r['aumento_massimo_orizzonte_deg'] for r in rows],color='#ad6b3c')
    axes[0].set(title='Aumento massimo dell’orizzonte',xlabel='Gradi rispetto al solo DEM vicino')
    axes[1].barh(names,[r['azimut_ostruzione_aumentata'] for r in rows],color='#556c94')
    axes[1].set(title='Direzioni con ostruzione aumentata',xlabel='Azimut su 360 (incremento >0.0001 gradi)',xlim=(0,360))
    for ax in axes:ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
    fig.tight_layout();fig.savefig(root/'confronto_orizzonti.png',dpi=150);plt.close(fig)
    final={'status':'PASS','siti':len(rows),'celle':cells,'direzioni_orizzonte':360*len(rows),
        'copertura_campioni_200km_completa_per_tutti':True,
        'max_errore_verifica_indipendente_gradi':max_error,
        'siti_con_note':sorted({n['sito'] for n in notes}),'note':notes,
        'dem_lontano':report['parametri']['dem_lontano'],
        'riferimento_ldsm':report['parametri']['riferimento_ldsm']}
    batch.save(root/'verifica_finale.json',final)
    print(json.dumps(final,indent=2,ensure_ascii=False))
    print('CSV disponibili:',[(p.name,sum(1 for _ in csv.DictReader(p.open(encoding='utf-8')))) for p in root.glob('riepilogo*.csv')])

if __name__=='__main__':
    main()

