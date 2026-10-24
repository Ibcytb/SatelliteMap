import hashlib,json,os
from pathlib import Path
from encode_png import encode
from github_api import download,upload
sizes=json.loads(os.environ['SIZES']);layer=os.environ['LAYER']
if not sizes:print('All PNG assets already exist');raise SystemExit(0)
source=Path('inputs/source.tif');source.parent.mkdir(exist_ok=True)
download(os.environ['SOURCE_URL'],source)
for n in sizes:
    info=encode(source,Path('exports'),n,layer)
    path=Path('exports')/info['filename']
    asset=upload(os.environ['UPLOAD_URL'],path,'image/png')
    assert asset['size']==info['bytes']
    if asset.get('digest'):assert asset['digest']=='sha256:'+info['sha256']
    metadata=path.with_suffix('.png.json');upload(os.environ['UPLOAD_URL'],metadata,'application/json')
    print(f'UPLOADED {info["filename"]}: {info["bytes"]:,} bytes SHA256 {info["sha256"]}',flush=True)
    # Verified Release assets are durable; reclaim this ephemeral runner's disk.
    path.unlink();metadata.unlink()
