"""Asynchronous rectified passcode crops, conservative OCR and exact registry lookup."""
import base64,hashlib,json,re,sqlite3,threading,time,unicodedata
from collections import deque
from pathlib import Path
import cv2
import numpy as np
from card_geometry import GeometryRefiner
from name_ocr import NAME_REGION,TitleReader,mark_conflicts,pick_by_name
from set_ocr import SetReader
from card_evidence import EvidenceSession,describe
from identity_resolution import IDENTITIES,canonical

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data/registry/registry.sqlite'
SIZE=(630,920)
REGIONS={'tight':(0,.970,.28,1.0),'wide':(0,.948,.49,1.0)}

def png(image):
    return 'data:image/png;base64,'+base64.b64encode(cv2.imencode('.png',image)[1]).decode('ascii')

def numbers(text):
    text=unicodedata.normalize('NFKC',text).strip()
    # Keep leading zeroes. No fuzzy edits, O->0 substitution or partial padding.
    found=re.findall(r'(?<![\w])([0-9]{8})(?![0-9])',text)
    if re.fullmatch(r'[0-9\s]+',text) and len(re.sub(r'\s','',text))==8:
        found.append(re.sub(r'\s','',text))
    return sorted(set(found))

def rectify(image,corners):
    points=np.asarray(corners,dtype=np.float32)
    if points.shape!=(4,2) or not np.isfinite(points).all() or not cv2.isContourConvex(points):
        raise ValueError('Esquinas inválidas')
    height,width=image.shape[:2]
    if (points[:,0]<0).any() or (points[:,0]>=width).any() or (points[:,1]<0).any() or (points[:,1]>=height).any():
        raise ValueError('Carta cortada por el borde de la imagen')
    if cv2.contourArea(points)<400: raise ValueError('Carta demasiado pequeña')
    native_width=float((np.linalg.norm(points[1]-points[0])+np.linalg.norm(points[2]-points[3]))/2)
    native_height=float((np.linalg.norm(points[3]-points[0])+np.linalg.norm(points[2]-points[1]))/2)
    dst=np.float32([[0,0],[SIZE[0]-1,0],[SIZE[0]-1,SIZE[1]-1],[0,SIZE[1]-1]])
    matrix=cv2.getPerspectiveTransform(points,dst)
    return cv2.warpPerspective(image,matrix,SIZE,flags=cv2.INTER_CUBIC),native_width,native_height

def region(image,box):
    h,w=image.shape[:2];x0,y0,x1,y1=box
    return image[round(y0*h):round(y1*h),round(x0*w):round(x1*w)].copy()

def open_registry(db_path=DB):
    """Read-only connection, or None while the registry has not been built."""
    if not db_path.exists(): return None
    return sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True,timeout=1)

def lookup(code,db_path=DB,db=None):
    owned=db is None
    if owned:
        db=open_registry(db_path)
        if db is None: return []
    try:
        ids=[r[0] for r in db.execute("SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?",(code,))]
        out=[]
        for uid in ids:
            if not IDENTITIES.allows(uid,'passcode',code):continue
            row=db.execute("SELECT name FROM names WHERE card_id=? AND language IN ('es','en') ORDER BY CASE language WHEN 'es' THEN 0 ELSE 1 END,CASE WHEN source LIKE 'neuron:%' THEN 0 ELSE 1 END LIMIT 1",(uid,)).fetchone()
            out.append({'card_id':uid,'name':row[0] if row else uid})
        return IDENTITIES.merge(out)
    finally:
        if owned: db.close()

class NumberReader:
    def __init__(self):
        from rapidocr import RapidOCR
        self.engine=RapidOCR(params={'Global.log_level':'error','Global.use_det':False,'Global.use_cls':False,
            'EngineConfig.onnxruntime.intra_op_num_threads':1,'EngineConfig.onnxruntime.inter_op_num_threads':1})
        self.title_reader=TitleReader(self.engine)
        self.set_reader=SetReader(self.engine)

    def read_set(self,rectified):
        return self.set_reader.read(rectified)

    def read_name(self,rectified):
        return self.title_reader.read(rectified)

    def read(self,rectified):
        observations=[]
        for turns in (0,2):
            oriented=np.ascontiguousarray(np.rot90(rectified,turns))
            for name in ('tight','wide','contrast'):
                crop=region(oriented,REGIONS['tight' if name=='tight' else 'wide'])
                if name=='contrast':
                    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
                    crop=cv2.cvtColor(cv2.createCLAHE(2.0,(4,2)).apply(gray),cv2.COLOR_GRAY2BGR)
                # Explicit text-line OCR: no global text detector or database hints.
                result=self.engine(crop,use_det=False,use_cls=False,use_rec=True)
                for text,score in zip(result.txts or [],result.scores or []):
                    observations.append({'text':text,'score':round(float(score),4),'variant':name,'orientation':turns*90,
                        'numbers':numbers(text)})
        choices={}
        for obs in observations:
            for code in obs['numbers']:
                if code not in choices or obs['score']>choices[code]['score']:
                    choices[code]={'passcode':code,**obs}
        ranked=sorted(choices.values(),key=lambda x:-x['score'])
        best=ranked[0] if ranked else None
        ambiguous=len(ranked)>1 and ranked[0]['score']-ranked[1]['score']<.08
        return best,ambiguous,observations

