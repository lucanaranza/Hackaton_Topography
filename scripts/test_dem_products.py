"""Test della risoluzione LDSM -> LDEM senza usare gradi come metri."""
import unittest
from pathlib import Path
import numpy as np
import rasterio
import test_horizon as fixtures
from dem_products import resolve_dem_path
from horizon import DEMSampler

class ProductTests(unittest.TestCase):
    setUp = fixtures.HorizonTests.setUp
    dem = fixtures.HorizonTests.dem
    calculate = fixtures.HorizonTests.calculate

    def test_nested_dem_and_different_extension(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff')
        (Path(self.temp.name)/'60S').mkdir()
        dem = self.dem('60S/LDEM_60S_240MPP_ADJ.TIF')
        self.assertEqual(resolve_dem_path(slope),dem.resolve())

    def test_horizon_resolves_reference_to_actual_elevation(self):
        near = self.dem('near.tif')
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff',level=3)
        dem = self.dem('LDEM_60S_240MPP_ADJ.TIF',level=100)
        referenced = self.calculate(near,far_dem=slope)
        explicit = self.calculate(near,far_dem=dem)
        np.testing.assert_array_equal(referenced['orizzonte'],explicit['orizzonte'])
        self.assertEqual(referenced['metadati']['dem_lontano'],str(dem.resolve()))
        self.assertEqual(referenced['metadati']['dem_lontano_richiesto'],str(slope))

    def test_mismatched_grid_is_rejected(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff',size=11)
        self.dem('LDEM_60S_240MPP_ADJ.TIF')
        with self.assertRaisesRegex(ValueError,'stessa griglia'):
            resolve_dem_path(slope)

    def test_wrong_resolution_name_is_not_selected(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff')
        self.dem('LDEM_60S_120MPP_ADJ.TIF')
        with self.assertRaisesRegex(ValueError,'Non trovo LDEM_60S_240MPP_ADJ'):
            resolve_dem_path(slope)

    def test_ambiguous_candidates_are_rejected(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff')
        self.dem('LDEM_60S_240MPP_ADJ.TIF')
        (Path(self.temp.name)/'duplicate').mkdir()
        self.dem('duplicate/LDEM_60S_240MPP_ADJ.tiff')
        with self.assertRaisesRegex(ValueError,'Piu LDEM'):
            resolve_dem_path(slope)

    def test_low_level_sampler_still_rejects_slope_pixels(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tiff')
        with rasterio.open(slope) as src:
            with self.assertRaisesRegex(ValueError,'mappa di pendenza'):
                DEMSampler(src)
