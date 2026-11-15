"""Orizzonte geografico lunare: contratto JSON per il motore effemeridi."""
from contextlib import ExitStack
from collections import OrderedDict
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Geod, Transformer
from rasterio.windows import Window
from scipy.ndimage import map_coordinates
from dem_products import resolve_dem_path
from site_coordinates import describe_site

RADIUS_M = 1_737_400.0
LUNAR_CRS = CRS.from_proj4(f"+proj=longlat +R={RADIUS_M} +no_defs")


class DEMSampler:
    def __init__(self, source):
        self.source = source
        product_name = Path(source.name).stem.upper()
        unit = (source.units[0] or '').lower() if source.count else ''
        if product_name.startswith('LDSM_') or product_name.endswith('_SLP') or 'degree' in unit:
            raise ValueError(f'{source.name}: mappa di pendenza, non DEM di quote. Usare LDEM o *_surf.tif.')
        if source.count != 1 or source.crs is None:
            raise ValueError("Serve un DEM monobanda con CRS lunare.")
        crs = CRS.from_wkt(source.crs.to_wkt())
        if not (np.isclose(crs.ellipsoid.semi_major_metre, RADIUS_M)
                and np.isclose(crs.ellipsoid.semi_minor_metre, RADIUS_M)):
            raise ValueError("Il DEM deve usare la sfera lunare di raggio 1737400 m.")
        self.to_xy = Transformer.from_crs(LUNAR_CRS, crs, always_xy=True)
        self.data = self._read() if source.width * source.height <= 20_000_000 else None
        self._tiles = OrderedDict()
        self._cache_bytes = 0

    def _read(self, window=None):
        src = self.source
        data = src.read(1, window=window, masked=True).astype("float64").filled(np.nan)
        data = data * src.scales[0] + src.offsets[0]
        data[~np.isfinite(data)] = np.nan
        return data

    def sample(self, lon, lat):
        x, y = self.to_xy.transform(lon, lat)
        inverse = ~self.source.transform
        col = inverse.a*np.asarray(x) + inverse.b*np.asarray(y) + inverse.c
        row = inverse.d*np.asarray(x) + inverse.e*np.asarray(y) + inverse.f
        # Rasterio riferisce la trasformazione all'angolo; scipy ai centri.
        row, col = np.atleast_1d(row) - 0.5, np.atleast_1d(col) - 0.5
        result = np.full(row.shape, np.nan)
        inside = (np.isfinite(row) & np.isfinite(col) & (row >= 0) & (col >= 0)
                  & (row <= self.source.height-1) & (col <= self.source.width-1))
        indices = np.flatnonzero(inside)
        if self.data is not None:
            result[indices] = map_coordinates(self.data, [row[indices], col[indices]], order=1,
                mode='constant', cval=np.nan, prefilter=False)
        elif indices.size:
            # Campionamento per tile: finestre limitate anche per raggi lunghi.
            # Una finestra rettangolare lungo la diagonale leggerebbe milioni
            # di pixel inutili tra pochi campioni distanti 100 metri.
            tile_h, tile_w = self.source.block_shapes[0]
            if tile_h == 1:
                tile_h = 256
            ncols = (self.source.width+tile_w-1)//tile_w
            keys = (row[indices].astype(int)//tile_h)*ncols + col[indices].astype(int)//tile_w
            for key in np.unique(keys):
                idx = indices[keys == key]
                r0, c0 = int(key//ncols)*tile_h, int(key%ncols)*tile_w
                cache_key = (r0, c0)
                if cache_key not in self._tiles:
                    height = min(tile_h+1, self.source.height-r0)
                    width = min(tile_w+1, self.source.width-c0)
                    tile = self._read(Window(c0, r0, width, height))
                    self._tiles[cache_key] = tile
                    self._cache_bytes += tile.nbytes
                    while self._cache_bytes > 64*1024*1024 and len(self._tiles)>1:
                        _, removed = self._tiles.popitem(last=False)
                        self._cache_bytes -= removed.nbytes
                self._tiles.move_to_end(cache_key)
                result[idx] = map_coordinates(self._tiles[cache_key], [row[idx]-r0, col[idx]-c0],
                    order=1, mode='constant', cval=np.nan, prefilter=False)
        return result


def elevation_angles(heights, ground_m, observer_height_m, distances_m):
    """Approssimazione prescritta nel README, con curvatura lunare."""
    d = np.asarray(distances_m, dtype=float)
    return np.degrees(np.arctan2(
        np.asarray(heights) - ground_m - observer_height_m - d*d/(2*RADIUS_M), d))


def calculate_horizon(input_path, lat=None, lon=None, name=None,
                      observer_height_m=2.0, near_distance_m=10_000.0,
                      step_m=5.0, far_dem=None, max_distance_m=200_000.0,
                      far_step_m=100.0, fallback_dems=None):
    """Orizzonte con DEM vicino, mosaico lontano e fallback regionali ordinati.

    Ogni fonte riempie soltanto campioni mancanti della fonte precedente.
    Le zone senza dati rimangono sconosciute, mai sostituite con quota zero.
    La copertura e riferita ai campioni, non alla risoluzione di tutti i rilievi.
    """
    if lat is None or lon is None:
        raise ValueError('Specificare lat e lon effettive del sito: il centro del DEM non viene usato automaticamente.')
    for value in (step_m, far_step_m, near_distance_m, max_distance_m):
        if not np.isfinite(value) or value <= 0:
            raise ValueError('Passi e distanze devono essere positivi e finiti.')
    if step_m > near_distance_m or max_distance_m < near_distance_m:
        raise ValueError('Servono passo <= distanza vicina <= distanza massima.')
    if not np.isfinite(observer_height_m) or observer_height_m < 0:
        raise ValueError('Altezza osservatore non valida.')
    if (lat is None) != (lon is None):
        raise ValueError('Specificare insieme latitudine e longitudine.')
    requested_far_dem = str(far_dem) if far_dem is not None else None
    requested_fallback_dems = [str(p) for p in (fallback_dems or [])]
    input_path = resolve_dem_path(input_path)
    far_dem = resolve_dem_path(far_dem) if far_dem is not None else None
    fallback_dems = [resolve_dem_path(p) for p in (fallback_dems or [])]
    if fallback_dems and far_dem is None:
        raise ValueError('I fallback richiedono anche --far-dem.')
    position = describe_site(input_path, lat, lon)
    lat, lon = position['lat'], position['lon']
    with ExitStack() as stack:
        src = stack.enter_context(rasterio.open(input_path))
        near = DEMSampler(src)
        paths = ([far_dem] if far_dem else []) + fallback_dems
        regional = [DEMSampler(stack.enter_context(rasterio.open(path))) for path in paths]
        sources = [near] + regional
        labels = ['vicino'] + (['lontano'] if far_dem else []) + [f'fallback{i+1}' for i in range(len(fallback_dems))]
        provenance = []
        for label, sampler in zip(labels, sources):
            dataset = sampler.source
            provenance.append({'id': label, 'file': str(dataset.name), 'shape': list(dataset.shape),
                'resolution_m': list(dataset.res), 'scale': dataset.scales[0], 'offset': dataset.offsets[0],
                'vertical_unit': 'm (documentazione NASA; verificata per confronto in sovrapposizione)',
                'bounds_m': dict(zip(('left','bottom','right','top'),dataset.bounds)),
                'radius_m': RADIUS_M})
        if not (np.isfinite(lat) and np.isfinite(lon) and -90 < lat < 90 and -180 <= lon <= 180):
            raise ValueError('Coordinate non valide; al polo esatto il Nord non e univoco.')
        ground = float(near.sample([lon], [lat])[0])
        if not np.isfinite(ground):
            raise ValueError('Il sito non ha una quota valida nel DEM vicino.')
        distances = np.append(np.arange(step_m, near_distance_m, step_m), near_distance_m)
        if regional and max_distance_m > near_distance_m:
            distances = np.concatenate((distances,
                np.arange(near_distance_m+far_step_m, max_distance_m, far_step_m), [max_distance_m]))
        geod = Geod(a=RADIUS_M, b=RADIUS_M)
        horizons, coverage, local_horizon, obstructions = [], [], [], []
        totals = {label: 0 for label in labels}
        for az in range(360):
            lons, lats, _ = geod.fwd(np.full(distances.size, lon), np.full(distances.size, lat),
                                      np.full(distances.size, az), distances)
            heights = np.full(distances.size, np.nan)
            source_index = np.full(distances.size, -1, dtype=np.int8)
            local = distances <= near_distance_m
            heights[local] = near.sample(lons[local], lats[local])
            source_index[np.isfinite(heights)] = 0
            local_angles = elevation_angles(heights, ground, observer_height_m, distances)
            local_horizon.append(float(np.nanmax(local_angles)) if np.isfinite(local_angles).any() else None)
            for index, sampler in enumerate(regional, 1):
                missing = ~np.isfinite(heights)
                if not missing.any():
                    break
                samples = sampler.sample(lons[missing], lats[missing])
                positions = np.flatnonzero(missing)
                heights[positions] = samples
                source_index[positions[np.isfinite(samples)]] = index
            valid = np.isfinite(heights)
            if not valid.any():
                raise ValueError(f'Nessun terreno disponibile ad azimut {az}.')
            angles = elevation_angles(heights, ground, observer_height_m, distances)
            winner = int(np.nanargmax(angles))
            horizons.append(float(angles[winner]))
            counts = {label: int(np.count_nonzero(source_index == i)) for i, label in enumerate(labels)}
            for label in labels:
                totals[label] += counts[label]
            coverage.append({'azimut': az, 'campioni_validi': int(valid.sum()),
                'campioni_totali': int(distances.size), 'campioni_per_fonte': counts,
                'distanza_valida_massima_m': float(distances[valid].max()),
                'copertura_completa': bool(valid.all())})
            obstructions.append({'azimut': az, 'distanza_m': float(distances[winner]),
                'quota_m': float(heights[winner]), 'fonte': labels[int(source_index[winner])]})
    complete = bool(regional) and all(c['copertura_completa'] for c in coverage)
    warnings = []
    if not regional:
        warnings.append('DEM lontano assente: rilievi oltre il DEM locale non valutati.')
    if not all(c['copertura_completa'] for c in coverage):
        warnings.append('Copertura incompleta: campioni fuori raster o NoData; orizzonte potenzialmente sottostimato.')
    if fallback_dems and any(totals[label] for label in labels[2:]):
        warnings.append('Fuori dalla copertura del DEM lontano prioritario sono usati DEM di supporto; dettaglio nei metadati.')
    return {'nome': name or Path(input_path).stem, 'lat': float(lat), 'lon': float(lon),
        'orizzonte': horizons, 'orizzonte_locale': local_horizon,
        'metadati': {'coordinate_origin': 'explicit_site_coordinates', 'site_position': position, 'quota_sito_m': ground, 'altezza_osservatore_m': observer_height_m,
            'raggio_lunare_m': RADIUS_M, 'frame': 'MOON_ME_DE421 (fonti NASA PGDA)',
            'azimut': '0=Nord geografico, 90=Est, 180=Sud, 270=Ovest',
            'dem_vicino': str(input_path), 'dem_lontano': str(far_dem) if far_dem else None,
            'dem_fallback': [str(p) for p in fallback_dems], 'fonti': provenance,
            'dem_lontano_richiesto': requested_far_dem, 'fallback_richiesti': requested_fallback_dems,
            'passo_vicino_m': step_m, 'passo_lontano_m': far_step_m,
            'distanza_vicina_m': near_distance_m, 'distanza_massima_richiesta_m': max_distance_m,
            'distanza_massima_campionata_m': float(distances[-1]),
            'copertura_completa_entro_distanza_richiesta': complete,
            'copertura_per_azimut': coverage, 'campioni_per_fonte': totals,
            'ostruzione_massima_per_azimut': obstructions,
            'modello_curvatura': 'Approssimazione d^2/(2R), senza rifrazione atmosferica',
            'limite_risoluzione': 'Copertura completa dei campioni non implica rilevamento di ogni rilievo tra campioni o oltre il raggio scelto.',
            'avvertenze': warnings}}

def plot_horizon(input_path, profile, output_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    from rasterio.enums import Resampling

    with rasterio.open(input_path) as src:
        factor = max(1, max(src.shape)/1000)
        image = src.read(1, out_shape=(max(1, int(src.height/factor)), max(1, int(src.width/factor))),
                         masked=True, resampling=Resampling.average)
        image = image * src.scales[0] + src.offsets[0]
        x, y = Transformer.from_crs(LUNAR_CRS, src.crs, always_xy=True).transform(profile["lon"], profile["lat"])
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
        raster = axes[0].imshow(image, extent=(src.bounds.left, src.bounds.right,
                                              src.bounds.bottom, src.bounds.top), cmap="terrain")
        axes[0].plot(x, y, 'r+', markersize=12, label='Sito: coordinate esplicite')
        center_x,center_y=src.transform*(src.width/2,src.height/2)
        axes[0].plot(center_x,center_y,'x',color='gray',markersize=7,label='Centro DEM')
        axes[0].set(xlabel="X griglia [m]", ylabel="Y griglia [m]", title=profile["nome"])
        axes[0].xaxis.set_major_locator(MaxNLocator(4))
        axes[0].legend()
        fig.colorbar(raster, ax=axes[0], label="Quota [m]")
        if profile.get('orizzonte_locale') and all(v is not None for v in profile['orizzonte_locale']):
            axes[1].plot(np.arange(361), profile['orizzonte_locale'] + profile['orizzonte_locale'][:1], '--', color='gray', label='Solo DEM vicino')
        axes[1].plot(np.arange(361), profile['orizzonte'] + profile['orizzonte'][:1], label='Con terreno lontano')
        axes[1].legend()
        axes[1].set(xlabel="Azimut geografico [gradi]", ylabel="Elevazione [gradi]",
                    title="Orizzonte campionato" + (" (copertura parziale)" if not profile["metadati"]["copertura_completa_entro_distanza_richiesta"] else ""),
                    xlim=(0, 360), xticks=[0, 90, 180, 270, 360])
        axes[1].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(output_path, dpi=140)
        plt.close(fig)





