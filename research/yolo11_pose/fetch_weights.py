"""Fetch official checkpoints with a local SHA256 manifest; no service changes."""
import hashlib,json,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'downloads/reference-assets/yolo11-pose'


def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for size in ('n','s'):
        name=f'yolo11{size}-pose.pt';target=OUT/name
        url=f'https://github.com/ultralytics/assets/releases/download/v8.3.0/{name}'
        if not target.exists():
            temporary=target.with_suffix('.pt.part')
            with urllib.request.urlopen(url,timeout=60) as source,temporary.open('wb') as dest:
                while chunk:=source.read(1024*1024):dest.write(chunk)
            temporary.replace(target)
        rows.append({'file':name,'url':url,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        print(name,target.stat().st_size,flush=True)
    (OUT/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')


if __name__=='__main__':main()
