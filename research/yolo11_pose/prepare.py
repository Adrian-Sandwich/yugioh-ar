"""Reproducible synthetic bootstrap; never promotes inferred real corners to labels."""
import argparse,hashlib,json,math
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/'data/pose/bootstrap-v1'
ORDER=['top_left','top_right','bottom_right','bottom_left']


def asset_split(uid):
    return 'val' if int(hashlib.sha256(uid.encode()).hexdigest()[:8],16)%5==0 else 'train'


def generate(entries,rng,index,size=640):
    base=rng.uniform(60,205,size=3)
    noise=rng.normal(0,5,(size,size,1))
    canvas=np.uint8(np.clip(base+noise,0,255));owner=np.full((size,size),-1,np.int16)
    instances=[]
    for n in range(int(rng.integers(1,4))):
        entry=entries[int(rng.integers(len(entries)))];card=cv2.imread(str(entry['path']))
        width=rng.uniform(140,235);height=width*88/59
        points=np.float32([[-width/2,-height/2],[width/2,-height/2],[width/2,height/2],[-width/2,height/2]])
        points+=rng.uniform(-.07,.07,(4,2))*[width,height]
        angle=rng.uniform(-math.pi,math.pi)
        rotation=np.float32([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        points=points@rotation.T+rng.uniform(130,510,(1,2))
        points=points.astype(np.float32)
        h,w=card.shape[:2]
        transform=cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),points)
        warped=cv2.warpPerspective(card,transform,(size,size))
        mask=cv2.warpPerspective(np.full((h,w),255,np.uint8),transform,(size,size),flags=cv2.INTER_NEAREST)>0
        canvas[mask]=warped[mask];owner[mask]=n
        instances.append({'card_id':entry['card_id'],'asset':entry['source'],'corners':points.tolist(),'instance':n})
    # Lighting/blur augment pixels without changing known projective geometry.
    gradient=np.linspace(rng.uniform(.65,1),rng.uniform(1,1.2),size)[None,:,None]
    canvas=np.uint8(np.clip(canvas.astype(float)*gradient,0,255))
    if index%3==0:canvas=cv2.GaussianBlur(canvas,(3,3),rng.uniform(.4,1.1))
    if index%4==0:
        glow=np.zeros((size,size),np.float32)
        cv2.ellipse(glow,tuple(rng.integers(100,540,2)),(70,24),float(rng.uniform(0,180)),0,360,.65,-1)
        glow=cv2.GaussianBlur(glow,(0,0),12)[...,None]
        canvas=np.uint8(canvas*(1-glow)+255*glow)
    labels=[];kept=[]
    for obj in instances:
        n=obj['instance'];p=np.float32(obj['corners'])
        if np.count_nonzero(owner==n)<250:continue
        lo=np.maximum(p.min(0),0);hi=np.minimum(p.max(0),size-1)
        if np.any(hi-lo<10):continue
        keypoints=[]
        for point in p:
            x,y=point
            if not (0<=x<size and 0<=y<size):keypoints.append([0.,0.,0]);continue
            # Sample just inside the boundary to avoid rasterization ambiguity.
            sample=.95*point+.05*p.mean(0);sx,sy=np.rint(sample).astype(int)
            visible=owner[np.clip(sy,0,size-1),np.clip(sx,0,size-1)]==n
            keypoints.append([float(x/size),float(y/size),2 if visible else 1])
        center=(lo+hi)/2/size;dims=(hi-lo)/size
        labels.append(' '.join(map(str,[0,*center.tolist(),*dims.tolist(),*np.array(keypoints).flatten().tolist()])))
        kept.append({**obj,'keypoints':keypoints,'bbox_xyxy':[*lo.tolist(),*hi.tolist()]})
    return canvas,labels,kept


def prepare(output=DEFAULT,train=48,val=12,seed=1104):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be new or empty; preserve existing datasets.')
    catalog=ROOT/'data/pilot/catalog.json'
    entries=json.loads(catalog.read_text(encoding='utf-8'))
    for e in entries:e['path']=(catalog.parent/e['source']).resolve()
    entries=[e for e in entries if e['path'].exists()]
    groups={split:[e for e in entries if asset_split(e['card_id'])==split] for split in ('train','val')}
    if not all(groups.values()):raise ValueError('Need identities in both train and val')
    records=[];tiles=[]
    for split,count in (('train',train),('val',val)):
        (output/'images'/split).mkdir(parents=True,exist_ok=True)
        (output/'labels'/split).mkdir(parents=True,exist_ok=True)
        for i in range(count):
            rng=np.random.default_rng(seed+i+(100000 if split=='val' else 0))
            image,labels,objects=generate(groups[split],rng,i)
            relative=f'images/{split}/{i:05}.jpg'
            cv2.imwrite(str(output/relative),image,[cv2.IMWRITE_JPEG_QUALITY,92])
            (output/'labels'/split/f'{i:05}.txt').write_text('\n'.join(labels)+'\n',encoding='utf-8')
            records.append({'image':relative,'sha256':hashlib.sha256((output/relative).read_bytes()).hexdigest(),
                            'split':split,'synthetic':True,'objects':objects})
            if i<4:
                for obj in objects:
                    p=np.int32(obj['corners']);cv2.polylines(image,[p],True,(0,230,80),2)
                    for k,point in enumerate(p):cv2.putText(image,str(k),tuple(point),0,.6,(10,10,255),2)
                tiles.append(cv2.resize(image,(320,320)))
    manifest={'version':1,'seed':seed,'corner_order':ORDER,'split_by':'card identity (all arts together)',
              'purpose':'Synthetic training bootstrap and plumbing tests; not real-world accuracy validation.',
              'source_catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),'records':records}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    # Relative root is rewritten to an absolute path by train.py for portability.
    (output/'dataset.yaml').write_text('path: .\ntrain: images/train\nval: images/val\nnames: [card]\nkpt_shape: [4, 3]\nflip_idx: [0, 1, 2, 3]\n',encoding='utf-8')
    cv2.imwrite(str(output/'preview.jpg'),np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]))
    return {'dataset':str(output),'train':train,'val':val,'objects':sum(len(r['objects']) for r in records)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--train',type=int,default=48);p.add_argument('--val',type=int,default=12);p.add_argument('--seed',type=int,default=1104)
    a=p.parse_args();print(json.dumps(prepare(a.output,a.train,a.val,a.seed)))
