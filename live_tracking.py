"""Corner tracking between full analyses, so AR follows the card at video rate.

Each accepted detection becomes a track: a grid of points inside the card is
followed with pyramidal Lucas-Kanade on a downscaled grey frame and a RANSAC
homography moves the four corners. Tracks die when too few points survive or
the card leaves the frame. Identity never comes from here: `sync` copies it
from the recognizer, `verified_at` says how old that identity is, and the
recognizer decides (vision_onnx.REUSE_MAX_AGE_S) whether to trust it again.

Analyses arrive late: the corners refer to a frame already replaced by newer
ones. A short frame history lets `sync` place the corners on the analysed
frame and replay the flow up to the newest frame.
"""
import threading,time
from collections import deque
import cv2
import numpy as np

GRID=(5,7)
LK=dict(winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,20,.03))
IDENTITY_FIELDS=('card_id','name','sprite_ref','score','margin','rotation','top5','ref_id','artwork_id','id','acceptance','source_card_id')


def grid_points(corners):
    """Interior sample points of a quadrilateral, away from the border."""
    src=np.float32([[0,0],[1,0],[1,1],[0,1]]);matrix=cv2.getPerspectiveTransform(src,np.float32(corners))
    u=np.linspace(.12,.88,GRID[0]);v=np.linspace(.1,.9,GRID[1])
    unit=np.float32([[x,y] for y in v for x in u]).reshape(-1,1,2)
    return cv2.perspectiveTransform(unit,matrix).reshape(-1,2)


def quad_iou(a,b):
    a=np.float32(a);b=np.float32(b)
    inter=cv2.intersectConvexConvex(a,b)[0];union=cv2.contourArea(a)+cv2.contourArea(b)-inter
    return float(inter/union) if union>0 else 0.


class LiveTracker:
    def __init__(self,width=640,history=45,min_inliers=8,max_silent_s=2.5):
        self.lock=threading.Lock();self.width=width;self.min_inliers=min_inliers;self.max_silent_s=max_silent_s
        self.frames=deque(maxlen=history)  # (captured_at, grey, scale)
        self.tracks={};self.next_id=1;self.frame_count=0;self.last_update_ms=0.

    # --- frames ---------------------------------------------------------------
    def decode(self,jpeg):
        image=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_GRAYSCALE)
        if image is None:return None,1.
        scale=min(1.,self.width/image.shape[1])
        small=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else image
        return small,scale

    def update(self,jpeg,captured_at):
        """Advance every track to this frame. Returns the number of live tracks."""
        started=time.perf_counter()
        grey,scale=self.decode(jpeg)
        if grey is None:return len(self.tracks)
        with self.lock:
            if self.frames and captured_at<=self.frames[-1][0]:return len(self.tracks)
            previous=self.frames[-1] if self.frames else None
            self.frames.append((captured_at,grey,scale));self.frame_count+=1
            if previous is not None:self._flow(previous[1],grey,captured_at,scale)
            self.last_update_ms=round((time.perf_counter()-started)*1000,1)
            return len(self.tracks)

    def _flow(self,prev_grey,grey,captured_at,scale):
        dead=[]
        for key,track in self.tracks.items():
            points=(np.float32(track['corners'])*scale)
            seeds=grid_points(points).reshape(-1,1,2).astype(np.float32)
            moved,status,_=cv2.calcOpticalFlowPyrLK(prev_grey,grey,seeds,None,**LK)
            back,status_back,_=cv2.calcOpticalFlowPyrLK(grey,prev_grey,moved,None,**LK)
            ok=(status.ravel()==1)&(status_back.ravel()==1)&(np.linalg.norm((back-seeds).reshape(-1,2),axis=1)<1.5)
            if ok.sum()<self.min_inliers:dead.append(key);continue
            matrix,mask=cv2.findHomography(seeds[ok].reshape(-1,2),moved[ok].reshape(-1,2),cv2.RANSAC,2.5)
            if matrix is None or mask is None or int(mask.sum())<self.min_inliers:dead.append(key);continue
            corners=cv2.perspectiveTransform(points.reshape(-1,1,2),matrix).reshape(-1,2)
            h,w=grey.shape[:2]
            if not np.isfinite(corners).all() or not cv2.isContourConvex(np.float32(corners)) or cv2.contourArea(np.float32(corners))<200:dead.append(key);continue
            if (corners[:,0]<-w*.1).any() or (corners[:,0]>w*1.1).any() or (corners[:,1]<-h*.1).any() or (corners[:,1]>h*1.1).any():dead.append(key);continue
            track.update(corners=(corners/scale).tolist(),tracked_at=captured_at,inliers=int(mask.sum()),frames=track['frames']+1)
        for key in dead:self.tracks.pop(key,None)

    # --- analyses -------------------------------------------------------------
    def sync(self,detections,captured_at):
        """Adopt accepted detections (analysed-frame coordinates) and replay the flow to now."""
        with self.lock:
            index=next((i for i,(ts,_,_) in enumerate(self.frames) if ts>=captured_at),None)
            fresh=[]
            for d in detections:
                if not d.get('card_id') or not d.get('corners'):continue
                best=max(((quad_iou(d['corners'],t['corners']),k) for k,t in self.tracks.items() if t['card_id']==d['card_id']),default=(0.,None))
                key=best[1] if best[0]>=.4 else None
                if key is None:key=self.next_id;self.next_id+=1
                track={**self.tracks.get(key,{'frames':0,'created_at':captured_at}),'track_id':key,'corners':[list(map(float,p)) for p in d['corners']],
                       'verified_at':captured_at,'tracked_at':captured_at,'inliers':None,'stable':bool(d.get('stable'))}
                for field in IDENTITY_FIELDS:
                    if field in d:track[field]=d[field]
                self.tracks[key]=track;fresh.append(key)
            # Tracks the analysis did not confirm are kept only while they were seen recently.
            for key in [k for k,t in self.tracks.items() if k not in fresh and captured_at-t['verified_at']>self.max_silent_s]:
                self.tracks.pop(key)
            if index is not None:
                frames=list(self.frames)
                for (ts_a,grey_a,scale),(ts_b,grey_b,_) in zip(frames[index:],frames[index+1:]):
                    self._flow(grey_a,grey_b,ts_b,scale)
            return [self.tracks[k] for k in fresh]

    def snapshot(self,now=None):
        now=time.time() if now is None else now
        with self.lock:
            return [{k:v for k,v in t.items()} for t in self.tracks.values()]

    def reuse_candidates(self,captured_at,max_age):
        """Tracks fresh enough for the recognizer to keep their identity without encoding."""
        with self.lock:
            return [dict(t) for t in self.tracks.values() if t.get('card_id') and 0<=captured_at-t['verified_at']<=max_age and t.get('stable')]

    def clear(self):
        with self.lock:self.tracks.clear();self.frames.clear()
