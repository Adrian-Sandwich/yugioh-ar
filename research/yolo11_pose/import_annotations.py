"""Validate reviewed real annotations and build a separate dataset by session."""
import argparse,hashlib,json,shutil
from pathlib import Path
import cv2,numpy as np


def collect(folder):
    records=[];sessions={};images={}
    for path in sorted(Path(folder).glob('*.pose.json')):
        r=json.loads(path.read_text(encoding='utf-8'))
        if r.get('reviewed') is not True or r.get('exhaustive') is not True:raise ValueError(f'Incomplete/unreviewed scene: {path}')
        if r.get('corner_order')!=['TL','TR','BR','BL']:raise ValueError('Unknown corner convention')
        if r.get('split') not in ('train','val','test') or not r.get('session'):raise ValueError('Missing session/split')
        if sessions.setdefault(r['session'],r['split'])!=r['split']:raise ValueError('Session leaks across splits')
        name=r['image']
        if Path(name).name!=name:raise ValueError('Images must be next to their annotation files')
        source=path.parent/name;sha=hashlib.sha256(source.read_bytes()).hexdigest()
        if sha!=r['image_sha256']:raise ValueError('Original image hash mismatch')
        if sha in images:raise ValueError('Duplicate image; resolve annotations before import')
        images[sha]=r['split']
        im=cv2.imread(str(source))
        if im is None:raise ValueError('Unreadable image')
        h,w=im.shape[:2]
        if (r['width'],r['height'])!=(w,h):raise ValueError('Image dimensions changed')
        labels=[]
        for obj in r['objects']:
            p=np.float32(obj['corners'])
            if p.shape!=(4,2) or not np.isfinite(p).all() or not cv2.isContourConvex(p) or cv2.contourArea(p,oriented=True)<100:raise ValueError('Invalid corner polygon/order')
            if (p<0).any() or (p[:,0]>=w).any() or (p[:,1]>=h).any():raise ValueError('Out-of-frame point; use future occlusion workflow')
            if obj.get('visibility')!=[2,2,2,2]:raise ValueError('This importer currently requires four observed corners')
            normalized=p/[w,h];lo=normalized.min(0);hi=normalized.max(0)
            keypoints=np.column_stack((normalized,np.full(4,2)))
            labels.append(' '.join(map(str,[0,*((lo+hi)/2),*(hi-lo),*keypoints.flatten()])))
        records.append((r,source,labels))
    if not records:raise ValueError('No .pose.json annotations found')
    return records


def build(folder,output):
    records=collect(folder);output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be new or empty')
    rows=[]
    for r,source,labels in records:
        split=r['split'];name=r['image_sha256']+source.suffix.lower()
        (output/'images'/split).mkdir(parents=True,exist_ok=True);(output/'labels'/split).mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,output/'images'/split/name)
        (output/'labels'/split/(Path(name).stem+'.txt')).write_text('\n'.join(labels)+'\n',encoding='utf-8')
        rows.append({**r,'source_name':r['image'],'image':f'images/{split}/{name}','synthetic':False})
    (output/'manifest.json').write_text(json.dumps({'version':1,'records':rows},indent=2),encoding='utf-8')
    (output/'dataset.yaml').write_text('path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames: [card]\nkpt_shape: [4, 3]\nflip_idx: [0, 1, 2, 3]\n',encoding='utf-8')
    return {'images':len(rows),'train_ready':all(any(r['split']==s for r in rows) for s in ('train','val'))}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    print(json.dumps(build(a.folder,a.output)))
