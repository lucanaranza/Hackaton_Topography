"""Verifiche numeriche indipendenti su un piano e su dati mancanti."""
import unittest

import numpy as np

from script import terrain_derivatives


class TerrainTests(unittest.TestCase):
    def test_plane(self):
        rows, cols = np.indices((7, 7), dtype=float)
        # z = 0.1*x + 0.2*north: discesa verso sud-ovest.
        z = 0.1 * cols * 5 - 0.2 * rows * 5
        slope, aspect = terrain_derivatives(z, 5, 5)
        np.testing.assert_allclose(slope[1:-1, 1:-1], np.degrees(np.arctan(np.sqrt(0.05))))
        np.testing.assert_allclose(aspect[1:-1, 1:-1], 206.565051177)
        self.assertTrue(np.isnan(slope[0]).all())

    def test_flat_and_nodata(self):
        z = np.zeros((7, 7))
        z[3, 3] = np.nan
        slope, aspect = terrain_derivatives(z, 5, 5)
        self.assertTrue(np.isnan(slope[3, 3]))
        self.assertTrue(np.isnan(slope[2, 3]))
        self.assertTrue(np.isnan(slope[3, 2]))
        self.assertEqual(slope[1, 1], 0)
        self.assertTrue(np.isnan(aspect).all())


if __name__ == "__main__":
    unittest.main()
