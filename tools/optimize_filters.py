"""Choose lossless PNG filters by actual compressed size and reuse smaller old blocks."""
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

from encode_png import fast_zlib
from github_api import assets, download, releases, request, upload
from library import RELEASE
from strong_combined import (HELPER, MAGIC, RECORD, SHARDS, SIZES, assemble,
                             read_rgb, shard_name)


def variants(pixels,previous):
    output={name:bytearray() for name in ['avg','up','sub','paeth','none','adaptive','entropy']}
    for row in pixels:
        left=np.zeros_like(row,dtype=np.int16)
        left[3:]=row[:-3]
        above=previous.astype(np.int16)
        upper_left=np.zeros_like(above)
        upper_left[3:]=above[:-3]
        prediction=left+above-upper_left
        pa,pb,pc=np.abs(prediction-left),np.abs(prediction-above),np.abs(prediction-upper_left)
        paeth=np.where((pa<=pb)&(pa<=pc),left,np.where(pb<=pc,above,upper_left)).astype(np.uint8)
        choices=[row,row-left.astype(np.uint8),row-previous,
                 row-((left+above)//2).astype(np.uint8),row-paeth]
        for name,code in [('avg',3),('up',2),('sub',1),('paeth',4),('none',0)]:
            output[name].append(code)
            output[name].extend(choices[code].tobytes())
        score=[np.abs(value.view(np.int8).astype(np.int16)).sum() for value in choices]
        code=int(np.argmin(score))
        output['adaptive'].append(code)
        output['adaptive'].extend(choices[code].tobytes())
        entropy=[]
        for value in choices:
            frequency=np.bincount(value,minlength=256)
            frequency=frequency[frequency>0]
            entropy.append(-np.sum(frequency*np.log2(frequency)))
        code=int(np.argmin(entropy))
        output['entropy'].append(code)
        output['entropy'].extend(choices[code].tobytes())
        previous=row
    return {name:bytes(raw) for name,raw in output.items()},previous.copy()


def fast_compress(raw,final):
    compressor=fast_zlib.compressobj(9,wbits=-15,strategy=zlib.Z_FILTERED)
    payload=compressor.compress(raw)+compressor.flush(zlib.Z_FINISH if final else zlib.Z_SYNC_FLUSH)
    return len(payload)*8,len(raw),zlib.adler32(raw),payload


def best_block(options,old,final):
    encoded={name:fast_compress(raw,final) for name,raw in options.items()}
    kind=min(encoded,key=lambda name:len(encoded[name][3]))
    best=encoded[kind]
    if old:
        assert old[1]==len(options['avg']) and old[2]==zlib.adler32(options['avg'])
        if len(old[3])<=len(best[3]):
            best=old
    # Try the optimal parser only where the measured filter change can help.
    worthwhile=(kind!='avg' and len(encoded[kind][3])<len(encoded['avg'][3])*.99)
    if worthwhile and len(encoded[kind][3])>256*1024 and (not old or len(best[3])>=len(old[3])*.97):
        result=subprocess.run([HELPER,str(int(final)),'1'],input=options[kind],capture_output=True,check=True)
        bits=struct.unpack('<Q',result.stdout[:8])[0]
        payload=result.stdout[8:]
        candidate=bits,len(options[kind]),zlib.adler32(options[kind]),payload
        assert len(payload)==(bits+7)//8
        if len(payload)<len(best[3]):
            best=candidate
    return best


def metadata(remote,name):
    with request(remote[name]['url'],'application/octet-stream') as response:
        return json.load(response)


def old_records(size,index,remote):
    name=shard_name(size,index)
    if name not in remote or Path(name).with_suffix('.json').name not in remote:
        return []
    info=metadata(remote,Path(name).with_suffix('.json').name)
    path=Path('exports')/name
    download(remote[name]['url'],path)
    assert path.stat().st_size==info['bytes']
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==info['sha256']
    records=[]
    with path.open('rb') as stream:
        assert stream.read(len(MAGIC))==MAGIC
        assert struct.unpack('<III',stream.read(12))==(size,size*index//SHARDS,size*(index+1)//SHARDS)
        while header:=stream.read(RECORD.size):
            bits,length,adler,rows=RECORD.unpack(header)
            payload=stream.read((bits+7)//8)
            assert len(payload)==(bits+7)//8
            records.append((bits,length,adler,payload,rows))
    path.unlink()
    return records


def optimize(size,index,remote,upload_url):
    name='optimized-'+shard_name(size,index)
    if name in remote and Path(name).with_suffix('.json').name in remote:
        print('Optimized shard already exists:',name,flush=True)
        return
    path=Path('exports')/name
    old=old_records(size,index,remote)
    start,end=size*index//SHARDS,size*(index+1)//SHARDS
    begin=time.time()
    saved=0
    with rasterio.Env(GDAL_CACHEMAX=512*1024*1024), \
            rasterio.open('inputs/land.tif') as land,rasterio.open('inputs/water.tif') as water, \
            concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool,path.open('wb') as stream:
        stream.write(MAGIC)
        stream.write(struct.pack('<III',size,start,end))
        previous=read_rgb(land,water,size,start-1,1)[0] if start else np.zeros(size*3,np.uint8)
        pending=[]

        def finish_one():
            nonlocal saved
            future,rows,original=pending.pop(0)
            bits,length,adler,payload=future.result()
            stream.write(RECORD.pack(bits,length,adler,rows))
            stream.write(payload)
            if original:
                saved+=len(original[3])-len(payload)

        for block,y in enumerate(range(start,end,32)):
            rows=min(32,end-y)
            options,previous=variants(read_rgb(land,water,size,y,rows),previous)
            original=old[block][:4] if old else None
            if old:
                assert old[block][4]==rows
            pending.append((pool.submit(best_block,options,original,y+rows==size),rows,original))
            if len(pending)>=4:
                finish_one()
            if (y-start)%512==0:
                print(f'Filters {size} shard {index}: {y-start}/{end-start}; saved {saved:,} bytes',flush=True)
        while pending:
            finish_one()
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    info=dict(size=size,index=index,start=start,end=end,bytes=path.stat().st_size,
              sha256=digest,savedBytes=saved,compression='adaptive lossless filters')
    manifest=path.with_suffix('.json')
    manifest.write_text(json.dumps(info),encoding='utf-8')
    result=upload(upload_url,path,'application/octet-stream')
    assert result['size']==info['bytes']
    if result.get('digest'):
        assert result['digest']=='sha256:'+digest
    upload(upload_url,manifest,'application/json')
    path.unlink()
    manifest.unlink()
    print('FILTER SHARD VERIFIED',json.dumps(info),round(time.time()-begin,1),'seconds',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['shard','assemble'])
    args=parser.parse_args()
    stage_id=int(os.environ['STAGING_ID'])
    remote={a['name']:a for a in assets(stage_id)}
    if args.operation=='shard':
        Path('inputs').mkdir(exist_ok=True)
        Path('exports').mkdir(exist_ok=True)
        for layer in ['land','water']:
            download(os.environ[layer.upper()+'_SOURCE_URL'],Path(f'inputs/{layer}.tif'))
        for size in SIZES:
            optimize(size,int(os.environ['SHARD_INDEX']),remote,os.environ['UPLOAD_URL'])
    else:
        destination=next(r for r in releases() if r['tag_name']==RELEASE)
        for size in SIZES:
            selected={}
            for index in range(SHARDS):
                name=shard_name(size,index)
                optimized='optimized-'+name
                original_meta=Path(name).with_suffix('.json').name
                optimized_meta=Path(optimized).with_suffix('.json').name
                if optimized in remote and optimized_meta in remote and (name not in remote or remote[optimized]['size']<=remote[name]['size']):
                    selected[name]=remote[optimized]
                    selected[original_meta]=remote[optimized_meta]
                else:
                    selected[name]=remote[name]
                    selected[original_meta]=remote[original_meta]
            assemble(size,selected,destination['upload_url'],'Adaptive PNG filters + Zopfli/zlib-ng (lossless)')
