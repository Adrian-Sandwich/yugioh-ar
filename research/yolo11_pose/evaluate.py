"""Offline four-corner evaluation; synthetic metrics never authorize deployment."""
import argparse,json,os,time
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'.runtime/ultralytics-pose'))
# Ultralytics falls back to <cwd>/Ultralytics when this directory does not exist yet.
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)


def iou(a,b):
    lo=np.maximum(a[:2],b[:2]);hi=np.minimum(a[2:],b[2:]);inter=np.prod(np.maximum(hi-lo,0))
    return float(inter/max(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-inter,1e-9))


def summarize(observations):
    truth=sum(o['truth'] for o in observations);pred=sum(o['predicted'] for o in observations);matched=sum(o['matched'] for o in observations)
    errors=[e for o in observations for e in o['visible_corner_error_px']]
    normalized=[e for o in observations for e in o['visible_corner_error_diagonal']]
    times=[o['elapsed_ms'] for o in observations]
    return {'images':len(observations),'truth_instances':truth,'predicted_instances':pred,'matched_bbox_iou_05':matched,
        'bbox_precision':matched/pred if pred else None,'bbox_recall':matched/truth if truth else None,
        'matched_corners_measured':len(errors),'corner_error_px_median':float(np.median(errors)) if errors else None,
        'corner_error_diagonal_median':float(np.median(normalized)) if normalized else None,
        'wall_ms_p50':float(np.median(times)),'wall_ms_p95':float(np.percentile(times,95)),
        'caution':'Single-frame batch1 predict wall time; small samples/synthetic scenes are not deployment validation.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--split',default='val')
    p.add_argument('--device',default='cpu');p.add_argument('--imgsz',type=int,default=640)
    p.add_argument('--limit',type=int,default=0);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    import torch,ultralytics
    from ultralytics import YOLO
    torch.set_num_threads(2);model=YOLO(str(a.weights))
    if list(model.model.model[-1].kpt_shape)!=[4,3]:raise ValueError('Not a trained four-corner model')
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'));records=[r for r in manifest['records'] if r['split']==a.split]
    if a.limit:records=records[:a.limit]
    if not records:raise ValueError('Empty evaluation split')
    observations=[]
    for index,r in enumerate(records):
        if not r.get('synthetic') and not (r.get('reviewed') and r.get('exhaustive')):raise ValueError('Unreviewed real scene')
        image=cv2.imread(str(a.manifest.parent/r['image']));h,w=image.shape[:2]
        if index==0:
            for _ in range(2):model.predict(image,imgsz=a.imgsz,device=a.device,verbose=False)
        if a.device!='cpu':torch.cuda.synchronize()
        start=time.perf_counter();result=model.predict(image,imgsz=a.imgsz,device=a.device,conf=.25,verbose=False)[0]
        boxes=result.boxes.xyxy.cpu().numpy();points=result.keypoints.xy.cpu().numpy()
        if a.device!='cpu':torch.cuda.synchronize()
        elapsed=(time.perf_counter()-start)*1000
        targets=[]
        for obj in r['objects']:
            q=np.float32(obj['corners']);box=np.r_[np.maximum(q.min(0),0),np.minimum(q.max(0),[w-1,h-1])]
            visibility=np.array(obj.get('visibility',[k[2] for k in obj.get('keypoints',[])]))
            if visibility.shape!=(4,):raise ValueError('Missing corner visibility')
            targets.append((q,box,visibility))
        candidates=sorted([(iou(b,t[1]),i,j) for i,b in enumerate(boxes) for j,t in enumerate(targets)],reverse=True)
        used_pred=set();used_gt=set();errors=[];normalized=[]
        for overlap,i,j in candidates:
            if overlap<.5:break
            if i in used_pred or j in used_gt:continue
            used_pred.add(i);used_gt.add(j)
            q,box,visibility=targets[j];distance=np.linalg.norm(points[i]-q,axis=1)[visibility==2]
            errors.extend(distance.tolist());normalized.extend((distance/max(np.linalg.norm(box[2:]-box[:2]),1)).tolist())
        observations.append({'image':r['image'],'truth':len(targets),'predicted':len(boxes),'matched':len(used_gt),
            'visible_corner_error_px':errors,'visible_corner_error_diagonal':normalized,'elapsed_ms':elapsed})
    report={'summary':summarize(observations),'observations':observations,'weights':str(a.weights),
        'ultralytics':ultralytics.__version__,'torch':torch.__version__,'device':a.device,'imgsz':a.imgsz,
        'matching':'greedy one-to-one bbox IoU >= 0.5; semantic TL/TR/BR/BL order, no cyclic minimization',
        'visibility_warning':'Stock loss treats v=1 and v=2 as present. Output confidence is NOT observed/occluded classification.',
        'deployable':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
