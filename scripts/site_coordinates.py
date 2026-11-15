"""Coordinate esplicite dei siti e verifica della loro posizione nel DEM."""
import argparse
import csv
import hashlib
import json
import math
from numbers import Real
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from rasterio.windows import Window

RADIUS_M = 1737400.0
FRAME = 'MOON_ME_DE421'
LUNAR_CRS = CRS.from_proj4('+proj=longlat +R=1737400 +no_defs')


def checked_coordinates(lat, lon):
    if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, Real) or not isinstance(lon, Real):
        raise ValueError('Servono lat e lon numeriche esplicite del sito, in gradi.')
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 < lat < 90 and -180 <= lon <= 360):
        raise ValueError('Coordinate non valide: lat in (-90,90), lon est positiva in [-180,360].')
    return float(lat), float((lon+180)%360-180)


def dem_geometry(dem):
    with rasterio.open(dem) as src:
        if src.count != 1 or src.crs is None or not src.crs.is_projected:
            raise ValueError('Serve un DEM monobanda con CRS lunare proiettato.')
        crs = CRS.from_wkt(src.crs.to_wkt())
        if not (np.isclose(crs.ellipsoid.semi_major_metre,RADIUS_M) and np.isclose(crs.ellipsoid.semi_minor_metre,RADIUS_M)):
            raise ValueError('Il CRS non usa la sfera lunare attesa.')
        if src.crs.linear_units != 'metre':
            raise ValueError('Il DEM deve avere coordinate proiettate in metri.')
        x,y=src.transform*(src.width/2,src.height/2)
        lon,lat=Transformer.from_crs(src.crs,LUNAR_CRS,always_xy=True).transform(x,y)
        return {'dem':str(Path(dem).resolve()),'dem_center_lat':lat,'dem_center_lon':lon,
            'dem_center_x_m':x,'dem_center_y_m':y,'height':src.height,'width':src.width,
            'bounds_m':dict(zip(('left','bottom','right','top'),src.bounds)),
            'crs_wkt':src.crs.to_wkt()}


def describe_site(dem, lat, lon):
    original_lon=lon
    lat,lon=checked_coordinates(lat,lon)
    geometry=dem_geometry(dem)
    with rasterio.open(dem) as src:
        to_xy=Transformer.from_crs(LUNAR_CRS,src.crs,always_xy=True)
        x,y=to_xy.transform(lon,lat)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError('Trasformazione geografica non valida.')
        row,col=src.index(x,y)
        if not (0<=row<src.height and 0<=col<src.width):
            raise ValueError(f'Sito fuori dal DEM: lat={lat}, lon={lon}, pixel=({row},{col}), shape={src.shape}.')
        inv=~src.transform
        c=inv.a*x+inv.b*y+inv.c-.5
        r=inv.d*x+inv.e*y+inv.f-.5
        if not (0<=r<=src.height-1 and 0<=c<=src.width-1) or min(src.shape)<2:
            raise ValueError('Sito troppo vicino al bordo per interpolare la quota: serve copertura DEM aggiuntiva.')
        ri,ci=min(math.floor(r),src.height-2),min(math.floor(c),src.width-2)
        wr,wc=r-ri,c-ci
        patch=src.read(1,window=Window(ci,ri,2,2),masked=True).astype('float64').filled(np.nan)
        patch=patch*src.scales[0]+src.offsets[0]
        if not np.isfinite(patch).all():
            raise ValueError('Quota del sito non disponibile: NoData nei vicini necessari.')
        ground=float((1-wr)*(1-wc)*patch[0,0]+wr*(1-wc)*patch[1,0]+(1-wr)*wc*patch[0,1]+wr*wc*patch[1,1])
        pixel_x,pixel_y=src.xy(row,col)
    _,_,distance=Geod(a=RADIUS_M,b=RADIUS_M).inv(geometry['dem_center_lon'],geometry['dem_center_lat'],lon,lat)
    return {'lat':lat,'lon':lon,'longitude_input_deg':float(original_lon),'frame':FRAME,
        'coordinate_origin':'explicit_site_coordinates','x_m':x,'y_m':y,
        'pixel_row':int(row),'pixel_col':int(col),'pixel_center_x_m':pixel_x,'pixel_center_y_m':pixel_y,
        'ground_elevation_m':ground,'inside_dem':True,'distance_from_dem_center_m':float(distance),
        'dem_center':{'lat':geometry['dem_center_lat'],'lon':geometry['dem_center_lon'],
                      'x_m':geometry['dem_center_x_m'],'y_m':geometry['dem_center_y_m']},
        'dem':geometry['dem']}


def load_catalog(path):
    path=Path(path)
    catalog=json.loads(path.read_text(encoding='utf-8-sig'))
    if catalog.get('frame') != FRAME or catalog.get('units') != 'degree' or catalog.get('longitude_positive') != 'east':
        raise ValueError('Il catalogo deve dichiarare frame MOON_ME_DE421, units degree, longitude_positive east.')
    if not isinstance(catalog.get('sites'),list):
        raise ValueError('Manca la lista sites nel catalogo.')
    entries={}
    for entry in catalog['sites']:
        if not isinstance(entry,dict) or not isinstance(entry.get('site_id'),str) or not entry['site_id'].strip():
            raise ValueError('Ogni sito deve dichiarare site_id.')
        key=entry['site_id'].strip().casefold()
        if key in entries:raise ValueError(f'ID sito duplicato: {entry["site_id"]}')
        entries[key]=entry
    return entries, hashlib.sha256(path.read_bytes()).hexdigest()