class Consensus:
    def __init__(self): self.tracks={};self.next_id=1

    def update(self,items,frame_hash,now=None):
        now=time.monotonic() if now is None else now
        available={k:v for k,v in self.tracks.items() if now-v['seen']<15}
        current={}
        for item in items:
            item_hash=item.get('ocr_image_hash',frame_hash)
            points=np.float32(item['corners']);center=points.mean(axis=0);size=max(np.linalg.norm(points[0]-points[2]),1)
            distances=sorted((float(np.linalg.norm(center-v['center'])/size),k) for k,v in available.items()
                if item.get('evidence_track_id') is None or item.get('evidence_track_id')==v.get('evidence_track_id'))
            if distances and distances[0][0]<.3 and (len(distances)==1 or distances[1][0]-distances[0][0]>.08):
                key=distances[0][1];track=available.pop(key)
            else:
                key=self.next_id;self.next_id+=1;track={'votes':deque(maxlen=5)}
            code=item.get('passcode')
            qualified=bool(code and item.get('ocr_score',0)>=.85 and not item.get('ambiguous') and item.get('estimated_digit_height',0)>=7)
            if not qualified:
                track['votes'].clear()
            elif not item.get('ocr_reused') and (not track['votes'] or track['votes'][-1][0]!=item_hash):
                if track['votes'] and track['votes'][-1][1]!=code: track['votes'].clear()
                track['votes'].append((item_hash,code))
            votes=len({h for h,c in track['votes'] if c==code})
            matches=item.get('matches',[])
            visual=canonical(item.get('visual_card_id'))
            conflict=bool(visual and matches and all(m['card_id']!=visual for m in matches))
            if item.get('ambiguous'): state='ambiguous_reading'
            elif not code: state='unreadable'
            elif not matches: state='not_in_registry'
            elif len(matches)>1: state='ambiguous_identity'
            elif conflict: state='visual_conflict'
            elif votes>=2: state='repeated_match'
            else: state='candidate'
            item.update(track_id=key,consistent_frames=votes,status=state,visual_conflict=conflict)
            track.update(center=center,seen=now,evidence_track_id=item.get('evidence_track_id'));current[key]=track
        self.tracks=current
        return items

