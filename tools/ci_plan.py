import json,os
from github_api import releases,assets
from library import SOURCE_RELEASE,RELEASE,SIZES,LAYERS,filename
r=releases();source=next(x for x in r if x['tag_name']==SOURCE_RELEASE);dest=next(x for x in r if x['tag_name']==RELEASE)
source_assets=assets(source['id']);existing={a['name'] for a in assets(dest['id'])}
matrix=[]
for layer in LAYERS:
    missing=[n for n in SIZES if filename(layer,n) not in existing or filename(layer,n)+'.json' not in existing]
    buckets=[[] for _ in range(min(8,len(missing)))];weights=[0]*len(buckets)
    for n in reversed(missing):
        i=min(range(len(buckets)),key=weights.__getitem__);buckets[i].append(n);weights[i]+=n*n
    matrix += [{'layer':layer,'bucket':i+1,'sizes':b} for i,b in enumerate(buckets)]
if not matrix:matrix=[{'layer':'land','bucket':0,'sizes':[]}]
outputs={'matrix':json.dumps({'include':matrix},separators=(',',':')),'upload_url':dest['upload_url'],'release_id':str(dest['id'])}
for layer,title in LAYERS.items():outputs[layer+'_source']=next(a['url'] for a in source_assets if a['name']==f'{title}_separated_64k_v4.tif')
with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
    for k,v in outputs.items():f.write(f'{k}={v}\n')
print('Build groups:',len(matrix),'PNG files:',sum(len(x['sizes']) for x in matrix))
