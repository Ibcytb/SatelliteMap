"""Independently verify the public PNG header, dimensions and byte size of every link."""
import argparse
import concurrent.futures
import json
import struct
import time
import urllib.request
import zlib
from pathlib import Path


def verify(entry):
    for attempt in range(4):
        try:
            request = urllib.request.Request(entry['url'],headers={
                'User-Agent':'SatelliteMap-download-verification',
                'Range':'bytes=0-32','Accept-Encoding':'identity'})
            with urllib.request.urlopen(request,timeout=60) as response:
                header = response.read(33)
                total = response.headers.get('Content-Range','').split('/')[-1]
                if not total.isdigit():
                    total = response.headers.get('Content-Length','')
                assert total.isdigit() and int(total)==entry['bytes'], (entry['filename'],total)
                assert header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR'
                width,height,depth,colour,compression,filtering,interlace = struct.unpack('>IIBBBBB',header[16:29])
                assert (width,height)==(entry['size'],entry['size'])
                assert (depth,colour,compression,filtering,interlace)==(8,2 if entry['layer']=='both' else 6,0,0,0)
                assert zlib.crc32(header[12:29]) & 0xffffffff == struct.unpack('>I',header[29:33])[0]
            return dict(filename=entry['filename'],layer=entry['layer'],size=entry['size'],
                        width=width,height=height,bytes=int(total),verified=True,
                        catalogSha256=entry['sha256'],url=entry['url'])
        except Exception:
            if attempt==3:
                raise
            time.sleep(2**attempt)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--catalog',type=Path,default=Path('docs/catalog.json'))
    parser.add_argument('--output',type=Path,default=Path('tools/download_validation.json'))
    parser.add_argument('--reuse',type=Path)
    args=parser.parse_args()
    catalog=json.loads(args.catalog.read_text(encoding='utf-8'))
    previous={}
    if args.reuse and args.reuse.exists():
        cached=json.loads(args.reuse.read_text(encoding='utf-8'))
        if cached.get('verifierSchema')==2:
            previous={entry['filename']:entry for entry in cached['files']}
    results=[]
    pending=[]
    for entry in catalog['assets']:
        saved=previous.get(entry['filename'],{})
        if (saved.get('verified') and saved.get('layer')==entry['layer'] and saved.get('size')==entry['size'] and
                saved.get('catalogSha256')==entry['sha256'] and
                saved.get('url')==entry['url'] and saved.get('bytes')==entry['bytes'] and
                saved.get('width')==entry['size'] and saved.get('height')==entry['size']):
            results.append(saved)
        else:
            pending.append(entry)
    print('Previously verified, unchanged files:',len(results),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(verify,entry) for entry in pending]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            if len(results)%24==0:
                print(f'Public downloads verified: {len(results)}/{len(catalog["assets"])}',flush=True)
    results.sort(key=lambda item:(item['layer'],item['size']))
    report=dict(verifierSchema=2,verifiedAt=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                complete=len(results)==len(catalog['assets']),count=len(results),
                totalBytes=sum(entry['bytes'] for entry in results),files=results)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('VERIFIED',report['count'],'public PNGs;',report['totalBytes'],'bytes',flush=True)
