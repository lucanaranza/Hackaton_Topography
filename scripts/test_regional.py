"""Test dei DEM regionali in cascata e della copertura dichiarata."""
import test_horizon as fixtures
import unittest
import numpy as np

class RegionalTests(unittest.TestCase):
    setUp = fixtures.HorizonTests.setUp
    dem = fixtures.HorizonTests.dem
    calculate = fixtures.HorizonTests.calculate
    def test_fallback_completes_missing_far_coverage(self):
        near = self.dem('near_small.tif',size=11)
        far = self.dem('far_small.tif',size=11)
        fallback = self.dem('wide.tif',level=100)
        result = self.calculate(near,far_dem=far,fallback_dems=[fallback])
        self.assertTrue(result['metadati']['copertura_completa_entro_distanza_richiesta'])
        self.assertGreater(result['metadati']['campioni_per_fonte']['fallback1'],0)
        self.assertTrue(np.all(np.asarray(result['orizzonte']) >= np.asarray(result['orizzonte_locale'])))
        self.assertTrue(all(c['campioni_validi']==c['campioni_totali'] for c in result['metadati']['copertura_per_azimut']))

    def test_fallback_does_not_override_primary_coverage(self):
        near = self.dem('near.tif')
        far = self.dem('far.tif',level=100)
        fallback = self.dem('high.tif',level=10000)
        primary = self.calculate(near,far_dem=far)
        result = self.calculate(near,far_dem=far,fallback_dems=[fallback])
        np.testing.assert_array_equal(result['orizzonte'],primary['orizzonte'])
        self.assertEqual(result['metadati']['campioni_per_fonte']['fallback1'],0)

    def test_fallback_cannot_claim_coverage_with_missing_samples(self):
        small = self.dem('small.tif',size=11)
        result = self.calculate(small,far_dem=small,fallback_dems=[small])
        self.assertFalse(result['metadati']['copertura_completa_entro_distanza_richiesta'])

    def test_missing_ldem_for_slope_product_is_reported(self):
        slope = self.dem('LDSM_60S_240MPP_ADJ.tif')
        with self.assertRaisesRegex(ValueError,'Non trovo LDEM'):
            self.calculate(slope)

