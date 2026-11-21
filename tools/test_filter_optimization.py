import io
import struct
import unittest
import zlib

import numpy as np
from PIL import Image

from encode_png import chunk
from optimize_filters import variants,best_block,fast_compress
from strong_combined import BitJoiner,combine_adler


def png(raw,size):
    stream=io.BytesIO()
    stream.write(b'\x89PNG\r\n\x1a\n')
    chunk(stream,b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))
    chunk(stream,b'IDAT',raw)
    chunk(stream,b'IEND',b'')
    return stream.getvalue()


class FilterTest(unittest.TestCase):
    def test_all_filter_strategies_preserve_every_rgb_pixel(self):
        random=np.random.default_rng(8).integers(0,256,(17,17,3),dtype=np.uint8)
        for pixels in [random,np.full((17,17,3),119,np.uint8)]:
            choices,_=variants(pixels.reshape(17,51),np.zeros(51,np.uint8))
            for name,raw in choices.items():
                with self.subTest(strategy=name):
                    with Image.open(io.BytesIO(png(zlib.compress(raw),17))) as decoded:
                        np.testing.assert_array_equal(np.asarray(decoded),pixels)

    def test_reused_and_new_blocks_form_one_lossless_image(self):
        pixels=np.random.default_rng(31).integers(0,256,(17,17,3),dtype=np.uint8)
        previous=np.zeros(51,np.uint8)
        joined=bytearray(b'\x78\xda')
        checksum=1
        joiner=BitJoiner()
        for start in range(0,17,4):
            rows=pixels.reshape(17,51)[start:start+4]
            choices,previous=variants(rows,previous)
            final=start+len(rows)==17
            old=fast_compress(choices['avg'],final)
            record=best_block(choices,old,final)
            self.assertLessEqual(len(record[3]),len(old[3]))
            joined.extend(joiner.append(record[3],record[0]))
            checksum=combine_adler(checksum,record[2],record[1])
        joined.extend(joiner.finish())
        joined.extend(struct.pack('>I',checksum))
        with Image.open(io.BytesIO(png(joined,17))) as decoded:
            np.testing.assert_array_equal(np.asarray(decoded),pixels)


if __name__=='__main__':
    unittest.main()
