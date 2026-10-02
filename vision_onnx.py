"""The recognizer: detect card boxes, refine their corners, identify them against the reference index.

Models and sessions: onnx_models.py. Reference index: reference_index.py. Second votes (art,
title): promotions.py. Thresholds are experimental, not calibrated confidence.

One batched encoder run per orientation. On 19 annotated
real crops the wrong (180°) orientation scored at most 0.815 while the right
one always won by at least 0.122, so the second orientation is skipped only
when the first already scores >= ORIENTATION_SKIP_SCORE.
"""
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
from card_geometry import GeometryRefiner
import settings
from util import quad_iou  # noqa: F401  (vision_onnx.quad_iou, used here and by tests)
# Split out on 02/10/2026; the names stay importable from here.
from onnx_models import (DEVICE, ENCODER_VARIANT, IMAGENET_MEAN, IMAGENET_STD, MODELS, Detector, Encoder,  # noqa: F401
                         crop, encoder_path, providers, session, tensor, with_features)
from reference_index import build_index, index_paths, previous_index, reference_entries, references_digest  # noqa: F401
from promotions import ART_PROMOTION_MAX_AGE_S, ART_PROMOTION_MIN_IOU, NAME_MEMORY_S, promote_by_art, promote_by_name  # noqa: F401

ROOT=settings.ROOT
PILOT=settings.PILOT
# Reference scope: 'pilot' (the <=50 cards chosen in the catalog, default) or
# 'full' (every catalog identity with a usable image, catalog.export_full into
# data/full). Photos enrolled with enroll_reference.py live in the pilot folder
# and join either scope.
SCOPE=settings.SCOPE
REFS=settings.REFS
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
# Detector OBB against a tracked quadrilateral: an upright rectangle around a
# card in mild perspective still overlaps it well above this.
TRACKED_GEOMETRY_MIN_IOU=.75
UNRESOLVED_RETRY_S=2.
UNRESOLVED_MIN_IOU=.85


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
        # Frame-wide edge evidence (~60 ms at 1080p) only when a box needs refining: with every card
        # tracked (the usual live case) nothing would read it.
        refined=dict(zip(pending,GeometryRefiner(image).refine_all([boxes[i]['corners'] for i in pending],snap=snap))) if pending else {}
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
                result.append(detection(box,geometry,quad,rotation,track['card_id'],float(track.get('score',0.)),float(track.get('margin',0.)),True,top,'track',
                                        reuse_iou=round(iou,3),track_id=track.get('track_id')))
                continue
            score,rotation,top=identified[index]
            if not top:
                # Empty index or no classifier mapping: report the box, never an identity.
                result.append(detection(box,geometry,quad,rotation,None,0.,0.,False,[],'none'))
                continue
            margin=top[0]['score']-(top[1]['score'] if len(top)>1 else 0)
            accepted=bool(top[0]['card_id']) and top[0]['score']>=minimum and margin>=margin_floor
            result.append(detection(box,geometry,quad,rotation,top[0]['card_id'],top[0]['score'],margin,accepted,top,
                                    'embedding' if self.mode=='embedding' else 'classifier',acceptance='score' if accepted else None))
        return {'detections':result,'processing_ms':round((time.perf_counter()-started)*1000,1),'mode':self.mode,
                'experimental_thresholds':True,'geometry_ms':geometry_ms,'encoded_cards':encoded,'reused_cards':len(reused),'outside_regions':outside}


def detection(box,geometry,quad,rotation,card_id,score,margin,accepted,top5,source,**extra):
    """One contracts.Detection: `quad` the refined corners and `rotation` the quarter turns that
    make the card upright (both corner sets are rolled by it)."""
    return {'card_id':card_id,'corners':np.roll(quad,-rotation,axis=0).tolist(),'score':score,
            'detector_corners':np.roll(box['corners'],-rotation,axis=0).tolist(),
            'geometry_status':geometry['geometry_status'],'geometry_iou':geometry.get('geometry_iou'),
            'margin':margin,'accepted':accepted,'top5':top5,'rotation':rotation*90,'detector_score':box['score'],
            'identity_source':source,**extra}


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
        self.map_auto_sprites()
        for ref in self.references:
            self.cards.setdefault(ref['card_id'],ref)
            self.references_by_id.setdefault(ref['id'],ref)

    def map_auto_sprites(self):
        """Cards without a TDOANE sprite use their automatic cut-out when research/auto_cutout.py
        made one. Re-run when data/auto-sprites changes: new cards gain a sprite, removed ones lose it."""
        auto=ROOT/'data/auto-sprites'
        try: self.auto_signature=(auto/'index.json').stat().st_mtime_ns
        except OSError: self.auto_signature=None
        made={p.name for p in auto.glob('*.png')} if auto.exists() else set()
        for ref in self.references:
            if (ref.get('sprite_ref') or '').startswith('auto:'): ref.pop('sprite_ref')
            if not ref.get('sprite_ref') and ref.get('source'):
                name=Path(ref['source']).stem+'.png'
                if name in made: ref['sprite_ref']='auto:'+name

    def refresh_auto_sprites(self):
        try: signature=(ROOT/'data/auto-sprites'/'index.json').stat().st_mtime_ns
        except OSError: signature=None
        if signature==getattr(self,'auto_signature',None): return False
        self.map_auto_sprites(); return True

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
        if not reloaded: self.refresh_auto_sprites()
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
            faces=[tuple(np.float32(d['corners']).mean(0)) for d in result['detections']]
            scores=self.backs.check(image,back_zones,faces=faces)
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
        # Title evidence is remembered where it was read: the OCR worker reads a few cards per
        # batch, and a promotion that needed a fresh reading every 4 s flickered on and off.
        now=time.time();memory=getattr(self,'name_memory',[])
        for item in verified:
            if item.get('evidence')!='name': continue
            memory=[m for m in memory if quad_iou(m['corners'],item['corners'])<ART_PROMOTION_MIN_IOU]+[item]
        self.name_memory=[m for m in memory if 0<=now-m.get('captured_at',0)<=NAME_MEMORY_S]
        result['name_promoted']=promote_by_name(result['candidates'],self.name_memory,now,max_age=NAME_MEMORY_S)
        result['detections']=[self.describe(c) for c in result['candidates'] if c['accepted']]
        result.update(width=image.shape[1],height=image.shape[0])
        return result


if __name__=='__main__':
    build_index()
