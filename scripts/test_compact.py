import tempfile
from pathlib import Path
import unittest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from script import analyze

class CompactTest(unittest.TestCase):
    def test_same_metrics_without_raster_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dem = root/'dem.tif'
            y, x = np.indices((9,9), dtype=np.float32)
            with rasterio.open(dem, 'w', driver='GTiff', width=9, height=9, count=1,
                dtype='float32', crs='+proj=stere +lat_0=-90 +R=1737400 +units=m',
                transform=from_origin(100,200,5,5), nodata=np.nan) as dst:
                dst.write(x*.5+y*.2, 1)
            compact = analyze(dem, root/'compact', write_rasters=False)
            complete = analyze(dem, root/'complete', write_rasters=True)
            self.assertEqual(compact, complete)
            self.assertTrue((root/'compact/site_cells.csv').is_file())
            self.assertFalse((root/'compact/terrain_metrics.tif').exists())
            self.assertTrue((root/'complete/terrain_metrics.tif').is_file())
