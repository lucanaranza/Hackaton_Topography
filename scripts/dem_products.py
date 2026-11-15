"""Trova il prodotto LDEM corrispondente a una mappa LDSM locale."""
from pathlib import Path
import re
import rasterio


def resolve_dem_path(value):
    """LDSM identifica regione/risoluzione; le quote si leggono dal LDEM.

    Cerca soltanto nella cartella della mappa e nelle sue sottocartelle.
    Non inverte le pendenze e non modifica/scarica alcun raster.
    """
    path = Path(value)
    if not path.stem.upper().startswith('LDSM_'):
        return path
    match = re.fullmatch(r'LDSM_(\d+[NS])_(\d+MPP)_ADJ', path.stem, re.IGNORECASE)
    if not match:
        raise ValueError('Serve una mappa LDSM_<regione>_<risoluzione>_ADJ, non una mappa di errore o altro derivato.')
    if not path.is_file():
        raise ValueError(f'Mappa LDSM non trovata: {path}')
    expected = f'LDEM_{match[1]}_{match[2]}_ADJ'.upper()
    matches = sorted({f.resolve() for f in path.parent.rglob('*')
        if f.is_file() and f.suffix.lower() in ('.tif', '.tiff') and f.stem.upper() == expected})
    if not matches:
        raise ValueError(f'Non trovo {expected}.tif nella cartella {path.parent} e sottocartelle. Il LDEM deve contenere quote: non si ricostruiscono univocamente dalla sola pendenza LDSM.')
    if len(matches) != 1:
        raise ValueError(f'Piu LDEM corrispondenti a {path.name}: specificare direttamente il DEM desiderato. Trovati: '+', '.join(map(str,matches)))
    dem = matches[0]
    with rasterio.open(path) as slope, rasterio.open(dem) as elevation:
        same_crs = (slope.crs is not None and elevation.crs is not None
                    and slope.crs.to_dict() == elevation.crs.to_dict())
        if (slope.count != 1 or elevation.count != 1 or slope.shape != elevation.shape
                or not slope.transform.almost_equals(elevation.transform) or not same_crs):
            raise ValueError(f'LDSM e LDEM non hanno la stessa griglia/proiezione: {path}, {dem}')
    return dem
