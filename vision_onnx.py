"""CPU research backend: DRAW2 OBB, classifier and pre-classifier embeddings.

Uses the downloaded DRAW2 Small weights. Thresholds are experimental, not
calibrated confidence. No training or model weight updates are performed.

Inference budget (this PC, 8 logical cores, measured 26/09/2026): one 224x224
encode costs ~624 ms with 2 threads, ~474 ms with 4, ~873 ms with 8; a batch of
four costs ~395 ms per image with 4 threads. Hence 4 threads by default
(`YUGIOH_ONNX_THREADS`) and one batched run per orientation. On 19 annotated
real crops the wrong (180°) orientation scored at most 0.815 while the right
one always won by at least 0.122, so the second orientation is skipped only
when the first already scores >= ORIENTATION_SKIP_SCORE.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from card_geometry import GeometryRefiner
from identity_resolution import canonical

ROOT=Path(__file__).resolve().parent
MODELS=ROOT/'downloads/reference-assets/draw2/onnx'
PILOT=ROOT/'data/pilot'
# Acceptance rules per mode: (minimum top-1 score, minimum margin to the best
# different identity). Experimental; see research/CALIBRACION_ESCANEOS.md.
ACCEPTANCE={'embedding':(.80,.07),'classifier':(.50,.15)}
ORIENTATION_SKIP_SCORE=.90
# A track keeps its identity without re-encoding while it is this fresh and
# still overlaps the new box; afterwards the card is identified again so a
# substitution in the same place is noticed.
REUSE_MAX_AGE_S=8.
REUSE_MIN_IOU=.75
ART_PROMOTION_MAX_AGE_S=4.
ART_PROMOTION_MIN_IOU=.5


def session(path,threads=None):
    options=ort.SessionOptions()
    options.intra_op_num_threads=int(threads or os.environ.get('YUGIOH_ONNX_THREADS') or 4)
    options.inter_op_num_threads=1
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])


def tensor(image,size=224):
    rgb=cv2.cvtColor(cv2.resize(image,(size,size)),cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray((rgb.astype(np.float32)/127.5-1).transpose(2,0,1)[None])


def quad_iou(a,b):
    a=np.float32(a);b=np.float32(b)
    intersection=cv2.intersectConvexConvex(a,b)[0]
    union=cv2.contourArea(a)+cv2.contourArea(b)-intersection
    return float(intersection/union) if union>0 else 0.


def with_features():
    import onnx
    from onnx import helper,TensorProto
    source=MODELS/'vit_yugiscan_int8.onnx'
    target=ROOT/'data/models/vit_small_features.onnx'
    target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    manifest=target.with_suffix('.json')
    if target.exists() and manifest.exists() and json.loads(manifest.read_text())['source_sha256']==digest:
        return target
    model=onnx.load(source)
    # Audited graph: Gather of the final normalized CLS token, before classifier quantization.
    feature='/Gather_output_0'
    assert any(n.op_type=='Gather' and feature in n.output for n in model.graph.node)
    dimension=next(i.dims[0] for i in model.graph.initializer if i.name=='vit.layernorm.weight')
    model.graph.output.append(helper.make_tensor_value_info(feature,TensorProto.FLOAT,['batch',dimension]))
    onnx.checker.check_model(model)
    onnx.save(model,target)
    manifest.write_text(json.dumps({'source_sha256':digest,'feature':feature,'dimension':dimension,
        'preprocessing':'BGR->RGB; resize224 square; x/127.5-1; NCHW; L2 features','trained_for_retrieval':False},indent=2))
    return target


class Encoder:
    def __init__(self):
        self.model_path=with_features()
        self.model=session(self.model_path)
        self.labels=json.loads((MODELS/'card_labels_yugiscan.json').read_text(encoding='utf-8'))
        self.mapping=json.loads((ROOT/'research/references-20260924/draw2-small-ygojson-map.json').read_text(encoding='utf-8'))

    def predict(self,image,*,classify=True):
        return self.predict_batch([image],classify=classify)[0]

    def predict_batch(self,images,*,classify=True):
        """One ONNX run for several crops; each result equals `predict` on that crop."""
        if not images: return []
        blob=np.concatenate([tensor(image) for image in images],axis=0)
        logits,features=self.model.run(None,{self.model.get_inputs()[0].name:blob})
        results=[]
        for row in range(len(images)):
            z=features[row].astype(np.float32);z/=max(np.linalg.norm(z),1e-12)
            # Retrieval uses only z. Do not softmax/sort/map the entire classifier
            # vocabulary when the caller will immediately discard that ranking.
            if not classify:
                results.append(([],z));continue
            scores=np.exp(logits[row]-np.max(logits[row]));scores/=scores.sum()
            top=np.argsort(scores)[-5:][::-1]
            predictions=[{'index':int(i),'label':self.labels[str(i)],'card_id':self.mapping.get(str(i),{}).get('ygojson_uuid'),
                          'score':float(scores[i])} for i in top]
            results.append((predictions,z))
        return results


class Detector:
    def __init__(self):
        self.model=session(MODELS/'ygo_yolo.onnx')

    def detect(self,image,threshold=.2):
        h,w=image.shape[:2];scale=min(640/w,640/h)
        rw,rh=round(w*scale),round(h*scale);px,py=(640-rw)//2,(640-rh)//2
        padded=np.zeros((640,640,3),np.uint8)
        padded[py:py+rh,px:px+rw]=cv2.resize(image,(rw,rh))
        blob=np.ascontiguousarray(cv2.cvtColor(padded,cv2.COLOR_BGR2RGB).transpose(2,0,1)[None].astype(np.float32)/255)
        rows=self.model.run(None,{self.model.get_inputs()[0].name:blob})[0][0]
        if rows.shape[0]<rows.shape[1]: rows=rows.T
        if rows.shape[1]!=6: raise ValueError('Unexpected detector output shape')
        boxes=[]
        for x,y,bw,bh,score,angle in rows[rows[:,4]>=threshold]:
            x,y=(x-px)/scale,(y-py)/scale;bw,bh=bw/scale,bh/scale
            if bw>bh: bw,bh,angle=bh,bw,angle+np.pi/2
            rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            corners=(np.array([[-bw/2,-bh/2],[bw/2,-bh/2],[bw/2,bh/2],[-bw/2,bh/2]])@rotation.T+[x,y]).astype(np.float32)
            if bw<20 or bh<20 or not np.isfinite(corners).all(): continue
            boxes.append({'corners':corners,'score':float(score)})
        kept=[]
        for candidate in sorted(boxes,key=lambda b:-b['score']):
            if any(quad_iou(candidate['corners'],k['corners'])>.5 for k in kept): continue
            kept.append(candidate)
            if len(kept)>=20: break
        return kept


def crop(image,corners):
    dst=np.float32([[0,0],[223,0],[223,223],[0,223]])
    matrix=cv2.getPerspectiveTransform(np.float32(corners),dst)
    return cv2.warpPerspective(image,matrix,(224,224))


def reference_entries(catalog_path=PILOT/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    """Pilot renders plus photographs of the owner's physical cards (enroll_reference.py)."""
    entries=json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    enrolled=json.loads(Path(enrolled_path).read_text(encoding='utf-8')) if Path(enrolled_path).exists() else []
    for entry in enrolled:
        entry.setdefault('enrolled',True)
    return entries+enrolled


