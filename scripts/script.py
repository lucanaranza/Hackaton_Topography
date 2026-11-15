"""Calcola l'orizzonte lunare per il motore effemeridi e metriche opzionali.

Esempio: python scripts/script.py --input DEM.tif --lat LAT --lon LON
Metriche precedenti: python scripts/script.py --mode metrics
Le soglie sono filtri esplorativi, non criteri di certificazione del lander.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as transform_coordinates
from dem_products import resolve_dem_path
from site_coordinates import describe_site


SOURCE_URL = "https://pgda.gsfc.nasa.gov/products/78"


def statistics(values):
    values = values[np.isfinite(values)]
    if not values.size:
        return None
    return {
        "count": int(values.size),
        "min": float(values.min()), "max": float(values.max()),
        "mean": float(values.mean(dtype=np.float64)),
        "std": float(values.std(dtype=np.float64)),
        **{f"p{p}": float(np.percentile(values, p)) for p in (5, 50, 95)},
    }


def terrain_derivatives(elevation, dx, dy):
    """Differenze centrate a 3 punti; nessuna estrapolazione ai bordi.

    Aspect: direzione di discesa, oraria dal nord della GRIGLIA, non nord
    geografico. Al polo le due direzioni possono essere molto diverse.
    """
    dz_south, dz_east = np.gradient(elevation, dy, dx)
    dz_north = -dz_south
    valid = np.isfinite(elevation)
    stencil = np.zeros(valid.shape, dtype=bool)
    stencil[1:-1, 1:-1] = (
        valid[1:-1, 1:-1] & valid[:-2, 1:-1] & valid[2:, 1:-1]
        & valid[1:-1, :-2] & valid[1:-1, 2:]
    )
    magnitude = np.hypot(dz_east, dz_north)
    slope = np.degrees(np.arctan(magnitude))
    aspect = np.degrees(np.arctan2(-dz_east, -dz_north)) % 360
    slope[~stencil] = np.nan
    aspect[~stencil | (magnitude < 1e-7)] = np.nan
    return slope, aspect


def lunar_lonlat(crs, xs, ys):
    # Conserva il datum lunare: non trasformare verso EPSG:4326 terrestre.
    geographic = rasterio.crs.CRS.from_string("+proj=longlat +R=1737400 +no_defs")
    return transform_coordinates(crs, geographic, xs, ys)


def analyze(input_path, output_dir, max_slope=10.0, tile_size=100.0, write_rasters=True, lat=None, lon=None, coordinate_source=None):
    input_path = resolve_dem_path(input_path)
    site = describe_site(input_path,lat,lon) if lat is not None or lon is not None else None
    if site is not None:
        site['coordinate_source'] = coordinate_source
    output_dir = Path(output_dir)
    with rasterio.open(input_path) as src:
        if src.count != 1 or src.crs is None or not src.crs.is_projected:
            raise ValueError("Serve un DEM monobanda con CRS proiettato in metri.")
        if src.crs.linear_units != "metre":
            raise ValueError("Le unita orizzontali devono essere metri.")
        if src.crs.to_dict().get("R") != 1737400:
            raise ValueError("Questo script richiede il CRS lunare sferico con raggio 1737400 m.")
        affine = src.transform
        if affine.b != 0 or affine.d != 0 or affine.a <= 0 or affine.e >= 0:
            raise ValueError("Serve una griglia north-up, senza rotazione.")
        dx, dy = src.res
        elevation = src.read(1, masked=True).astype("float32").filled(np.nan)
        elevation *= src.scales[0]
        elevation += src.offsets[0]
        elevation[~np.isfinite(elevation)] = np.nan
        slope, aspect = terrain_derivatives(elevation, dx, dy)
        valid_slope = np.isfinite(slope)
        valid_elevation = np.isfinite(elevation)
        pixel_area = dx * dy
        tile_cols, tile_rows = round(tile_size / dx), round(tile_size / dy)
        if tile_cols < 1 or tile_rows < 1:
            raise ValueError("La dimensione delle celle deve essere almeno un pixel.")
        output_dir.mkdir(parents=True, exist_ok=True)

        if write_rasters:
            profile = src.profile.copy()
            profile.update(driver="GTiff", dtype="float32", count=3, nodata=np.nan,
                           compress="deflate", predictor=3)
            with rasterio.open(output_dir / "terrain_metrics.tif", "w", **profile) as dst:
                for band, (array, name, unit) in enumerate((
                    (elevation, "elevation_m", "m"),
                    (slope, "slope_deg", "degree"),
                    (aspect, "downslope_grid_aspect_deg", "degree"),
                ), 1):
                    dst.write(array, band)
                    dst.set_band_description(band, name)
                    dst.set_band_unit(band, unit)
                dst.update_tags(source_url=SOURCE_URL, method="central differences; grid distances",
                                elevation_reference="Verify vertical datum in source documentation")
    
            mask = np.full(elevation.shape, 255, dtype="uint8")
            mask[valid_slope] = (slope[valid_slope] <= max_slope).astype("uint8")
            profile.update(dtype="uint8", count=1, nodata=255, predictor=1)
            with rasterio.open(output_dir / "slope_filter.tif", "w", **profile) as dst:
                dst.write(mask, 1)
                dst.set_band_description(1, "passes_slope_filter")
                dst.update_tags(max_slope_deg=str(max_slope), values="0=fail; 1=pass; 255=unknown")
    
        tiles = []
        for row in range(0, src.height, tile_rows):
            for col in range(0, src.width, tile_cols):
                end_row, end_col = min(row + tile_rows, src.height), min(col + tile_cols, src.width)
                z = elevation[row:end_row, col:end_col]
                s = slope[row:end_row, col:end_col]
                zv, sv = z[np.isfinite(z)], s[np.isfinite(s)]
                if not zv.size:
                    continue
                x, y = affine * ((col + end_col) / 2, (row + end_row) / 2)
                tiles.append({
                    "row_start": row, "col_start": col,
                    "x_m": x, "y_m": y,
                    "width_m": (end_col-col)*dx, "height_m": (end_row-row)*dy,
                    "elevation_coverage_pct": 100 * zv.size / z.size,
                    "slope_coverage_pct": 100 * sv.size / s.size,
                    "elevation_mean_m": float(zv.mean(dtype=np.float64)),
                    "relief_m": float(np.ptp(zv)),
                    "slope_mean_deg": float(sv.mean(dtype=np.float64)) if sv.size else None,
                    "slope_max_deg": float(sv.max()) if sv.size else None,
                    # Denominatore: tutta la cella, dati mancanti non contano come idonei.
                    "passes_slope_filter_pct": 100 * int(np.count_nonzero(s <= max_slope)) / s.size,
                })
        if tiles:
            lon, lat = lunar_lonlat(src.crs, [t["x_m"] for t in tiles], [t["y_m"] for t in tiles])
            for tile, longitude, latitude in zip(tiles, lon, lat):
                tile.update(longitude_deg=longitude, latitude_deg=latitude)
            with (output_dir / "site_cells.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(tiles[0]))
                writer.writeheader()
                writer.writerows(tiles)

        if site is not None:
            r,c=site['pixel_row'],site['pixel_col']
            site['slope_deg_at_pixel']=float(slope[r,c]) if np.isfinite(slope[r,c]) else None
            site['grid_aspect_deg_at_pixel']=float(aspect[r,c]) if np.isfinite(aspect[r,c]) else None
            site['cell_statistics']=next((t for t in tiles if t['row_start']==(r//tile_rows)*tile_rows and t['col_start']==(c//tile_cols)*tile_cols),None)
        center = affine * (src.width / 2, src.height / 2)
        lon, lat = lunar_lonlat(src.crs, [center[0]], [center[1]])
        thresholds = sorted(set([5.0, 10.0, 15.0, 20.0, max_slope]))
        slope_count = int(valid_slope.sum())
        summary = {
            "source": str(input_path), "source_documentation": SOURCE_URL,
            "rasterio_version": rasterio.__version__,
            "shape": [src.height, src.width], "resolution_m": [dx, dy],
            "site": site, "statistics_scope": "entire_dem",
            "bounds_projected_m": dict(zip(("left", "bottom", "right", "top"), src.bounds)),
            "crs_wkt": src.crs.to_wkt(), "lunar_radius_m": 1737400,
            "center": {"x_m": center[0], "y_m": center[1],
                       "longitude_deg": lon[0], "latitude_deg": lat[0]},
            "extent_projected_km2": src.width * src.height * pixel_area / 1e6,
            "valid_elevation_projected_km2": int(valid_elevation.sum()) * pixel_area / 1e6,
            "missing_elevation_pct": 100 * (1 - int(valid_elevation.sum()) / elevation.size),
            "valid_slope_projected_km2": slope_count * pixel_area / 1e6,
            "elevation_m": statistics(elevation), "slope_deg": statistics(slope),
            "slope_filters": [{
                "max_slope_deg": threshold,
                "area_projected_km2": int(np.count_nonzero(slope <= threshold)) * pixel_area / 1e6,
                "pct_of_valid_slope": 100 * int(np.count_nonzero(slope <= threshold)) / slope_count if slope_count else None,
            } for threshold in thresholds],
            "tile_size_actual_m": [tile_cols*dx, tile_rows*dy],
            "selected_max_slope_deg": max_slope,
            "top_cells_by_slope_only": sorted(
                [t for t in tiles if t["slope_coverage_pct"] == 100],
                key=lambda t: (-t["passes_slope_filter_pct"], t["slope_max_deg"], t["relief_m"]),
            )[:10],
            "limitations": [
                "Elevation units in meters from PGDA product documentation; vertical datum must be verified before combining DEMs.",
                "Slopes use central differences over a 10 m baseline at 5 m/pixel; grid distances approximate ground distances.",
                "Areas are projected grid areas; aspect is relative to grid north.",
                "Cell relief is max minus min elevation, not detrended roughness.",
                "5 m sampling does not resolve smaller hazards and does not imply 5 m measurement accuracy.",
                "Slope filter is not landing safety or a complete suitability score; passing pixels may be disconnected.",
                "Sunlight, Earth visibility, temperature, permanent shadow and ice require additional data/models.",
            ],
        }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary


def main():
    base = Path(__file__).resolve().parent.parent
    default_dem = next((base / "dati_siti_topografia").rglob("Site01_final_adj_5mpp_surf.tif"),
                       base / "dati_siti_topografia/Site01_final_adj_5mpp_surf.tif")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default_dem)
    parser.add_argument("--output", type=Path, default=base / "risultati topografia/Sito_01")
    parser.add_argument("--max-slope", type=float, default=10.0)
    parser.add_argument("--tile-size", type=float, default=100.0)
    parser.add_argument("--mode", choices=("horizon", "metrics", "all"), default="horizon")
    parser.add_argument("--name", help="Nome sito; predefinito: nome del DEM")
    parser.add_argument("--lat", type=float, help="Latitudine effettiva del sito, obbligatoria per horizon/all")
    parser.add_argument("--lon", type=float, help="Longitudine lunare positiva a est")
    parser.add_argument("--observer-height", type=float, default=2.0, help="Altezza osservatore [m]")
    parser.add_argument("--near-distance", type=float, default=10000.0, help="Raggio DEM vicino [m]")
    parser.add_argument("--step", type=float, default=5.0, help="Passo vicino [m]")
    parser.add_argument("--far-dem", type=Path, help="DEM lontano o LDSM da cui trovare il LDEM corrispondente")
    parser.add_argument("--max-distance", type=float, default=200000.0, help="Raggio massimo [m]")
    parser.add_argument("--far-step", type=float, default=100.0, help="Passo lontano [m]")
    parser.add_argument("--no-plot", action="store_true", help="Non generare anteprima PNG")
    parser.add_argument('--no-rasters', action='store_true', help='Salva JSON, CSV e PNG senza GeoTIFF derivati')
    parser.add_argument('--fallback-dem', type=Path, action='append', default=[], help='DEM regionale aggiuntivo, ripetibile; usato solo nei buchi del mosaico')
    parser.add_argument('--coordinate-source', default='manual_cli', help='Fonte delle coordinate esplicite')
    args = parser.parse_args()
    if args.mode in ('horizon','all') and (args.lat is None or args.lon is None):
        parser.error('Per horizon/all specificare --lat e --lon del sito; nessun ripiego sul centro DEM.')
    product_mapping = []
    try:
        def resolved(value):
            actual = resolve_dem_path(value)
            if actual.resolve() != value.resolve():
                product_mapping.append({'richiesto': str(value), 'dem_usato': str(actual)})
                print(f'LDSM -> LDEM: {value} -> {actual}')
            return actual
        args.input = resolved(args.input)
        if args.far_dem is not None:
            args.far_dem = resolved(args.far_dem)
        args.fallback_dem = [resolved(p) for p in args.fallback_dem]
    except ValueError as exc:
        parser.error(str(exc))
    for dem in (args.input, args.far_dem, *args.fallback_dem):
        if dem is not None and not dem.is_file():
            parser.error(f"DEM non trovato: {dem}. Specificare il GeoTIFF con --input / --far-dem.")
    if not np.isfinite(args.max_slope) or not 0 <= args.max_slope < 90:
        parser.error("--max-slope deve essere tra 0 e 90 gradi (90 escluso)")
    if not np.isfinite(args.tile_size) or args.tile_size <= 0:
        parser.error("--tile-size deve essere positivo e finito")
    if args.mode in ("horizon", "all"):
        from horizon import calculate_horizon, plot_horizon
        try:
            profile = calculate_horizon(args.input, args.lat, args.lon, args.name,
                args.observer_height, args.near_distance, args.step, args.far_dem,
                args.max_distance, args.far_step, args.fallback_dem)
        except ValueError as exc:
            parser.error(str(exc))
        profile['metadati']['prodotti_risolti'] = product_mapping
        profile['metadati']['coordinate_source'] = args.coordinate_source
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "horizon.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if not args.no_plot:
            plot_horizon(args.input, profile, args.output / "horizon.png")
        print(f"Orizzonte: 360 valori, da {min(profile['orizzonte']):.3f} a {max(profile['orizzonte']):.3f} gradi")
        for warning in profile["metadati"]["avvertenze"]:
            print(f"ATTENZIONE: {warning}")
    if args.mode in ("metrics", "all"):
        summary = analyze(args.input, args.output, args.max_slope, args.tile_size, not args.no_rasters, lat=args.lat, lon=args.lon, coordinate_source=args.coordinate_source)
        print(json.dumps({k: summary[k] for k in (
            "shape", "resolution_m", "center", "missing_elevation_pct", "elevation_m", "slope_deg", "slope_filters"
        )}, indent=2))
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()





