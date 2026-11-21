import json,os,time
from pathlib import Path
from github_api import api,assets,request,REPO
from library import SIZES,LAYERS,filename,RELEASE,STANDARD,THOUSANDS,asset_url
remote={a['name']:a for a in assets(int(os.environ['RELEASE_ID']))}
entries=[]
for layer in LAYERS:
    for size in SIZES:
        name=filename(layer,size);png=remote[name];meta=remote[name+'.json']
        with request(meta['url'],'application/octet-stream') as r:info=json.load(r)
        assert info['filename']==name and info['size']==size and info['layer']==layer
        assert info['width']==size and info['height']==size
        if layer=='both':assert info['mode']=='RGB' and info['png_stream_verified']
        assert info['bytes']==png['size'] and info['bytes']<2*1024**3
        assert info['png_crc_verified'] and len(info['sha256'])==64
        if png.get('digest'):assert png['digest']=='sha256:'+info['sha256']
        entries.append({'layer':layer,'size':size,'width':size,'height':size,'mode':info['mode'],'filename':name,'bytes':png['size'],'sha256':info['sha256'],'url':asset_url(layer,size),'ready':True})
catalog={'schema':1,'repository':REPO,'release':RELEASE,'version':'v4','standard':STANDARD,'thousands':THOUSANDS,'sizes':SIZES,'fileCount':len(entries),'complete':True,'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'assets':entries}
assert len(entries)==len(SIZES)*len(LAYERS)
text=json.dumps(catalog,ensure_ascii=False,indent=2)
Path('docs/catalog.json').write_text(text+'\n',encoding='utf-8')
Path('docs/catalog.js').write_text('window.ATLAS_CATALOG = '+text+';\n',encoding='utf-8')
Path('docs/SHA256SUMS.txt').write_text('\n'.join(a['sha256']+'  '+a['filename'] for a in entries)+'\n',encoding='utf-8')
print('CATALOG VERIFIED',len(entries),'PNGs',sum(a['bytes'] for a in entries),'bytes')
