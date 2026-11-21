import unittest
import zlib
import io
import struct
import numpy as np
from PIL import Image

from strong_combined import BitJoiner, combine_adler, average_rows
from encode_png import chunk


class StrongCompressionTest(unittest.TestCase):
    def test_average_filter_preserves_rgb_across_work_boundaries(self):
        pixels = np.random.default_rng(91).integers(0,256,(17,17,3),dtype=np.uint8)
        rows = pixels.reshape(17,51)
        previous = np.zeros(51,np.uint8)
        encoded = []
        for start in range(0,17,4):
            block,previous = average_rows(rows[start:start+4],previous)
            encoded.append(block)
        file = io.BytesIO()
        file.write(b'\x89PNG\r\n\x1a\n')
        chunk(file,b'IHDR',struct.pack('>IIBBBBB',17,17,8,2,0,0,0))
        chunk(file,b'IDAT',zlib.compress(b''.join(encoded)))
        chunk(file,b'IEND',b'')
        with Image.open(io.BytesIO(file.getvalue())) as decoded:
            np.testing.assert_array_equal(np.asarray(decoded),pixels)

    def test_unaligned_bit_boundaries(self):
        pieces = [(b'\xfd',3),(b'\x91\x83\xff',19),(b'\x01',1),(b'\x42\xa6',16),(b'\xff',7)]
        expected = []
        joiner = BitJoiner()
        result = bytearray()
        for data,count in pieces:
            expected.extend((data[index//8] >> (index%8)) & 1 for index in range(count))
            result.extend(joiner.append(data,count))
        result.extend(joiner.finish())
        actual = [(result[index//8] >> (index%8)) & 1 for index in range(len(expected))]
        self.assertEqual(actual,expected)
        self.assertEqual(len(result),(len(expected)+7)//8)

    def test_single_standard_zlib_stream_and_checksum(self):
        pieces = [bytes(range(256))*27,b'\0'*90000,b'land and water'*1000]
        joiner = BitJoiner()
        result = bytearray(b'\x78\xda')
        checksum = 1
        for index,piece in enumerate(pieces):
            compressor = zlib.compressobj(wbits=-15)
            data = compressor.compress(piece)+compressor.flush(zlib.Z_FINISH if index==len(pieces)-1 else zlib.Z_SYNC_FLUSH)
            result.extend(joiner.append(data,len(data)*8))
            checksum = combine_adler(checksum,zlib.adler32(piece),len(piece))
        result.extend(joiner.finish())
        result.extend(checksum.to_bytes(4,'big'))
        self.assertEqual(checksum,zlib.adler32(b''.join(pieces)))
        self.assertEqual(zlib.decompress(result),b''.join(pieces))


if __name__=='__main__':
    unittest.main()
