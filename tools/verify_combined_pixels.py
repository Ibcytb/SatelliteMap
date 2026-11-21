"""Check public combined downloads against the corresponding individual maps."""
import hashlib
import io
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image


def verify(catalog, size):
    images = {}
    digests = {}
    for layer in ['land','water','both']:
        entry = next(a for a in catalog['assets'] if a['layer']==layer and a['size']==size)
        with urllib.request.urlopen(urllib.request.Request(entry['url'],headers={
                'User-Agent':'SatelliteMap-pixel-verification'}),timeout=120) as response:
            content = response.read()
        assert len(content)==entry['bytes']
        assert hashlib.sha256(content).hexdigest()==entry['sha256']
        digests[layer] = entry['sha256']
        images[layer] = Image.open(io.BytesIO(content))
        assert images[layer].size==(size,size)
    land,water,combined = (images[layer] for layer in ['land','water','both'])
    land_alpha = np.asarray(land.getchannel('A')).astype(np.uint16)
    water_alpha = np.asarray(water.getchannel('A')).astype(np.uint16)
    # TIFF overview rounding can make the two alphas total 256 instead of 255.
    # Independently composite with floating-point weights and round to RGB8.
    total = (land_alpha+water_alpha).astype(np.float64)
    assert np.all(total>0), 'The source maps must cover the whole image.'
    numerator = (np.asarray(land.convert('RGB'),dtype=np.float64)*land_alpha[...,None] +
                 np.asarray(water.convert('RGB'),dtype=np.float64)*water_alpha[...,None])
    expected = np.floor(numerator/total[...,None]+.5).astype(np.uint8)
    assert combined.mode=='RGB'
    np.testing.assert_array_equal(np.asarray(combined),expected)
    print(f'{size} × {size}: all pixels and all three SHA-256 hashes match',flush=True)
    return dict(size=size,width=size,height=size,allPixelsMatch=True,sha256Verified=True,sha256=digests)


if __name__=='__main__':
    catalog=json.loads(Path('docs/catalog.json').read_text(encoding='utf-8'))
    report=dict(verifiedAt=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                files=[verify(catalog,size) for size in [512,1000,1536]])
    Path('tools/combined_pixel_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
