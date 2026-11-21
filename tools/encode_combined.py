"""Combine complementary map masks and stream a lossless RGB PNG, without a canvas."""
import argparse
import json
import struct
import time
import zlib
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

from encode_png import HashWriter, chunk, fast_zlib, LIMIT
from library import filename


def merge_pixels(land, water):
    """Inputs are CHW RGBA. Preserve source RGB and require complete coverage."""
    alpha = land[3].astype(np.uint16) + water[3]
    if np.any(alpha == 0):
        raise ValueError('The two source masks leave uncovered pixels.')
    # v4 masks are complementary and binary at native resolution. The weighted
    # form also handles fractional masks in the existing TIFF overview levels.
    rgb = (land[:3].astype(np.uint32) * land[3] +
           water[:3].astype(np.uint32) * water[3] + alpha // 2) // alpha
    return np.ascontiguousarray(rgb.astype(np.uint8).transpose(1, 2, 0))


def filter_row(row, previous):
    """Adaptive PNG filters, including Paeth; all calculations are lossless."""
    left = np.zeros_like(row)
    left[3:] = row[:-3]
    upper_left = np.zeros_like(previous)
    upper_left[3:] = previous[:-3]
    a, b, c = left.astype(np.int16), previous.astype(np.int16), upper_left.astype(np.int16)
    p = a + b - c
    pa, pb, pc = np.abs(p-a), np.abs(p-b), np.abs(p-c)
    predictor = np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))
    candidates = [row, row-left, row-previous,
                  row-((a+b)//2).astype(np.uint8), row-predictor.astype(np.uint8)]
    # A prime stride samples every colour channel instead of aliasing one.
    scores = [np.abs(x.view(np.int8)[::17].astype(np.int16)).sum() for x in candidates]
    code = int(np.argmin(scores))
    return bytes([code]) + candidates[code].tobytes()


def validate_combined(path, size):
    """Check every chunk CRC and the entire deflate stream with bounded memory."""
    inflater = zlib.decompressobj()
    decoded = 0
    chunks = 0
    with Path(path).open('rb') as stream:
        assert stream.read(8) == b'\x89PNG\r\n\x1a\n'
        first = True
        while True:
            header = stream.read(8)
            assert len(header) == 8
            length, kind = struct.unpack('>I4s', header)
            crc = zlib.crc32(kind)
            left = length
            payload = b''
            while left:
                block = stream.read(min(left, 1024*1024))
                assert block
                left -= len(block)
                crc = zlib.crc32(block, crc)
                if kind == b'IHDR':
                    payload += block
                elif kind == b'IDAT':
                    while block:
                        decoded += len(inflater.decompress(block, 1024*1024))
                        block = inflater.unconsumed_tail
            assert struct.unpack('>I', stream.read(4))[0] == crc & 0xffffffff
            if first:
                assert kind == b'IHDR'
                assert struct.unpack('>IIBBBBB', payload) == (size,size,8,2,0,0,0)
                first = False
            if kind == b'IDAT':
                chunks += 1
            if kind == b'IEND':
                assert length == 0 and chunks and stream.read(1) == b''
                break
    assert inflater.eof and not inflater.unused_data
    assert decoded == (size*3+1)*size, (decoded, size)


def encode_combined(land_path, water_path, output, size):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / filename('both', size)
    temporary = destination.with_suffix('.part')
    started = time.time()
    try:
        with rasterio.Env(GDAL_CACHEMAX=128*1024*1024), \
                rasterio.open(land_path) as land, rasterio.open(water_path) as water, \
                temporary.open('wb') as raw:
            assert (land.width,land.height,land.count) == (water.width,water.height,water.count)
            assert land.count == 4 and land.width == land.height
            writer = HashWriter(raw)
            writer.write(b'\x89PNG\r\n\x1a\n')
            chunk(writer,b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))
            chunk(writer,b'tEXt',b'Software\x00SatelliteMap v4 combined')
            compressor = fast_zlib.compressobj(level=9)
            previous = np.zeros(size*3, np.uint8)
            scale = land.width/size
            last_progress = 0
            for y in range(0,size,16):
                rows = min(16,size-y)
                options = dict(window=Window(0,y*scale,land.width,rows*scale),
                               out_shape=(4,rows,size),resampling=Resampling.nearest)
                pixels = merge_pixels(land.read(**options),water.read(**options)).reshape(rows,size*3)
                for row in pixels:
                    compressed = compressor.compress(filter_row(row, previous))
                    if compressed:
                        chunk(writer,b'IDAT',compressed)
                    previous = row.copy()
                if time.time()-last_progress > 30:
                    print(f'{destination.name}: {(y+rows)/size:.0%}; {writer.size:,} bytes',flush=True)
                    last_progress = time.time()
            compressed = compressor.flush()
            if compressed:
                chunk(writer,b'IDAT',compressed)
            chunk(writer,b'IEND',b'')
            digest, length = writer.hash.hexdigest(), writer.size
        assert length < LIMIT, f'Combined PNG exceeds Release limit: {length}'
        validate_combined(temporary,size)
        temporary.replace(destination)
        info = dict(layer='both',size=size,width=size,height=size,filename=destination.name,
                    bytes=length,sha256=digest,format='PNG',mode='RGB',version='v4',
                    png_crc_verified=True,png_stream_verified=True,
                    elapsed_seconds=round(time.time()-started,2))
        destination.with_suffix('.png.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        print('VERIFIED',json.dumps(info),flush=True)
        return info
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--land',type=Path,required=True)
    parser.add_argument('--water',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('exports'))
    parser.add_argument('--size',type=int,required=True)
    args = parser.parse_args()
    assert 512 <= args.size <= 65536
    encode_combined(args.land,args.water,args.output,args.size)
