"""Research backend: DRAW2 OBB, classifier and pre-classifier embeddings (CPU, or CUDA via YUGIOH_ONNX_DEVICE).

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from card_geometry import GeometryRefiner
from identity_resolution import canonical

ROOT=Path(__file__).resolve().parent
MODELS=ROOT/'downloads/reference-assets/draw2/onnx'
PILOT=ROOT/'data/pilot'
# Reference scope: 'pilot' (the <=50 cards chosen in the catalog, default) or
# 'full' (every catalog identity with a usable image, catalog.export_full into
# data/full). Photos enrolled with enroll_reference.py live in the pilot folder
# and join either scope.
SCOPE=os.environ.get('YUGIOH_SCOPE','pilot').lower()
if SCOPE not in ('pilot','full'): raise ValueError(f'YUGIOH_SCOPE={SCOPE!r}: use pilot or full')
REFS=PILOT if SCOPE=='pilot' else ROOT/'data/full'
# Acceptance rules per mode: (minimum top-1 score, minimum margin to the best
# different identity). Embedding rule calibrated on 26/09/2026 against 1,336
# TCGplayer scans of cards outside the pilot (0 false accepts down to 0.48/0.24)
# and 446 scans of pilot cards (97.1% recall vs 91.0% with the old 0.80/0.07);
# set a little above that frontier because scans are flatter than table photos.
# See research/CALIBRACION_ESCANEOS.md.
ACCEPTANCE={'embedding':(.50,.25),'classifier':(.50,.15)}
ORIENTATION_SKIP_SCORE=.90
# A track keeps its identity without re-encoding while it is this fresh and
# still overlaps the new box; afterwards the card is identified again so a
# substitution in the same place is noticed.
REUSE_MAX_AGE_S=8.
REUSE_MIN_IOU=.75
ART_PROMOTION_MAX_AGE_S=4.
ART_PROMOTION_MIN_IOU=.5
# Detector OBB against a tracked quadrilateral: an upright rectangle around a
# card in mild perspective still overlaps it well above this.
TRACKED_GEOMETRY_MIN_IOU=.75
UNRESOLVED_RETRY_S=2.
UNRESOLVED_MIN_IOU=.85
# Separate from card_geometry.POOL, whose workers this thread waits on.
EVIDENCE=ThreadPoolExecutor(max_workers=1,thread_name_prefix='evidence')


# Execution device: 'cpu' (default) or 'cuda' (needs onnxruntime-gpu, see
# requirements-gpu.txt). The int8 encoder only runs well on CPU; on CUDA the
# default is the float model from research/dequantize_encoder.py, which has its
# own index (embeddings-<variant>.npy) and must be calibrated separately.
DEVICE=os.environ.get('YUGIOH_ONNX_DEVICE','cpu').lower()
ENCODER_VARIANT=os.environ.get('YUGIOH_ENCODER') or ('int8' if DEVICE=='cpu' else 'fp16')


def providers():
    if DEVICE=='cpu': return ['CPUExecutionProvider']
    if DEVICE!='cuda': raise ValueError(f'YUGIOH_ONNX_DEVICE={DEVICE!r}: use cpu or cuda')
    if hasattr(ort,'preload_dlls'): ort.preload_dlls()  # CUDA/cuDNN from the nvidia-* wheels
    # Heuristic cuDNN search: batch size changes with the number of cards and an
    # exhaustive search per new shape stalls the first frames that see it.
    return [('CUDAExecutionProvider',{'cudnn_conv_algo_search':'HEURISTIC'}),'CPUExecutionProvider']


def session(path,threads=None):
    options=ort.SessionOptions()
    options.intra_op_num_threads=int(threads or os.environ.get('YUGIOH_ONNX_THREADS') or 4)
    options.inter_op_num_threads=1
    result=ort.InferenceSession(str(path),sess_options=options,providers=providers())
    if DEVICE=='cuda' and 'CUDAExecutionProvider' not in result.get_providers():
        print(f'WARNING: CUDA unavailable for {Path(path).name}; running on CPU',flush=True)
    return result


def index_paths(variant=None):
    """Index files of the current scope for an encoder variant; int8 keeps the historical names."""
    variant=variant or ENCODER_VARIANT
    stem='embeddings' if variant=='int8' else f'embeddings-{variant}'
    return REFS/f'{stem}.npy',REFS/f'{stem}.json'


IMAGENET_MEAN=np.float32([.485,.456,.406]);IMAGENET_STD=np.float32([.229,.224,.225])


def tensor(image,size=224,normalization='draw2'):
    rgb=cv2.cvtColor(cv2.resize(image,(size,size)),cv2.COLOR_BGR2RGB).astype(np.float32)
    x=(rgb/255-IMAGENET_MEAN)/IMAGENET_STD if normalization=='imagenet' else rgb/127.5-1
    return np.ascontiguousarray(x.transpose(2,0,1)[None])


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


def encoder_path(variant):
    """int8/fp32/fp16: DRAW2 Small; any other name is a retrieval-only model in data/models (e.g. dinov2_vits14)."""
    if variant=='int8': return with_features()
    draw2=variant in ('fp32','fp16')
    path=ROOT/(f'data/models/vit_small_features_{variant}.onnx' if draw2 else f'data/models/{variant}.onnx')
    if not path.exists():
        raise FileNotFoundError(f'{path} missing: run research/{"dequantize_encoder.py" if draw2 else "export_dinov2.py"}')
    return path


class Encoder:
    def __init__(self,variant=None):
        self.variant=variant or ENCODER_VARIANT
        self.model_path=encoder_path(self.variant)
        self.model=session(self.model_path)
        manifest=self.model_path.with_suffix('.json')
        self.normalization=json.loads(manifest.read_text()).get('preprocessing') if manifest.exists() else None
        self.normalization='imagenet' if self.normalization=='imagenet' else 'draw2'
        # Retrieval-only encoders have a single output and no classifier vocabulary.
        self.retrieval_only=len(self.model.get_outputs())==1
        self.labels=json.loads((MODELS/'card_labels_yugiscan.json').read_text(encoding='utf-8'))
        self.mapping=json.loads((ROOT/'research/references-20260924/draw2-small-ygojson-map.json').read_text(encoding='utf-8'))

    def predict(self,image,*,classify=True):
        return self.predict_batch([image],classify=classify)[0]

    def predict_batch(self,images,*,classify=True):
        """One ONNX run for several crops; each result equals `predict` on that crop."""
        if not images: return []
        blob=np.concatenate([tensor(image,normalization=self.normalization) for image in images],axis=0)
        outputs=self.model.run(None,{self.model.get_inputs()[0].name:blob})
        logits,features=(None,outputs[0]) if self.retrieval_only else outputs
        results=[]
        for row in range(len(images)):
            z=features[row].astype(np.float32);z/=max(np.linalg.norm(z),1e-12)
            # Retrieval uses only z. Do not softmax/sort/map the entire classifier
            # vocabulary when the caller will immediately discard that ranking.
            if not classify or logits is None:
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


def reference_entries(catalog_path=REFS/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    """Scope references plus photographs of the owner's physical cards (enroll_reference.py)."""
    entries=json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    enrolled=json.loads(Path(enrolled_path).read_text(encoding='utf-8')) if Path(enrolled_path).exists() else []
    for entry in enrolled:
        # Enrolled sources are relative to the pilot folder, whatever the scope.
        entry.setdefault('enrolled',True);entry['base']=str(Path(enrolled_path).parent)
    return entries+enrolled


