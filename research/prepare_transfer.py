"""Create coherent SQLite backups and a source manifest while the crawler runs."""
import hashlib,json,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def source_manifest():
    files=set(ROOT.glob('*.py'))|set(ROOT.glob('*.ps1'))|set(ROOT.glob('*.txt'))|set(ROOT.glob('*.md'))
    for folder in ('web','research'):
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.ps1','.md','.html','.js','.yaml','.toml') and 'runs' not in p.parts)
    return [{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    out=ROOT/'transfer'/stamp;out.mkdir(parents=True,exist_ok=False)
    backups=[]
    for relative in ('data/registry/registry.sqlite','data/catalog/catalog.sqlite','data/catalog/reviews.sqlite'):
        source=ROOT/relative
        if not source.exists():continue
        target=out/relative;target.parent.mkdir(parents=True,exist_ok=True)
        start=time.monotonic()
        def check(status,remaining,total):
            if time.monotonic()-start>180:raise TimeoutError('Backup exceeded 180 seconds; incomplete destination, do not restore')
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
            src.backup(dst,pages=1024,progress=check,sleep=.1)
            result=dst.execute('PRAGMA quick_check').fetchone()[0]
            if result!='ok':raise ValueError(result)
        with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        backups.append({'path':relative,'bytes':target.stat().st_size,'sha256':digest,'quick_check':result})
        print('SQLite backup OK:',relative,flush=True)
    code=source_manifest()
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'sqlite_backups':backups,'source_hashes':code,
        'copy_directories':['data','downloads','repos','research','web'],
        'exclude':['.venv*','.runtime','__pycache__','tmp*','*.sqlite-wal','*.sqlite-shm'],
        'instructions':'Copy project assets preserving relative paths; replace database files in destination with these backups BEFORE starting services. Do not overwrite source databases. This directory is not a full project archive.',
        'consistency':'Each SQLite backup is internally coherent. The three databases and growing Neuron file cache are not one atomic snapshot.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (out/'neuron-progress.json').write_bytes((ROOT/'data/registry/neuron/progress.json').read_bytes())
    print(json.dumps({'transfer':str(out),'backups':len(backups),'source_files':len(code)}))


if __name__=='__main__':main()
