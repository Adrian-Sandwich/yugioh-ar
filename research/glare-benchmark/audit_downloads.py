"""Record source revisions and file hashes, inspect checkpoints without executing pickle globals."""
import hashlib,json,subprocess
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
report={'repositories':{},'weights':[]}
for name in ('DocSHRNet','SHDocs','UnReflectAnything'):
    report['repositories'][name]=subprocess.check_output(['git','-C',str(ROOT/'repos'/name),'rev-parse','HEAD'],text=True).strip()
hf=json.loads((OUT/'unreflect-files.json').read_text())
for name in ('docshrnet.pth','mimo-shdocs.pkl','unreflect-full.pt'):
    path=ROOT/'downloads/glare-models'/name
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    row={'file':name,'bytes':path.stat().st_size,'sha256':digest,
         'pickle_globals':torch.serialization.get_unsafe_globals_in_checkpoint(path)}
    if name=='unreflect-full.pt':
        remote=next(x for x in hf if x['path']=='weights/full_model_weights.pt')
        row['remote_lfs_sha256']=remote.get('lfs',{}).get('oid')
        row['matches_remote']=digest==row['remote_lfs_sha256']
        assert row['matches_remote'], 'UnReflectAnything checksum mismatch'
    report['weights'].append(row)
(OUT/'downloads.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
