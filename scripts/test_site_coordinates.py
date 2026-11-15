"""Verifiche per punti reali decentrati e coordinate mancanti/esterne."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from pyproj import Transformer
import test_horizon as fixtures
from horizon import LUNAR_CRS, calculate_horizon
from script import analyze
from site_coordinates import checked_coordinates, describe_site, create_template, preflight

class CoordinateTests(unittest.TestCase):
    setUp=fixtures.HorizonTests.setUp
    dem=fixtures.HorizonTests.dem

    def off_center(self):
        lon,lat=Transformer.from_crs(self.crs,LUNAR_CRS,always_xy=True).transform(self.x+100,self.y+50)
        return lat,lon

    def test_no_implicit_dem_center(self):
        path=self.dem('dem.tif')
        with self.assertRaisesRegex(ValueError,'centro del DEM'):
            calculate_horizon(path)

    def test_off_center_coordinates_select_known_pixel_and_elevation(self):
        path=self.dem('dem.tif',slope=.1)
        lat,lon=self.off_center()
        point=describe_site(path,lat,lon)
        self.assertEqual((point['pixel_row'],point['pixel_col']),(55,70))
        self.assertAlmostEqual(point['x_m'],self.x+100,places=6)
        self.assertAlmostEqual(point['y_m'],self.y+50,places=6)
        self.assertAlmostEqual(point['ground_elevation_m'],10,places=6)
        self.assertGreater(point['distance_from_dem_center_m'],100)
        result=calculate_horizon(path,lat=lat,lon=lon,near_distance_m=100,step_m=10,max_distance_m=300)
        self.assertAlmostEqual(result['lat'],lat,places=12)
        self.assertAlmostEqual(result['lon'],lon,places=12)
        self.assertEqual(result['metadati']['site_position']['pixel_col'],70)
        self.assertEqual(result['metadati']['coordinate_origin'],'explicit_site_coordinates')

    def test_summary_site_is_separate_from_dem_center(self):
        path=self.dem('dem.tif',slope=.1)
        lat,lon=self.off_center()
        summary=analyze(path,Path(self.temp.name)/'metrics',write_rasters=False,lat=lat,lon=lon,coordinate_source='test reference')
        self.assertAlmostEqual(summary['site']['ground_elevation_m'],10,places=6)
        self.assertNotEqual(summary['site']['lon'],summary['center']['longitude_deg'])
        self.assertEqual(summary['statistics_scope'],'entire_dem')
        self.assertEqual(summary['site']['coordinate_source'],'test reference')
        self.assertIsNotNone(summary['site']['cell_statistics'])

    def test_outside_dem_is_rejected(self):
        path=self.dem('dem.tif')
        with self.assertRaisesRegex(ValueError,'fuori dal DEM'):
            describe_site(path,0,0)

    def test_positive_east_longitude_normalization(self):
        self.assertEqual(checked_coordinates(-89.5,270),(-89.5,-90))
        with self.assertRaises(ValueError):checked_coordinates(-89.5,None)

    def test_missing_catalog_coordinate_stays_missing(self):
        root=Path(self.temp.name)
        (root/'data/Sito_A').mkdir(parents=True)
        self.dem('data/Sito_A/example_surf.tif')
        catalog=root/'catalog.json'
        create_template(root/'data',catalog)
        result=preflight(root/'data',catalog,root/'control')
        self.assertFalse(result['ready'])
        self.assertEqual(result['ready_count'],0)
        self.assertIsNone(result['sites'][0]['lat'])
        self.assertIsNotNone(result['sites'][0]['dem_center_lat'])

    def test_catalog_off_center_point_is_ready(self):
        root=Path(self.temp.name)
        (root/'data/Sito_A').mkdir(parents=True)
        self.dem('data/Sito_A/example_surf.tif',slope=.1)
        lat,lon=self.off_center()
        catalog=root/'catalog.json'
        catalog.write_text(json.dumps({'frame':'MOON_ME_DE421','units':'degree','longitude_positive':'east',
            'sites':[{'site_id':'Sito_A','lat':lat,'lon':lon,'source':'reference point'}]}),encoding='utf-8')
        result=preflight(root/'data',catalog,root/'control')
        self.assertTrue(result['ready'])
        self.assertEqual(result['sites'][0]['pixel_col'],70)
        value=json.loads(catalog.read_text())
        value['frame']='EPSG:4326';catalog.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'MOON_ME_DE421'):
            preflight(root/'data',catalog,root/'control')

    def test_cli_missing_coordinate_does_not_write_results(self):
        root=Path(self.temp.name)
        path=self.dem('dem.tif')
        output=root/'must_not_be_created'
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('script.py')),
            '--input',str(path),'--output',str(output),'--mode','all'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('--lat e --lon',result.stderr)
        self.assertFalse(output.exists())
