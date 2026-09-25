"""Short-lived, conservative card association and independent evidence fusion."""
import copy
from collections import deque
import cv2
import numpy as np

def describe(image,native_height):
    small=cv2.resize(image,(32,48),interpolation=cv2.INTER_AREA)
    gray=cv2.cvtColor(cv2.resize(image,(315,460)),cv2.COLOR_BGR2GRAY)
    sharpness=float(cv2.Laplacian(gray,cv2.CV_32F).var())
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    # Proxy only: white artwork can also be bright and unsaturated.
    glare=float(np.mean((hsv[:,:,2]>245)&(hsv[:,:,1]<30)))
    score=float(np.log1p(sharpness)*min(native_height/600,1.5)*(1-.7*glare))
    return small,{'sharpness':round(sharpness,2),'bright_fraction':round(glare,4),'score':round(score,4)}

def compatible(a,b):
    pa=np.float32(a['corners']);pb=np.float32(b['corners'])
    sa=max(float(np.linalg.norm(pa[0]-pa[2])),1);sb=max(float(np.linalg.norm(pb[0]-pb[2])),1)
    if not .8<sa/sb<1.25:return False
    if np.linalg.norm(pa.mean(0)-pb.mean(0))/sa>.18:return False
    if a.get('visual_card_id')!=b.get('visual_card_id'):return False
    if a.get('_appearance') is None or b.get('_appearance') is None:return False
    distance=float(np.mean(np.abs(a['_appearance'].astype(float)-b['_appearance'].astype(float))))/255
    return distance<.055

def fuse(item):
    sources={}
    if item.get('visual_card_id'):sources['image']={item['visual_card_id']}
    if item.get('ocr_score') is not None and item['ocr_score']>=.85 and not item.get('ambiguous'):
        ids={m['card_id'] for m in item.get('matches',[])}
        if ids:sources['serial']=ids
    for field,label in (('name_ocr','name'),('set_ocr','set')):
        reading=item.get(field,{})
        if reading.get('status') in ('matched','conflict'):
            ids={m['card_id'] for m in reading.get('matches',[])}
            if ids:sources[label]=ids
    # Artwork verified by local features: visual evidence, independent of the
    # embedding, restricted to the candidates it was asked about.
    art=item.get('art_match',{})
    if art.get('status')=='matched' and art.get('card_id'):sources['art']={art['card_id']}
    intersection=set.intersection(*sources.values()) if sources else set()
    state='conflict' if sources and not intersection else 'candidate' if len(intersection)==1 else 'insufficient'
    return {'status':state,'card_id':next(iter(intersection)) if len(intersection)==1 else None,
            'sources':{k:sorted(v) for k,v in sources.items()},'agreeing_sources':len(sources)}

class EvidenceSession:
    """No matching across gaps, uncertain geometry, or competing associations."""
    def __init__(self):self.previous=[];self.next_id=1

    def associate(self,items,now):
        previous=[p for p in self.previous if 0<=now-p['_seen']<=3]
        edges=[[j for j,p in enumerate(previous) if compatible(i,p)] for i in items]
        for index,item in enumerate(items):
            matches=edges[index]
            unique=len(matches)==1 and sum(matches[0] in e for e in edges)==1
            old=previous[matches[0]] if unique else None
            if old:
                item['_track']=old['_track'];item['_history']=old['_history'];item['_best']=old.get('_best')
                item['_previous_capture']=old['_seen']
            else:
                item['_track']=self.next_id;self.next_id+=1;item['_history']=deque(maxlen=5);item['_best']=None
            item['_seen']=now

    def cached(self,item,captured,frame_hash):
        frame_hash=item.get('ocr_image_hash',frame_hash)
        best=item.get('_best')
        if not best or not 0<=captured-best['captured']<1.5:return None
        if best['hash']!=frame_hash and item['frame_quality']['score']>=best['quality']*.90:return None
        # Only reuse resolved, conflict-free evidence; retry unreadable frames.
        if best['item'].get('evidence',{}).get('status') not in ('candidate','corroborated','repeated'):return None
        if not any(k!='image' for k in best['item']['evidence']['sources']):return None
        out=copy.deepcopy(best['item'])
        out.update({k:v for k,v in item.items() if k.startswith('_')})
        out.update(corners=item['corners'],frame_quality=item['frame_quality'],ocr_reused=True,
                   evidence_captured_at=best['captured'],selection_reason='recent_better_frame')
        return out

    def finish(self,items,captured,frame_hash):
        for item in items:
            item_hash=item.get('ocr_image_hash',frame_hash)
            item['evidence_track_id']=item['_track']
            if not item.get('ocr_reused'):
                evidence=fuse(item);history=item['_history'];uid=evidence['card_id']
                # Visual-only identity (embedding, artwork features) never gains
                # confirmation from repetition; only text read from the card votes.
                qualifies=uid is not None and evidence['status']!='conflict' and any(k!='image' for k in evidence['sources'])
                textual=qualifies and any(k in ('serial','name','set') for k in evidence['sources'])
                if not textual or (history and history[-1][2]!=uid):history.clear()
                if textual and captured>item.get('_previous_capture',-float('inf')) and not any(h==item_hash or t==captured for h,t,c in history):history.append((item_hash,captured,uid))
                evidence['consistent_frames']=len(history)
                if textual and len(history)>=2:evidence['status']='repeated'
                elif qualifies and evidence['agreeing_sources']>=2:evidence['status']='corroborated'
                item.update(evidence=evidence,evidence_captured_at=captured,ocr_reused=False,selection_reason='current_frame')
                public={k:copy.deepcopy(v) for k,v in item.items() if not k.startswith('_')}
                item['_best']={'captured':captured,'hash':item_hash,'quality':item.get('frame_quality',{}).get('score',0),'item':public}
        self.previous=items
        return [{k:v for k,v in item.items() if not k.startswith('_')} for item in items]