class PasscodeWorker:
    """One active job and one replaceable pending job; no growing video queue."""
    def __init__(self,reader_factory=NumberReader,min_digit_height=7,verifier_factory=None):
        self.condition=threading.Condition();self.pending=None;self.result={'state':'loading','items':[]}
        self.closed=False;self.sequence=0;self.consensus=Consensus();self.reader_factory=reader_factory
        # Artwork verification is optional evidence; a missing reference set
        # must not make the text reader unavailable.
        if verifier_factory is None:
            from art_verify import ArtVerifier
            verifier_factory=ArtVerifier
        self.verifier_factory=verifier_factory if verifier_factory else None
        self.min_digit_height=min_digit_height;self.batch_offset=0;self.unavailable=False
        self.evidence=EvidenceSession()
        self.thread=threading.Thread(target=self.run,name='passcode-ocr',daemon=True);self.thread.start()

    def submit(self,jpeg,boxes,captured_at=None):
        with self.condition:
            if self.closed or self.unavailable:return False
            self.sequence+=1
            self.pending=(self.sequence,jpeg,boxes,captured_at if captured_at is not None else time.time())
            self.condition.notify()
            return True

    def snapshot(self):
        with self.condition:
            return {**self.result,'pending':self.pending is not None}

    def verified(self):
        """Cards whose illustration the verifier matched in the latest batch.

        Evidence for vision_onnx.promote_by_art: corners of the analysed frame,
        the verified identity and when that frame was captured. Never carries
        candidates the verifier rejected or found ambiguous.
        """
        with self.condition:
            result=self.result
        out=[]
        for item in result.get('items',[]):
            pick=item.get('name_pick')
            if pick and item.get('corners'):
                # Title evidence (vision_onnx.promote_by_name), kept apart from artwork evidence.
                out.append({'corners':item['corners'],'card_id':pick['card_id'],'evidence':'name','similarity':pick['similarity'],
                            'text':pick.get('text'),'captured_at':result.get('captured_at'),'evidence_track_id':item.get('evidence_track_id')})
            art=item.get('art_match') or {}
            if art.get('status')!='matched' or not art.get('card_id') or not item.get('corners'):continue
            best=(art.get('matches') or [{}])[0]
            out.append({'corners':item['corners'],'card_id':art['card_id'],'artwork_id':best.get('artwork_id'),'inliers':best.get('inliers'),
                        'captured_at':result.get('captured_at'),'evidence_track_id':item.get('evidence_track_id')})
        return out

    def close(self):
        with self.condition:self.closed=True;self.pending=None;self.condition.notify()

    def run(self):
        try: reader=self.reader_factory()
        except Exception as e:
            with self.condition:
                self.unavailable=True;self.pending=None
                self.result={'state':'unavailable','error':str(e),'items':[]}
            return
        verifier=None
        if self.verifier_factory:
            try:verifier=self.verifier_factory()
            except Exception:verifier=None
        with self.condition:self.result={'state':'ready','items':[]}
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.pending is not None or self.closed)
                if self.closed:return
                sequence,jpeg,boxes,captured=self.pending;self.pending=None
            started=time.monotonic();registry=None
            try:
                image=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
                if image is None: raise ValueError('JPEG inválido')
                items=[]
                # Rotate through large batches, rather than permanently excluding later cards.
                offset=self.batch_offset%len(boxes) if len(boxes)>6 else 0
                selected=(boxes[offset:]+boxes[:offset])[:6]
                self.batch_offset=offset+len(selected)
                refiner=GeometryRefiner(image) if any(not b.get('geometry_status') for b in selected) else None
                prepared=[]
                for box in selected:
                    item={'corners':box['corners'],'visual_card_id':canonical(box.get('visual_card_id')),'visual_name':box.get('name'),
                          'source_visual_card_id':box.get('source_visual_card_id',box.get('visual_card_id')),
                          'name_ocr':{'status':'skipped','reason':'uncertain_geometry'},
                          'set_ocr':{'status':'skipped','reason':'uncertain_geometry'}}
                    try:
                        geometry=box if box.get('geometry_status') else refiner.refine(box['corners'])
                        item.update(geometry_status=geometry['geometry_status'],geometry_iou=geometry.get('geometry_iou'))
                        if geometry['geometry_status']=='contour_refined':
                            item['corners']=geometry['corners']
                            corrected,nw,nh=rectify(image,item['corners'])
                            item['_rectified']=(corrected,nw,nh)
                            item['ocr_image_hash']=hashlib.sha256(corrected.tobytes()).hexdigest()
                            item['_appearance'],item['frame_quality']=describe(corrected,nh)
                    except ValueError:pass
                    prepared.append(item)
                self.evidence.associate(prepared,captured)
                frame_hash=hashlib.sha256(jpeg).hexdigest()
                for box,item in zip(selected,prepared):
                    with self.condition:
                        if self.closed:return
                    cached=self.evidence.cached(item,captured,frame_hash)
                    if cached is not None:
                        items.append(cached);continue
                    try:
                        if '_rectified' not in item:
                            item['ocr_skipped']='uncertain_geometry'
                            raise ValueError('No hay cuatro bordes fiables: muestra la carta completa y separada de las otras. Recorte y OCR omitidos.')
                        rectified,native_width,native_height=item.pop('_rectified')
                        # Upscaling cannot create readable pixels. Keep the zoom,
                        # but avoid six OCR passes below the existing confirmation gate.
                        too_small=native_height*.015<self.min_digit_height
                        best,ambiguous,observations=(None,False,[]) if too_small else reader.read(rectified)
                        if best and registry is None: registry=open_registry()
                        # One connection per batch; the registry may still be absent.
                        serial_matches=lookup(best['passcode'],db=registry) if best and registry is not None else []
                        title_started=time.monotonic()
                        # Titles from 240 px card height: a 308 px Ghost Rare Naturia Barkion read as
                        # "NČHIRIA BARKION" (0.91). A misread small title cannot pass pick_by_name.
                        if native_height*.025<6:
                            title={'status':'skipped','reason':'small_text'}
                        elif not hasattr(reader,'read_name'):
                            title={'status':'skipped','reason':'reader_unavailable'}
                        else:
                            try:title=reader.read_name(rectified)
                            except Exception as exc:title={'status':'error','error':str(exc)}
                        title['processing_ms']=round((time.monotonic()-title_started)*1000)
                        serial_qualified=bool(best and best['score']>=.85 and not ambiguous)
                        item['name_ocr']=mark_conflicts(title,box.get('visual_card_id'),serial_matches,serial_qualified)
                        # Second vote for cards the recognizer did not accept: the title names one of its
                        # own candidates (name_ocr.pick_by_name). Evidence only; vision_onnx decides.
                        title_reader=getattr(reader,'title_reader',None)
                        if not box.get('visual_card_id') and title_reader is not None and title.get('text') and (title.get('score') or 0)>=.7:
                            pick=pick_by_name(title_reader.registry,title['text'],box.get('candidate_ids') or [])
                            if pick:item['name_pick']={**pick,'text':title['text'],'ocr_score':title.get('score')}
                        if native_height*.015<7:
                            item['set_ocr']={'status':'skipped','reason':'small_text'}
                        elif hasattr(reader,'read_set'):
                            try:item['set_ocr']=reader.read_set(rectified)
                            except Exception as exc:item['set_ocr']={'status':'error','error':str(exc)}
                        else:item['set_ocr']={'status':'skipped','reason':'reader_unavailable'}
                        # Independent check of the illustration against the candidates
                        # proposed by the recognizer (accepted identity first).
                        proposals=[c for c in [box.get('visual_card_id'),*(box.get('candidate_ids') or [])[:3]] if c]
                        if verifier is None:item['art_match']={'status':'skipped','reason':'verifier_unavailable'}
                        elif native_height<120:item['art_match']={'status':'skipped','reason':'small_card'}
                        else:
                            try:item['art_match']=verifier.verify(rectified,proposals)
                            except Exception as exc:item['art_match']={'status':'error','error':str(exc)}
                        orientation=best['orientation'] if best else 0
                        # Title orientation may orient the preview only when its
                        # independent registry match is unambiguous and consistent.
                        if not serial_qualified and title['status']=='matched':orientation=title['orientation']
                        oriented=np.ascontiguousarray(np.rot90(rectified,orientation//90))
                        roi=region(oriented,REGIONS['wide'])
                        name_roi=region(oriented,NAME_REGION)
                        orientation_uncertain=(not box.get('visual_card_id') or bool(best and (ambiguous or best['score']<.85))) and title['status']!='matched'
                        alternative_name=region(np.ascontiguousarray(np.rot90(oriented,2)),NAME_REGION) if orientation_uncertain else None
                        preview=oriented.copy()
                        x0,y0,x1,y1=REGIONS['wide']
                        cv2.rectangle(preview,(int(x0*SIZE[0]),int(y0*SIZE[1])),(int(x1*SIZE[0]),int(y1*SIZE[1])),(30,220,255),3)
                        nx0,ny0,nx1,ny1=NAME_REGION
                        cv2.rectangle(preview,(int(nx0*SIZE[0]),int(ny0*SIZE[1])),(int(nx1*SIZE[0]),int(ny1*SIZE[1])),(200,180,60),3)
                        item.update(passcode=best['passcode'] if best else None,ocr_score=best['score'] if best else None,
                            ambiguous=ambiguous,raw_observations=observations,orientation=orientation,
                            ocr_skipped='small_text' if too_small else None,
                            crop=png(roi),rectified=png(cv2.resize(preview,(189,276))),
                            crop_alternative=png(region(np.ascontiguousarray(np.rot90(oriented,2)),REGIONS['wide'])) if orientation_uncertain else None,
                            name_crop=png(name_roi),name_crop_alternative=png(alternative_name) if alternative_name is not None else None,
                            name_orientation_uncertain=orientation_uncertain,
                            native_card_width=round(native_width),native_card_height=round(native_height),estimated_digit_height=round(native_height*.015,1),
                            matches=serial_matches)
                        item['quality_hint']='OCR del serial omitido: acerca la carta; los dígitos tienen pocos píxeles reales.' if too_small else 'Mantén la carta quieta, completa y sin reflejos.'
                    except ValueError as e:item.update(passcode=None,matches=[],quality_hint=str(e))
                    items.append(item)
                items=self.evidence.finish(items,captured,frame_hash)
                items=self.consensus.update(items,frame_hash)
                payload={'state':'ready','identity_resolution':IDENTITIES.info(),'sequence':sequence,'captured_at':captured,'completed_at':time.time(),
                    'processing_ms':round((time.monotonic()-started)*1000),'items':items,'detected_cards':len(boxes),'processed_cards':len(items)}
            except Exception as e:payload={'state':'error','sequence':sequence,'error':str(e),'items':[]}
            finally:
                if registry is not None: registry.close()
            with self.condition:self.result=payload
