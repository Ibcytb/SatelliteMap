"""Exercise pixel preservation, PNG filters, dimensions and stream corruption."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

from encode_combined import encode_combined, merge_pixels, validate_combined


class CombinedTest(unittest.TestCase):
    def test_pixels_dimensions_and_crc(self):
        rng = np.random.default_rng(20261121)
        rgb = rng.integers(0,256,(3,512,512),dtype=np.uint8)
        land_alpha = np.zeros((512,512),np.uint8)
        land_alpha[:256] = 255
        land_alpha[256:300] = 128
        land = np.concatenate([rgb,land_alpha[None]])
        water = np.concatenate([rgb,(255-land_alpha)[None]])
        # Discarded RGB cannot leak into the merged image.
        land[:3,land_alpha==0] = 0
        water[:3,land_alpha==255] = 0
        np.testing.assert_array_equal(merge_pixels(land,water),rgb.transpose(1,2,0))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name,pixels in [('land',land),('water',water)]:
                with rasterio.open(root/f'{name}.tif','w',driver='GTiff',width=512,height=512,count=4,dtype='uint8') as out:
                    out.write(pixels)
            for size in [17,512]:
                info = encode_combined(root/'land.tif',root/'water.tif',root,size)
                png = root/info['filename']
                with Image.open(png) as decoded:
                    self.assertEqual(decoded.size,(size,size))
                    self.assertEqual(decoded.mode,'RGB')
                    with rasterio.open(root/'land.tif') as source:
                        expected_land = source.read(out_shape=(4,size,size),resampling=Resampling.nearest)
                    with rasterio.open(root/'water.tif') as source:
                        expected_water = source.read(out_shape=(4,size,size),resampling=Resampling.nearest)
                    np.testing.assert_array_equal(np.asarray(decoded),merge_pixels(expected_land,expected_water))
            corrupt = bytearray(png.read_bytes())
            corrupt[-5] ^= 1
            bad = root/'corrupt.png'
            bad.write_bytes(corrupt)
            with self.assertRaises(AssertionError):
                validate_combined(bad,512)

    def test_missing_coverage_is_rejected(self):
        empty = np.zeros((4,2,2),np.uint8)
        with self.assertRaises(ValueError):
            merge_pixels(empty,empty)


if __name__=='__main__':
    unittest.main()
