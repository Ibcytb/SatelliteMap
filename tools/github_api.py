"""Small GitHub API client; tokens stay in process environment."""
import http.client,json,os,time,urllib.parse,urllib.request
TOKEN=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
REPO=os.environ.get('GITHUB_REPOSITORY','Ibcytb/SatelliteMap')

def request(url,accept='application/vnd.github+json'):
    if url.startswith('/') :url='https://api.github.com'+url
    headers={'User-Agent':'SatelliteMap-library','Accept':accept,'X-GitHub-Api-Version':'2022-11-28'}
    if TOKEN:headers['Authorization']='Bearer '+TOKEN
    for attempt in range(4):
        try:return urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=180)
        except Exception:
            if attempt==3:raise
            time.sleep(2**(attempt+1))

def api(path):
    with request(path) as r:return json.load(r)

def releases():return api(f'/repos/{REPO}/releases?per_page=100')

def assets(release_id):
    result=[]
    for page in range(1,20):
        batch=api(f'/repos/{REPO}/releases/{release_id}/assets?per_page=100&page={page}');result+=batch
        if len(batch)<100:break
    return result

def download(url,path):
    import shutil
    with request(url,'application/octet-stream') as r,open(path,'wb') as f:shutil.copyfileobj(r,f,1024*1024)

def upload(upload_url,path,content_type):
    from pathlib import Path
    path=Path(path);url=urllib.parse.urlsplit(upload_url.split('{')[0]+'?name='+urllib.parse.quote(path.name))
    assert url.hostname=='uploads.github.com'
    for attempt in range(4):
        conn=http.client.HTTPSConnection(url.hostname,timeout=300)
        try:
            conn.putrequest('POST',url.path+'?'+url.query)
            for k,v in {'Authorization':'Bearer '+TOKEN,'User-Agent':'SatelliteMap-library','Content-Type':content_type,'Content-Length':str(path.stat().st_size)}.items():conn.putheader(k,v)
            conn.endheaders()
            with path.open('rb') as f:
                while block:=f.read(1024*1024):conn.send(block)
            response=conn.getresponse();body=response.read();status=response.status
            if status==201:return json.loads(body)
            if status==422:
                release_id=int(url.path.split('/')[-2])
                matches=[a for a in assets(release_id) if a['name']==path.name and a['size']==path.stat().st_size]
                if matches:return matches[0]
            raise RuntimeError(f'GitHub upload failed: HTTP {status}, {body[:200]!r}')
        except Exception:
            if attempt==3:raise
            time.sleep(2**(attempt+1))
        finally:conn.close()
