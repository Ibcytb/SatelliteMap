"""Parallel lossless compression for PNGs which exceed a Release asset's limit.

Temporary shards live in a private draft Release. The published result remains
one standard PNG with one zlib stream; no browser-side assembly is required.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import struct
import subprocess
import time
import zlib
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

from encode_combined import merge_pixels, validate_combined
from encode_png import HashWriter, chunk, LIMIT
from github_api import api, assets, download, releases, upload, request
from library import LAYERS, RELEASE, SOURCE_RELEASE, filename

MAGIC = b'SMDEFLATE1\n'
RECORD = struct.Struct('<QQII')  # meaningful bits, raw length, Adler-32, rows
SHARDS = 16
SIZES = [64000, 65536]
HELPER = str(Path('tools/zopfli-block').resolve())


def compress_block(raw, final):
    process = subprocess.run([HELPER, str(int(final))], input=raw, capture_output=True, check=True)
    bits = struct.unpack('<Q', process.stdout[:8])[0]
    payload = process.stdout[8:]
    assert len(payload) == (bits+7)//8
    return bits, len(raw), zlib.adler32(raw), payload


class BitJoiner:
    """Join exact DEFLATE bits, preserving partial bytes across shard boundaries."""
    def __init__(self):
        self.pending = 0
        self.used = 0

    def append(self, data, bits):
        assert 0 < bits <= len(data)*8
        source = np.frombuffer(data,dtype=np.uint8).astype(np.uint16)
        if bits % 8:
            source[-1] &= (1 << (bits % 8))-1
        output = np.zeros(len(source)+1,np.uint16)
        output[0] = self.pending
        output[:-1] |= source << self.used
        if self.used:
            output[1:] |= source >> (8-self.used)
        complete, self.used = divmod(bits+self.used,8)
        self.pending = int(output[complete]) & ((1 << self.used)-1) if self.used else 0
        return output[:complete].astype(np.uint8).tobytes()

    def finish(self):
        return bytes([self.pending]) if self.used else b''


def combine_adler(first, second, length):
    a, b = first & 65535, first >> 16
    c, d = second & 65535, second >> 16
    return (((b+d+(length % 65521)*(a-1)) % 65521) << 16) | ((a+c-1) % 65521)


def self_test():
    raw = bytes(range(256))*20 + b'\0'*4097
    pieces = [raw[:37],raw[37:1444],raw[1444:8191],raw[8191:]]
    joiner = BitJoiner()
    stream = bytearray(b'\x78\xda')
    checksum = 1
    for index,piece in enumerate(pieces):
        bits,length,adler,payload = compress_block(piece,index==len(pieces)-1)
        stream.extend(joiner.append(payload,bits))
        checksum = combine_adler(checksum,adler,length)
    stream.extend(joiner.finish())
    stream.extend(struct.pack('>I',checksum))
    assert checksum == zlib.adler32(raw)
    assert zlib.decompress(stream) == raw
    print('Raw DEFLATE boundaries and combined Adler-32 verified',flush=True)


def read_rgb(land,water,size,start,count):
    scale = land.width/size
    options = dict(window=Window(0,start*scale,land.width,count*scale),
                   out_shape=(4,count,size),resampling=Resampling.nearest)
    return merge_pixels(land.read(**options),water.read(**options)).reshape(count,size*3)


def average_rows(pixels,previous):
    result = bytearray()
    for row in pixels:
        left = np.zeros_like(row,dtype=np.uint16)
        left[3:] = row[:-3]
        left += previous
        result.append(3)
        result.extend((row-(left//2).astype(np.uint8)).tobytes())
        previous = row
    return bytes(result),previous.copy()


def shard_name(size,index):
    return f'combined-{size}-shard-{index:02}.deflate'


def build_shard(size,index,upload_url):
    path = Path('exports')/shard_name(size,index)
    path.parent.mkdir(exist_ok=True)
    start,end = size*index//SHARDS,size*(index+1)//SHARDS
    begin = time.time()
    with rasterio.Env(GDAL_CACHEMAX=128*1024*1024), \
            rasterio.open('inputs/land.tif') as land, rasterio.open('inputs/water.tif') as water, \
            concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool, path.open('wb') as output:
        output.write(MAGIC)
        output.write(struct.pack('<III',size,start,end))
        previous = read_rgb(land,water,size,start-1,1)[0] if start else np.zeros(size*3,np.uint8)
        pending = []

        def finish_one():
            future,rows = pending.pop(0)
            bits,length,adler,payload = future.result()
            output.write(RECORD.pack(bits,length,adler,rows))
            output.write(payload)

        for y in range(start,end,32):
            rows = min(32,end-y)
            raw,previous = average_rows(read_rgb(land,water,size,y,rows),previous)
            pending.append((pool.submit(compress_block,raw,y+rows==size),rows))
            if len(pending)>=4:
                finish_one()
            if (y-start) % 512 == 0:
                print(f'{size} shard {index}: {y-start}/{end-start} rows submitted',flush=True)
        while pending:
            finish_one()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    info = dict(size=size,index=index,start=start,end=end,bytes=path.stat().st_size,sha256=digest)
    metadata = path.with_suffix('.json')
    metadata.write_text(json.dumps(info),encoding='utf-8')
    remote = upload(upload_url,path,'application/octet-stream')
    assert remote['size']==info['bytes']
    if remote.get('digest'):
        assert remote['digest']=='sha256:'+digest
    upload(upload_url,metadata,'application/json')
    path.unlink()
    metadata.unlink()
    print('SHARD UPLOADED',size,index,round(time.time()-begin,1),'seconds',flush=True)


def assemble(size,remote,upload_url,compression='Zopfli (lossless)'):
    begin = time.time()
    output = Path('exports')
    output.mkdir(exist_ok=True)
    destination = output/filename('both',size)
    joiner = BitJoiner()
    checksum,total_rows,raw_bytes = 1,0,0
    with destination.open('wb') as raw:
        writer = HashWriter(raw)
        writer.write(b'\x89PNG\r\n\x1a\n')
        chunk(writer,b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))
        chunk(writer,b'IDAT',b'\x78\xda')
        for index in range(SHARDS):
            part = output/shard_name(size,index)
            with request(remote[part.with_suffix('.json').name]['url'],'application/octet-stream') as response:
                info = json.load(response)
            download(remote[part.name]['url'],part)
            assert info['size']==size and info['index']==index and info['bytes']==part.stat().st_size
            with part.open('rb') as verify:
                assert hashlib.file_digest(verify,'sha256').hexdigest()==info['sha256']
            with part.open('rb') as stream:
                assert stream.read(len(MAGIC))==MAGIC
                dimensions,start,end = struct.unpack('<III',stream.read(12))
                assert dimensions==size and start==total_rows
                shard_rows = 0
                while header:=stream.read(RECORD.size):
                    assert len(header)==RECORD.size
                    bits,length,adler,rows = RECORD.unpack(header)
                    assert length==(size*3+1)*rows
                    payload = stream.read((bits+7)//8)
                    assert len(payload)==(bits+7)//8
                    data = joiner.append(payload,bits)
                    if data:
                        chunk(writer,b'IDAT',data)
                    checksum = combine_adler(checksum,adler,length)
                    shard_rows += rows
                    raw_bytes += length
                assert shard_rows==end-start
                total_rows = end
            part.unlink()
            print(f'Assembled {size}: {index+1}/{SHARDS} shards; {writer.size:,} bytes',flush=True)
        tail = joiner.finish()+struct.pack('>I',checksum)
        chunk(writer,b'IDAT',tail)
        chunk(writer,b'IEND',b'')
        digest,length = writer.hash.hexdigest(),writer.size
    assert total_rows==size and raw_bytes==(size*3+1)*size
    assert length<LIMIT,f'Optimized PNG is still too large: {length}'
    validate_combined(destination,size)
    info = dict(layer='both',size=size,width=size,height=size,filename=destination.name,
                bytes=length,sha256=digest,format='PNG',mode='RGB',version='v4',
                png_crc_verified=True,png_stream_verified=True,
                compression=compression,elapsed_seconds=round(time.time()-begin,2))
    metadata = destination.with_suffix('.png.json')
    metadata.write_text(json.dumps(info,indent=2),encoding='utf-8')
    published = upload(upload_url,destination,'image/png')
    assert published['size']==length
    if published.get('digest'):
        assert published['digest']=='sha256:'+digest
    upload(upload_url,metadata,'application/json')
    destination.unlink()
    metadata.unlink()
    print('OPTIMIZED PNG VERIFIED AND PUBLISHED',json.dumps(info),flush=True)


def plan():
    all_releases = releases()
    source = next(r for r in all_releases if r['tag_name']==SOURCE_RELEASE)
    source_assets = {a['name']:a for a in assets(source['id'])}
    staging = api(f'/repos/{os.environ["GITHUB_REPOSITORY"]}/releases/{os.environ["STAGING_ID"]}')
    result = dict(matrix=json.dumps({'index':list(range(SHARDS))}),upload_url=staging['upload_url'])
    for layer in ['land','water']:
        result[layer+'_source'] = source_assets[f'{LAYERS[layer]}_separated_64k_v4.tif']['url']
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:
        for key,value in result.items():
            stream.write(f'{key}={value}\n')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation',choices=['self-test','plan','shard','assemble'])
    args = parser.parse_args()
    if args.operation=='self-test':
        self_test()
    elif args.operation=='plan':
        plan()
    elif args.operation=='shard':
        Path('inputs').mkdir(exist_ok=True)
        for layer in ['land','water']:
            download(os.environ[layer.upper()+'_SOURCE_URL'],Path(f'inputs/{layer}.tif'))
        for size in SIZES:
            build_shard(size,int(os.environ['SHARD_INDEX']),os.environ['UPLOAD_URL'])
    else:
        remote = {a['name']:a for a in assets(int(os.environ['STAGING_ID']))}
        destination = next(r for r in releases() if r['tag_name']==RELEASE)
        for size in SIZES:
            assemble(size,remote,destination['upload_url'])