def references_digest(catalog_path=PILOT/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    digest=hashlib.sha256(Path(catalog_path).read_bytes())
    if Path(enrolled_path).exists(): digest.update(Path(enrolled_path).read_bytes())
    return digest.hexdigest()


def build_index(catalog_path=PILOT/'catalog.json'):
    entries=reference_entries(catalog_path)
    encoder=Encoder();vectors=[];rows=[]
    for i,entry in enumerate(entries):
        path=(Path(catalog_path).parent/entry['source']).resolve()
        image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        _,z=encoder.predict(image,classify=False)
        vectors.append(z);rows.append({'ref_id':entry['id'],'card_id':entry['card_id'],'artwork_id':entry.get('artwork_id'),
            'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'enrolled':bool(entry.get('enrolled'))})
        if (i+1)%10==0: print('INDEX',i+1,'/',len(entries),flush=True)
    out=Path(catalog_path).parent
    np.save(out/'embeddings.npy',np.stack(vectors))
    (out/'embeddings.json').write_text(json.dumps({'rows':rows,
        'model_sha256':hashlib.sha256(encoder.model_path.read_bytes()).hexdigest(),
        'catalog_sha256':references_digest(catalog_path),
        'dimension':len(vectors[0]),'normalization':'L2','retrieval':'exact cosine','scope':'pilot plus enrolled photos; thresholds not calibrated'},indent=2))
    print('INDEX DONE',len(rows),flush=True)


class ResearchRecognizer:
    def __init__(self,mode='embedding'):
        self.mode=mode;self.detector=Detector();self.encoder=Encoder()
        if mode=='embedding':
            self.vectors=np.load(PILOT/'embeddings.npy')
            metadata=json.loads((PILOT/'embeddings.json').read_text())
            if metadata['catalog_sha256']!=references_digest():
                raise ValueError('Pilot changed; rebuild embeddings index')
            if metadata['model_sha256']!=hashlib.sha256(self.encoder.model_path.read_bytes()).hexdigest():
                raise ValueError('Encoder changed; rebuild embeddings index')
            self.rows=metadata['rows']

    def rank(self,z):
        """Top identities for one embedding: best reference per card_id, sorted."""
        scores=self.vectors@z;grouped={}
        for i in np.argsort(scores)[::-1]:
            row=self.rows[i]
            grouped.setdefault(row['card_id'],{**row,'score':float(scores[i])})
        return list(grouped.values())[:5]

    def identify(self,rectified_crops):
        """Best orientation per crop with as few encoder runs as the scores allow."""
        classify=self.mode!='embedding'
        options=[[] for _ in rectified_crops]
        pending=list(range(len(rectified_crops)))
        for rotation in (0,2):
            if not pending: break
            batch=[np.ascontiguousarray(np.rot90(rectified_crops[i],rotation)) for i in pending]
            for i,(predictions,z) in zip(pending,self.encoder.predict_batch(batch,classify=classify)):
                if not classify: predictions=self.rank(z)
                options[i].append((predictions[0]['score'] if predictions else 0.,rotation,predictions))
            # Only crops whose first orientation is not already convincing pay for the second.
            pending=[i for i in pending if options[i][0][0]<ORIENTATION_SKIP_SCORE]
        return [max(o,key=lambda x:x[0]) for o in options]

    def detect(self,image,reuse=()):
        started=time.perf_counter();result=[]
        boxes=self.detector.detect(image)
        geometry_started=time.perf_counter()
        refiner=GeometryRefiner(image) if boxes else None
        geometries=[refiner.refine(box['corners']) for box in boxes] if refiner else []
        geometry_ms=round((time.perf_counter()-geometry_started)*1000,1)
        minimum,margin_floor=ACCEPTANCE['embedding' if self.mode=='embedding' else 'classifier']
        points=[np.float32(g.get('corners',b['corners'])) for b,g in zip(boxes,geometries)]
        # Fresh, well-overlapping tracks keep their identity without a new encode.
        reused={}
        for index,quad in enumerate(points):
            best=max(((quad_iou(quad,t['corners']),t) for t in reuse if t.get('card_id')),key=lambda x:x[0],default=(0.,None))
            if best[1] is not None and best[0]>=REUSE_MIN_IOU: reused[index]=(best[0],best[1])
        fresh=[i for i in range(len(boxes)) if i not in reused]
        identified=dict(zip(fresh,self.identify([crop(image,points[i]) for i in fresh])))
        encoded=len(fresh)
        for index,(box,geometry) in enumerate(zip(boxes,geometries)):
            quad=points[index]
            if index in reused:
                iou,track=reused[index]
                rotation=int(track.get('rotation',0))//90
                top=track.get('top5') or [{'card_id':track['card_id'],'score':track.get('score',0.),'ref_id':track.get('ref_id'),'artwork_id':track.get('artwork_id')}]
                result.append({'card_id':track['card_id'],'corners':np.roll(quad,-rotation,axis=0).tolist(),'score':float(track.get('score',0.)),
                               'detector_corners':np.roll(box['corners'],-rotation,axis=0).tolist(),
                               'geometry_status':geometry['geometry_status'],'geometry_iou':geometry.get('geometry_iou'),
                               'margin':float(track.get('margin',0.)),'accepted':True,'top5':top,'rotation':rotation*90,'detector_score':box['score'],
                               'identity_source':'track','reuse_iou':round(iou,3),'track_id':track.get('track_id')})
                continue
            score,rotation,top=identified[index]
            corners=np.roll(quad,-rotation,axis=0)
            if not top:
                # Empty index or no classifier mapping: report the box, never an identity.
                result.append({'card_id':None,'corners':corners.tolist(),'score':0.,'detector_corners':np.roll(box['corners'],-rotation,axis=0).tolist(),
                               'geometry_status':geometry['geometry_status'],'geometry_iou':geometry.get('geometry_iou'),'margin':0.,
                               'accepted':False,'top5':[],'rotation':rotation*90,'detector_score':box['score'],'identity_source':'none'})
                continue
            margin=top[0]['score']-(top[1]['score'] if len(top)>1 else 0)
            accepted=bool(top[0]['card_id']) and top[0]['score']>=minimum and margin>=margin_floor
            result.append({'card_id':top[0]['card_id'],'corners':corners.tolist(),'score':top[0]['score'],
                           'detector_corners':np.roll(box['corners'],-rotation,axis=0).tolist(),
                           'geometry_status':geometry['geometry_status'],'geometry_iou':geometry.get('geometry_iou'),
                           'margin':margin,'accepted':accepted,'top5':top,'rotation':rotation*90,'detector_score':box['score'],
                           'identity_source':'embedding' if self.mode=='embedding' else 'classifier',
                           'acceptance':'score' if accepted else None})
        return {'detections':result,'processing_ms':round((time.perf_counter()-started)*1000,1),'mode':self.mode,
                'experimental_thresholds':True,'geometry_ms':geometry_ms,'encoded_cards':encoded,'reused_cards':len(reused)}


def promote_by_art(candidates,verified,now=None):
    """Accept a rejected candidate whose top-1 identity was verified on the illustration.

    `verified` items come from the asynchronous art verifier: corners, card_id,
    inliers and captured_at. Only the same identity, on an overlapping card,
    within ART_PROMOTION_MAX_AGE_S, counts. The score itself is untouched.
    """
    now=time.time() if now is None else now
    promoted=0
    for candidate in candidates:
        if candidate.get('accepted') or not candidate.get('card_id'): continue
        for item in verified:
            if canonical(item.get('card_id'))!=canonical(candidate['card_id']): continue
            if not 0<=now-item.get('captured_at',0)<=ART_PROMOTION_MAX_AGE_S: continue
            if quad_iou(candidate['corners'],item['corners'])<ART_PROMOTION_MIN_IOU: continue
            candidate.update(accepted=True,acceptance='art_verified',art_inliers=item.get('inliers'),art_artwork_id=item.get('artwork_id'))
            promoted+=1;break
    return promoted


class LiveRecognizer(ResearchRecognizer):
    """Explicit experimental opt-in for the viewer, retaining rejected candidates."""
    def __init__(self,mode='embedding'):
        super().__init__(mode)
        self.references=reference_entries()
        self.cards={};self.references_by_id={}
        for ref in self.references:
            self.cards.setdefault(ref['card_id'],ref)
            self.references_by_id.setdefault(ref['id'],ref)
        # Names of classifier identities outside the pilot. The catalog is read-only
        # for this process, so entries stay valid until restart; the size bound only
        # limits memory if the classifier drifts over its whole vocabulary.
        self.outside_pilot={};self.outside_pilot_limit=2000

    def outside_entry(self,card_id):
        # Classifier can recognize cards outside the pilot; resolve metadata once,
        # but never claim a sprite unless its reference has a supported link.
        entry=self.outside_pilot.get(card_id)
        if entry is None:
            from catalog import connect
            with connect() as conn:
                row=conn.execute('SELECT name_es,name_en FROM cards WHERE id=?',(card_id,)).fetchone()
            entry={'name':(row['name_es'] or row['name_en']) if row else card_id}
            if len(self.outside_pilot)>=self.outside_pilot_limit: self.outside_pilot.clear()
            self.outside_pilot[card_id]=entry
        return entry

    def describe(self,candidate):
        entry=self.cards.get(candidate['card_id']) or self.outside_entry(candidate['card_id'])
        matching=self.references_by_id.get((candidate.get('top5') or [{}])[0].get('ref_id'),entry)
        if candidate.get('art_artwork_id'):
            # The verified illustration names the artwork; prefer its sprite when known.
            matching=next((r for r in self.references if r['card_id']==candidate['card_id'] and r.get('artwork_id')==candidate['art_artwork_id']),matching)
        return {**candidate,'id':matching.get('id','model:'+candidate['card_id']),'name':entry['name'],'artwork_id':matching.get('artwork_id'),
                'sprite_ref':matching.get('sprite_ref'),'experimental':True}

    def analyze_jpeg(self,data,reuse=(),verified=()):
        image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError('Invalid JPEG')
        result=self.detect(image,reuse=reuse)
        result['candidates']=result['detections']
        result['art_promoted']=promote_by_art(result['candidates'],verified)
        result['detections']=[self.describe(c) for c in result['candidates'] if c['accepted']]
        result.update(width=image.shape[1],height=image.shape[0])
        return result


if __name__=='__main__':
    build_index()
