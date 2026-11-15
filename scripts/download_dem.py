"""Download HTTP riprendibile a blocchi con controllo Content-Range."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import urllib.request

url, destination = sys.argv[1:3]
path=Path(destination).resolve();path.parent.mkdir(parents=True,exist_ok=True)
part=path.with_suffix(path.suffix+'.part');checkpoint=path.with_suffix(path.suffix+'.download.json')
with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=60) as response:
    total=int(response.headers['Content-Length']);modified=response.headers.get('Last-Modified')
if path.exists():
    if path.stat().st_size != total:raise ValueError('File finale di dimensione inattesa')
    print('File gia completo:',path,flush=True);sys.exit(0)
block=16*1024*1024
if checkpoint.exists():
    state=json.loads(checkpoint.read_text());assert state['url']==url and state['total_bytes']==total
    completed=set(state['completed_blocks'])
else:
    prefix=part.stat().st_size if part.exists() else 0
    assert prefix <= total
    completed=set(range(prefix//block))
    state={'url':url,'total_bytes':total,'last_modified':modified,'block_bytes':block}
    if shutil.disk_usage(path.parent).free < total-prefix+256*1024*1024:raise OSError('Spazio disco insufficiente')
    with part.open('ab') as target:target.truncate(total)
def persist():
    state['completed_blocks']=sorted(completed)
    temp=checkpoint.with_suffix(checkpoint.suffix+'.tmp')
    temp.write_text(json.dumps(state,indent=2),encoding='utf-8');temp.replace(checkpoint)
persist()
def fetch(index):
    start=index*block;end=min(total,start+block)-1
    for attempt in range(4):
        try:
            request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
            with urllib.request.urlopen(request,timeout=120) as response:
                assert response.status==206 and response.headers.get('Content-Range')==f'bytes {start}-{end}/{total}'
                data=response.read(end-start+2)
                assert len(data)==end-start+1,'Blocco incompleto'
            with part.open('r+b') as target:target.seek(start);target.write(data)
            return index
        except Exception:
            if attempt==3:raise
            time.sleep(attempt+1)
indices=[i for i in range((total+block-1)//block) if i not in completed]
print(f'Download: {path.name}, {total/1e9:.2f} GB, {len(indices)} blocchi mancanti',flush=True)
started=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for future in concurrent.futures.as_completed([pool.submit(fetch,i) for i in indices]):
        completed.add(future.result());persist()
        done=sum(min(block,total-i*block) for i in completed)
        print(f'{path.name}: {100*done/total:.1f}% ({done/1e6:.0f}/{total/1e6:.0f} MB)',flush=True)
assert len(completed)==(total+block-1)//block
part.replace(path)
digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
state.update({'sha256':digest,'download_complete':True,'elapsed_seconds':time.monotonic()-started})
checkpoint.write_text(json.dumps(state,indent=2),encoding='utf-8')
print('Completato:',path,flush=True)