def find_dem(folder):
    matches=[p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in ('.tif','.tiff') and p.stem.lower().endswith('_surf')]
    if len(matches)!=1:raise ValueError(f'Serve un solo DEM surf in {folder}; trovati {len(matches)}.')
    return matches[0].resolve()


def create_template(data_root, catalog_path):
    path=Path(catalog_path)
    if path.exists():return
    folders=sorted((p for p in Path(data_root).iterdir() if p.is_dir()),key=lambda p:p.name.casefold())
    catalog={'frame':FRAME,'units':'degree','longitude_positive':'east',
        'note':'Inserire le coordinate effettive confermate dal gruppo. Nessuna coordinata e ricavata dal centro del DEM.',
        'sites':[{'site_id':p.name,'lat':None,'lon':None,'source':None} for p in folders]}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(catalog,indent=2,ensure_ascii=False),encoding='utf-8')


def preflight(data_root, catalog_path, output_dir):
    entries,digest=load_catalog(catalog_path)
    folders=sorted((p for p in Path(data_root).iterdir() if p.is_dir()),key=lambda p:p.name.casefold())
    rows=[]
    for folder in folders:
        row={'site_id':folder.name,'lat':None,'lon':None,'source':None,
             'dem_center_lat':None,'dem_center_lon':None,'distance_from_dem_center_m':None,
             'pixel_row':None,'pixel_col':None,'status':'MISSING_COORDINATES','message':''}
        try:
            dem=find_dem(folder)
            geometry=dem_geometry(dem)
            row.update(dem=str(dem),dem_center_lat=geometry['dem_center_lat'],dem_center_lon=geometry['dem_center_lon'])
            entry=entries.get(folder.name.casefold())
            if entry is None:raise ValueError('ID sito assente dal catalogo: nessuna coordinata inventata.')
            row.update(lat=entry.get('lat'),lon=entry.get('lon'),source=entry.get('source'))
            checked_coordinates(row['lat'],row['lon'])
            if not isinstance(row['source'],str) or not row['source'].strip():
                raise ValueError('Manca la fonte delle coordinate del sito.')
            position=describe_site(dem,row['lat'],row['lon'])
            row.update(lat=position['lat'],lon=position['lon'],pixel_row=position['pixel_row'],
                pixel_col=position['pixel_col'],distance_from_dem_center_m=position['distance_from_dem_center_m'],
                status='READY',position=position,message='Coordinate esplicite, sito nel DEM e quota valida.')
        except (ValueError,OSError,rasterio.errors.RasterioError) as exc:
            row['message']=str(exc)
            if row['lat'] is not None and row['lon'] is not None:row['status']='INVALID_COORDINATES_OR_DEM'
        rows.append(row)
    ready=bool(rows) and all(r['status']=='READY' for r in rows)
    result={'ready':ready,'frame':FRAME,'catalog':str(Path(catalog_path).resolve()),'catalog_sha256':digest,
        'site_count':len(rows),'ready_count':sum(r['status']=='READY' for r in rows),'sites':rows}
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    (output/'coordinate_preflight.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    columns=['site_id','lat','lon','source','dem_center_lat','dem_center_lon','distance_from_dem_center_m','pixel_row','pixel_col','status','message']
    with (output/'coordinate_preflight.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    text=['# Controllo coordinate prima del calcolo','',
        'Le coordinate dei siti sono separate dai centri dei DEM. Nessun centro viene usato automaticamente.',
        f'Siti pronti: {result["ready_count"]}/{len(rows)}. Calcolo autorizzabile dai dati: {ready}.','',
        '| Sito | Lat sito | Lon sito | Lat centro DEM | Lon centro DEM | Distanza (m) | Stato |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        def fmt(value):return '-' if value is None else f'{value:.6f}'
        text.append(f'| {r["site_id"]} | {fmt(r["lat"])} | {fmt(r["lon"])} | {fmt(r["dem_center_lat"])} | {fmt(r["dem_center_lon"])} | {fmt(r["distance_from_dem_center_m"])} | {r["status"]} |')
    text+=['','Compilare config/site_coordinates.json con i punti reali e la fonte del gruppo effemeridi.',
        'I valori mancanti restano vuoti. Le coordinate approssimate dei crateri e i centri delle regioni non sono sostituti automatici dei punti scelti.',
        'Il JSON contiene anche X/Y lunari e riga/colonna del pixel, quando le coordinate sono disponibili.','']
    (output/'README.md').write_text('\n'.join(text),encoding='utf-8')
    return result


def main():
    base=Path(__file__).resolve().parent.parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,default=base/'config/site_coordinates.json')
    parser.add_argument('--create-template',action='store_true')
    args=parser.parse_args()
    if args.create_template:create_template(base/'dati_siti_topografia',args.catalog)
    result=preflight(base/'dati_siti_topografia',args.catalog,base/'controllo_coordinate')
    print(f'Coordinate verificate: {result["ready_count"]}/{result["site_count"]}; report: {base / "controllo_coordinate"}')
    return 0 if result['ready'] else 2

if __name__=='__main__':
    raise SystemExit(main())
