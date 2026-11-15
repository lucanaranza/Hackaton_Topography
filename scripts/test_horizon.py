import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

from horizon import DEMSampler, LUNAR_CRS, calculate_horizon, elevation_angles


class HorizonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.crs = "+proj=stere +lat_0=-90 +lon_0=0 +R=1737400 +units=m +no_defs"
        self.x, self.y = Transformer.from_crs(LUNAR_CRS, self.crs, always_xy=True).transform(90, -89.5)

    def dem(self, name, slope=0, level=0, size=121):
        transform = from_origin(self.x-size*5, self.y+size*5, 10, 10)
        _, columns = np.indices((size, size))
        data = level+slope*(transform.c+(columns+0.5)*10-self.x)
        path = Path(self.temp.name)/name
        with rasterio.open(path, "w", driver="GTiff", width=size, height=size, count=1,
                           dtype="float64", crs=self.crs, transform=transform, nodata=np.nan) as src:
            src.write(data, 1)
        return path

    def calculate(self, path, **kwargs):
        return calculate_horizon(path, lat=-89.5, lon=90, observer_height_m=0,
                                 near_distance_m=100, step_m=10, max_distance_m=300,
                                 far_step_m=10, **kwargs)

    def test_geographic_north_not_grid_north(self):
        result = self.calculate(self.dem("ramp.tif", slope=0.1))
        self.assertEqual(len(result["orizzonte"]), 360)
        # Alla longitudine 90 il Nord geografico e circa +X della griglia.
        self.assertAlmostEqual(result["orizzonte"][0], np.degrees(np.arctan(.1)), delta=.002)
        self.assertLess(result["orizzonte"][180], -5.7)
        self.assertLess(abs(result["orizzonte"][90]), .002)
        json.dumps(result, allow_nan=False)

    def test_curvature_and_observer_height(self):
        result = self.calculate(self.dem("flat.tif"))
        expected = float(elevation_angles([0], 0, 0, [10])[0])
        np.testing.assert_allclose(result["orizzonte"], expected, atol=1e-9)
        self.assertLess(expected, 0)
        self.assertLess(elevation_angles([0], 0, 2, [10])[0], expected)

    def test_far_terrain_and_complete_coverage(self):
        near, far = self.dem("near.tif"), self.dem("far.tif", level=100)
        result = self.calculate(near, far_dem=far)
        expected = float(elevation_angles([100], 0, 0, [110])[0])
        np.testing.assert_allclose(result["orizzonte"], expected, atol=1e-9)
        self.assertTrue(result["metadati"]["copertura_completa_entro_distanza_richiesta"])

    def test_missing_coverage_is_reported(self):
        result = self.calculate(self.dem("small.tif", size=11))
        self.assertFalse(result["metadati"]["copertura_completa_entro_distanza_richiesta"])
        self.assertTrue(any(not c["copertura_completa"] for c in result["metadati"]["copertura_per_azimut"]))
        self.assertEqual(len(result["metadati"]["avvertenze"]), 2)

    def test_invalid_site_and_parameters(self):
        path = self.dem("flat.tif")
        with self.assertRaises(ValueError):
            calculate_horizon(path, lat=0, lon=0)
        with self.assertRaises(ValueError):
            calculate_horizon(path, lat=-89.5)
        with self.assertRaises(ValueError):
            calculate_horizon(path, step_m=0)

    def test_windowed_sampling_and_nodata(self):
        path = self.dem("window.tif", slope=.1)
        with rasterio.open(path, "r+") as src:
            data = src.read(1)
            data[60, 60] = np.nan
            src.write(data, 1)
        with rasterio.open(path) as src:
            sampler = DEMSampler(src)
            cached = sampler.sample([90, 90.05], [-89.5, -89.5])
            sampler.data = None
            windowed = sampler.sample([90, 90.05], [-89.5, -89.5])
            np.testing.assert_allclose(cached, windowed, equal_nan=True)
            self.assertTrue(np.isnan(windowed[0]))


if __name__ == "__main__":
    unittest.main()
