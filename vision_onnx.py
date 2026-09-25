"""CPU research backend: DRAW2 OBB, classifier and pre-classifier embeddings.

Uses the downloaded DRAW2 Small weights. Thresholds are experimental, not
calibrated confidence. No training or model weight updates are performed.
"""
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from card_geometry import GeometryRefiner

ROOT=Path(__file__).resolve().parent
MODELS=ROOT/'downloads/reference-assets/draw2/onnx'


def session(path):
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])


def tensor(image,size=224):
    rgb=cv2.cvtColor(cv2.resize(image,(size,size)),cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray((rgb.astype(np.float32)/127.5-1).transpose(2,0,1)[None])


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
        logits,features=self.model.run(None,{self.model.get_inputs()[0].name:tensor(image)})
        z=features[0].astype(np.float32);z/=max(np.linalg.norm(z),1e-12)
        # Retrieval uses only z. Do not softmax/sort/map the entire classifier
        # vocabulary when the caller will immediately discard that ranking.
        if not classify:
            return [],z
        scores=np.exp(logits[0]-np.max(logits[0]));scores/=scores.sum()
        top=np.argsort(scores)[-5:][::-1]
        predictions=[{'index':int(i),'label':self.labels[str(i)],'card_id':self.mapping.get(str(i),{}).get('ygojson_uuid'),
                      'score':float(scores[i])} for i in top]
        return predictions,z


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
            a=candidate['corners'];area=cv2.contourArea(a)
            if any((lambda intersection,b:intersection/max(area+cv2.contourArea(b)-intersection,1e-8))
                   (cv2.intersectConvexConvex(a,k['corners'])[0],k['corners'])>.5 for k in kept): continue
            kept.append(candidate)
            if len(kept)>=20: break
        return kept


def crop(image,corners):
    dst=np.float32([[0,0],[223,0],[223,223],[0,223]])
    matrix=cv2.getPerspectiveTransform(np.float32(corners),dst)
    return cv2.warpPerspective(image,matrix,(224,224))


def build_index(catalog_path=ROOT/'data/pilot/catalog.json'):
    entries=json.loads(catalog_path.read_text(encoding='utf-8'))
    encoder=Encoder();vectors=[];rows=[]
    for i,entry in enumerate(entries):
        path=(catalog_path.parent/entry['source']).resolve()
        image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        _,z=encoder.predict(image,classify=False)
        vectors.append(z);rows.append({'ref_id':entry['id'],'card_id':entry['card_id'],'artwork_id':entry.get('artwork_id'),
            'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if (i+1)%10==0: print('INDEX',i+1,'/',len(entries),flush=True)
    out=ROOT/'data/pilot'
    np.save(out/'embeddings.npy',np.stack(vectors))
    (out/'embeddings.json').write_text(json.dumps({'rows':rows,
        'model_sha256':hashlib.sha256(encoder.model_path.read_bytes()).hexdigest(),
        'catalog_sha256':hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        'dimension':len(vectors[0]),'normalization':'L2','retrieval':'exact cosine','scope':'pilot only; thresholds not calibrated'},indent=2))
    print('INDEX DONE',len(rows),flush=True)


class ResearchRecognizer:
    def __init__(self,mode='embedding'):
        self.mode=mode;self.detector=Detector();self.encoder=Encoder()
        if mode=='embedding':
            self.vectors=np.load(ROOT/'data/pilot/embeddings.npy')
            metadata=json.loads((ROOT/'data/pilot/embeddings.json').read_text())
            if metadata['catalog_sha256']!=hashlib.sha256((ROOT/'data/pilot/catalog.json').read_bytes()).hexdigest():
                raise ValueError('Pilot changed; rebuild embeddings index')
            if metadata['model_sha256']!=hashlib.sha256(self.encoder.model_path.read_bytes()).hexdigest():
                raise ValueError('Encoder changed; rebuild embeddings index')
            self.rows=metadata['rows']

    def detect(self,image):
        started=time.perf_counter();result=[]
        boxes=self.detector.detect(image)
        geometry_started=time.perf_counter()
        refiner=GeometryRefiner(image) if boxes else None
        geometries=[refiner.refine(box['corners']) for box in boxes]
        geometry_ms=round((time.perf_counter()-geometry_started)*1000,1)
        for box,geometry in zip(boxes,geometries):
            points=np.float32(geometry.get('corners',box['corners']))
            options=[];rectified=crop(image,points)
            for rotation in (0,2):
                predictions,z=self.encoder.predict(np.ascontiguousarray(np.rot90(rectified,rotation)),classify=self.mode!='embedding')
                if self.mode=='embedding':
                    scores=self.vectors@z;grouped={}
                    for i in np.argsort(scores)[::-1]:
                        row=self.rows[i]
                        grouped.setdefault(row['card_id'],{**row,'score':float(scores[i])})
                    predictions=list(grouped.values())[:5]
                options.append((predictions[0]['score'],rotation,predictions))
            _,rotation,top=max(options,key=lambda x:x[0])
            margin=top[0]['score']-(top[1]['score'] if len(top)>1 else 0)
            accepted=bool(top[0]['card_id']) and top[0]['score']>=(.80 if self.mode=='embedding' else .50) and margin>=(.07 if self.mode=='embedding' else .15)
            corners=np.roll(points,-rotation,axis=0)
            result.append({'card_id':top[0]['card_id'],'corners':corners.tolist(),'score':top[0]['score'],
                           'detector_corners':np.roll(box['corners'],-rotation,axis=0).tolist(),
                           'geometry_status':geometry['geometry_status'],'geometry_iou':geometry.get('geometry_iou'),
                           'margin':margin,'accepted':accepted,'top5':top,'rotation':rotation*90,'detector_score':box['score']})
        return {'detections':result,'processing_ms':round((time.perf_counter()-started)*1000,1),'mode':self.mode,
                'experimental_thresholds':True,'geometry_ms':geometry_ms}


class LiveRecognizer(ResearchRecognizer):
    """Explicit experimental opt-in for the viewer, retaining rejected candidates."""
    def __init__(self,mode='embedding'):
        super().__init__(mode)
        self.references=json.loads((ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))
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

    def analyze_jpeg(self,data):
        image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError('Invalid JPEG')
        result=self.detect(image)
        result['candidates']=result['detections']
        result['detections']=[]
        for candidate in result['candidates']:
            if not candidate['accepted']: continue
            entry=self.cards.get(candidate['card_id']) or self.outside_entry(candidate['card_id'])
            matching=self.references_by_id.get(candidate['top5'][0].get('ref_id'),entry)
            result['detections'].append({**candidate,'id':matching.get('id','model:'+candidate['card_id']),
                    'name':entry['name'],'artwork_id':matching.get('artwork_id'),
                    'sprite_ref':matching.get('sprite_ref'),'experimental':True})
        result.update(width=image.shape[1],height=image.shape[0])
        return result


if __name__=='__main__':
    build_index()