def references_digest(catalog_path=REFS/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    digest=hashlib.sha256(Path(catalog_path).read_bytes())
    if Path(enrolled_path).exists(): digest.update(Path(enrolled_path).read_bytes())
    return digest.hexdigest()


def build_index(catalog_path=REFS/'catalog.json',encoder=None):
    entries=reference_entries(catalog_path)
    encoder=encoder or Encoder();vectors=[];rows=[]
    # Float encoders batch 32 references per run (lote/imagen drift 0.0001); int8
    # keeps one run per reference so the historical index reproduces exactly.
    step=1 if encoder.variant=='int8' else 32
    for start in range(0,len(entries),step):
        chunk=entries[start:start+step];images=[];data=[]
        for entry in chunk:
            path=(Path(entry.get('base') or Path(catalog_path).parent)/entry['source']).resolve()
            data.append(path.read_bytes());images.append(cv2.imdecode(np.frombuffer(data[-1],np.uint8),cv2.IMREAD_COLOR))
        for entry,raw,(_,z) in zip(chunk,data,encoder.predict_batch(images,classify=False)):
            vectors.append(z);rows.append({'ref_id':entry['id'],'card_id':entry['card_id'],'artwork_id':entry.get('artwork_id'),
                'image_sha256':hashlib.sha256(raw).hexdigest(),'enrolled':bool(entry.get('enrolled'))})
        done=start+len(chunk)
        if done%(10 if len(entries)<1000 else 1024)<len(chunk) or done==len(entries): print('INDEX',done,'/',len(entries),flush=True)
    out=Path(catalog_path).parent
    vectors_path,metadata_path=index_paths(encoder.variant)
    # Atomic replace: two viewers may rebuild after the same pilot change, and a
    # reader must never load half a file. Vectors first, metadata (the digest) last.
    suffix=f'.{os.getpid()}.tmp'
    with open(out/(vectors_path.name+suffix),'wb') as f: np.save(f,np.stack(vectors))
    os.replace(out/(vectors_path.name+suffix),out/vectors_path.name)
    (out/(metadata_path.name+suffix)).write_text(json.dumps({'rows':rows,'encoder_variant':encoder.variant,
        'model_sha256':hashlib.sha256(encoder.model_path.read_bytes()).hexdigest(),
        'catalog_sha256':references_digest(catalog_path),
        'dimension':len(vectors[0]),'normalization':'L2','retrieval':'exact cosine','scope':f'{SCOPE} plus enrolled photos; thresholds not calibrated'},indent=2))
    os.replace(out/(metadata_path.name+suffix),out/metadata_path.name)
    print('INDEX DONE',len(rows),flush=True)


class ResearchRecognizer:
    def __init__(self,mode='embedding',rebuild=True):
        self.mode=mode;self.detector=Detector();self.encoder=Encoder()
        self.model_sha=hashlib.sha256(self.encoder.model_path.read_bytes()).hexdigest()
        if mode=='embedding': self.load_index(rebuild=rebuild)

    def load_index(self,rebuild=True):
        """Pilot index for this encoder; rebuilt when the pilot or the encoder changed.

        Saving the pilot in the catalog rewrites catalog.json but not the index, so
        a stale index is expected, not an error. `rebuild=False` keeps the old strict
        behaviour for experiments that must not touch data/pilot.
        """
        vectors_path,metadata_path=index_paths(self.encoder.variant)
        digest=references_digest()
        def stale():
            if not (vectors_path.exists() and metadata_path.exists()): return 'missing'
            metadata=json.loads(metadata_path.read_text())
            if metadata['catalog_sha256']!=digest: return 'pilot changed'
            if metadata['model_sha256']!=self.model_sha: return 'encoder changed'
            return None
        reason=stale()
        if reason:
            if not rebuild: raise ValueError(f'{vectors_path.name}: {reason}; rebuild with YUGIOH_ENCODER={self.encoder.variant} python vision_onnx.py')
            print(f'INDEX {self.encoder.variant}: {reason}; rebuilding',flush=True)
            build_index(encoder=self.encoder)
        metadata=json.loads(metadata_path.read_text())
        self.vectors=np.load(vectors_path);self.rows=metadata['rows'];self.index_digest=metadata['catalog_sha256']

    def rank(self,z):
        """Top identities for one embedding: best reference per card_id, sorted."""
        scores=self.vectors@z;grouped={}
        for i in np.argsort(scores)[::-1]:
            row=self.rows[i]
            grouped.setdefault(row['card_id'],{**row,'score':float(scores[i])})
            # Only the first five identities are returned: stop there (a full
            # catalog has ~16k references, and this loop is Python).
            if len(grouped)==5: break
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

    def detect(self,image,reuse=(),regions=None):
        """`regions`: image polygons of the duel board's field zones. Boxes whose centre falls
        outside all of them (a hand, the Graveyard, the table) skip geometry and encoding."""
        started=time.perf_counter();result=[]
        # Frame-wide edge evidence does not depend on the boxes: extract it while the detector runs.
        evidence=EVIDENCE.submit(GeometryRefiner,image)
        boxes=self.detector.detect(image);outside=0
        if regions:
            polygons=[np.float32(r).reshape(-1,1,2) for r in regions]
            inside=[b for b in boxes if any(cv2.pointPolygonTest(p,tuple(map(float,np.float32(b['corners']).mean(0))),False)>=0 for p in polygons)]
            outside=len(boxes)-len(inside);boxes=inside
        geometry_started=time.perf_counter()
        # A box over a fresh, stable track takes the tracker's corners: the tracker
        # follows them at video rate (2-5 px) and refining a static card again cost
        # 5-90 ms each on live frames. Status 'tracked' keeps OCR crops off; the track
        # expires after REUSE_MAX_AGE_S and the card is then refined and encoded again.
        tracked={}
        for index,box in enumerate(boxes):
            best=max(((quad_iou(box['corners'],t['corners']),t) for t in reuse if t.get('card_id')),key=lambda x:x[0],default=(0.,None))
            if best[1] is not None and best[0]>=TRACKED_GEOMETRY_MIN_IOU: tracked[index]=best[1]
        now=time.time();self.unresolved=[(q,t) for q,t in getattr(self,'unresolved',[]) if now-t<=UNRESOLVED_RETRY_S]
        pending=[i for i in range(len(boxes)) if i not in tracked]
        # Edge snapping just failed on (nearly) this box: skip only that fallback until the retry delay.
        snap=[not any(quad_iou(boxes[i]['corners'],q)>=UNRESOLVED_MIN_IOU for q,_ in self.unresolved) for i in pending]
        refiner=evidence.result()
        refined=dict(zip(pending,refiner.refine_all([boxes[i]['corners'] for i in pending],snap=snap))) if pending else {}
        for i,s in zip(pending,snap):
            if s and refined[i]['geometry_status']=='unresolved': self.unresolved.append((np.float32(boxes[i]['corners']),now))
        # Track corners are in card order (rotation applied); undo it so the common path below rolls them once.
        geometries=[{'corners':np.roll(np.float32(tracked[i]['corners']),int(tracked[i].get('rotation',0))//90,axis=0).tolist(),
                     'geometry_status':'tracked','geometry_source':'live_tracking'} if i in tracked else refined[i] for i in range(len(boxes))]
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
                'experimental_thresholds':True,'geometry_ms':geometry_ms,'encoded_cards':encoded,'reused_cards':len(reused),'outside_regions':outside}


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
        self.load_references()
        # Names of classifier identities outside the pilot. The catalog is read-only
        # for this process, so entries stay valid until restart; the size bound only
        # limits memory if the classifier drifts over its whole vocabulary.
        self.outside_pilot={};self.outside_pilot_limit=2000

    def pilot_signature(self):
        return tuple(p.stat().st_mtime_ns if p.exists() else None for p in (REFS/'catalog.json',PILOT/'enrolled.json'))

    def load_references(self):
        self.signature=self.pilot_signature()
        self.references=reference_entries()
        self.cards={};self.references_by_id={}
        # Cards without a TDOANE sprite use their automatic cut-out when research/auto_cutout.py made one.
        auto=ROOT/'data/auto-sprites'
        made={p.name for p in auto.glob('*.png')} if auto.exists() else set()
        for ref in self.references:
            if not ref.get('sprite_ref') and ref.get('source'):
                name=Path(ref['source']).stem+'.png'
                if name in made: ref['sprite_ref']='auto:'+name
        for ref in self.references:
            self.cards.setdefault(ref['card_id'],ref)
            self.references_by_id.setdefault(ref['id'],ref)

    def refresh_pilot(self):
        """Pick up a pilot saved in the catalog (or new enrolled photos) without a restart."""
        if self.pilot_signature()==self.signature: return False
        if self.mode=='embedding': self.load_index()
        self.load_references()
        return True

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

    def analyze_jpeg(self,data,reuse=(),verified=(),regions=None,back_zones=None):
        """`back_zones`: [{'id','polygon'}] of the duel board; those without a detected card are
        checked for a card back (card_backs), reported in result['backs'] with their scores."""
        image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError('Invalid JPEG')
        reloaded=self.refresh_pilot()
        result=self.detect(image,reuse=reuse,regions=regions)
        if back_zones and self.mode=='embedding':
            from card_backs import BackChecker,THRESHOLD
            if getattr(self,'backs',None) is None: self.backs=BackChecker(self.encoder)
            from card_backs import STRONG
            started=time.perf_counter()
            # Every zone is scored. A face-up card scores <= 0.15 against the backs, so a strong back
            # score means a back even when the recogniser "accepted" a face there: on 28/09/2026 a
            # set card was read as Salamangreat Almiraj for seconds, the zone looked empty and the
            # duel sent the set monster to the Graveyard. Weak back scores still yield to a face.
            scores=self.backs.check(image,back_zones)
            polygons={z['id']:np.float32(z['polygon']).reshape(-1,1,2) for z in back_zones}
            inside=lambda d,zid:cv2.pointPolygonTest(polygons[zid],tuple(map(float,np.float32(d['corners']).mean(0))),False)>=0
            strong={s['id'] for s in scores if s['score']>=STRONG}
            for d in result['detections']:
                if d.get('accepted') and any(inside(d,zid) for zid in strong):
                    d.update(accepted=False,acceptance=None,rejected_as='card_back')
            faces=[d for d in result['detections'] if d.get('accepted')]
            result['backs']=[s for s in scores if s['id'] in strong or (s['score']>=THRESHOLD and not any(inside(d,s['id']) for d in faces))]
            result['back_scores']=scores;result['backs_ms']=round((time.perf_counter()-started)*1000,1)
        result['pilot_reloaded']=reloaded
        result['candidates']=result['detections']
        result['art_promoted']=promote_by_art(result['candidates'],verified)
        result['detections']=[self.describe(c) for c in result['candidates'] if c['accepted']]
        result.update(width=image.shape[1],height=image.shape[0])
        return result


if __name__=='__main__':
    build_index()
