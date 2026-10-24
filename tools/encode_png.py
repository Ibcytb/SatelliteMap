"""Bounded-memory, lossless RGBA PNG writing at up to 65536 square."""
import argparse, hashlib, json, os, struct, time, zlib
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
try:
    from zlib_ng import zlib_ng as fast_zlib
except ImportError:
    fast_zlib=zlib
from library import filename,SIZES
LIMIT=2*1024**3

class HashWriter:
    def __init__(self,f):self.f=f;self.hash=hashlib.sha256();self.size=0
    def write(self,data):self.f.write(data);self.hash.update(data);self.size+=len(data)

def chunk(f,kind,data):
    f.write(struct.pack('>I',len(data)));f.write(kind);f.write(data)
    f.write(struct.pack('>I',zlib.crc32(data,zlib.crc32(kind))&0xffffffff))

def validate_png(path,size):
    with path.open('rb') as f:
        assert f.read(8)==b'\x89PNG\r\n\x1a\n'
        first=True;count=0
        while True:
            head=f.read(8);assert len(head)==8
            length,kind=struct.unpack('>I4s',head)
            crc=zlib.crc32(kind);left=length
            data=b''
            while left:
                part=f.read(min(left,1024*1024));assert part
                if kind==b'IHDR':data+=part
                crc=zlib.crc32(part,crc);left-=len(part)
            actual=struct.unpack('>I',f.read(4))[0];assert actual==crc&0xffffffff
            if first:
                assert kind==b'IHDR' and struct.unpack('>IIBBBBB',data)==(size,size,8,6,0,0,0)
                first=False
            if kind==b'IDAT':count+=1
            if kind==b'IEND':assert length==0 and count>0 and f.read(1)==b'';break

def encode(source,output,size,layer):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dest=output/filename(layer,size);part=dest.with_suffix('.part')
    started=time.time()
    try:
        for level in [6,9]:
            with rasterio.Env(GDAL_CACHEMAX=128*1024*1024),rasterio.open(source) as src,part.open('wb') as raw:
                assert (src.width,src.height,src.count)==(65536,65536,4)
                f=HashWriter(raw);f.write(b'\x89PNG\r\n\x1a\n')
                chunk(f,b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
                chunk(f,b'tEXt',b'Software\x00SatelliteMap v4')
                compressor=fast_zlib.compressobj(level=level)
                previous=np.zeros(size*4,np.uint8);scale=65536/size;last=0
                for y in range(0,size,32):
                    rows=min(32,size-y)
                    bands=src.read(window=Window(0,y*scale,65536,rows*scale),out_shape=(4,rows,size),resampling=Resampling.nearest)
                    pixels=np.ascontiguousarray(bands.transpose(1,2,0)).reshape(rows,size*4)
                    for row in pixels:
                        up=np.subtract(row,previous,dtype=np.uint8)
                        sub=row.copy();sub[4:]=np.subtract(row[4:],row[:-4],dtype=np.uint8)
                        # Choose a legal lossless PNG filter using a fixed sample.
                        up_score=np.abs(up.view(np.int8)[::32].astype(np.int16)).sum()
                        sub_score=np.abs(sub.view(np.int8)[::32].astype(np.int16)).sum()
                        code,filtered=(1,sub) if sub_score<up_score else (2,up)
                        data=compressor.compress(bytes([code])+filtered.tobytes())
                        if data:chunk(f,b'IDAT',data)
                        previous=row.copy()
                    if time.time()-last>20:
                        print(f'{dest.name}: {(y+rows)/size:.0%}; {f.size:,} bytes',flush=True);last=time.time()
                data=compressor.flush()
                if data:chunk(f,b'IDAT',data)
                chunk(f,b'IEND',b'')
                digest=f.hash.hexdigest();length=f.size
            if length<LIMIT:break
            print('Retrying with maximum compression to satisfy the Release asset limit',flush=True)
        assert length<LIMIT,f'PNG exceeds GitHub Release 2 GiB limit: {length}'
        validate_png(part,size)
        part.replace(dest)
        info={'layer':layer,'size':size,'width':size,'height':size,'filename':dest.name,
              'bytes':length,'sha256':digest,'format':'PNG','mode':'RGBA','version':'v4',
              'png_crc_verified':True,'elapsed_seconds':round(time.time()-started,2)}
        dest.with_suffix('.png.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        print('VERIFIED',json.dumps(info),flush=True)
        return info
    finally:
        if part.exists():part.unlink()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('exports'));p.add_argument('--layer',choices=['land','water'],required=True)
    p.add_argument('--size',type=int,required=True);a=p.parse_args()
    assert 512<=a.size<=65536
    encode(a.source,a.output,a.size,a.layer)
