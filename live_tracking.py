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
from util import quad_iou  # noqa: F401  (live_tracking.quad_iou)

GRID=(5,7)
LK=dict(winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,20,.03))
from contracts import IDENTITY_FIELDS  # noqa: E402  (live_tracking.IDENTITY_FIELDS)
# Live measurement 27/09/2026: ten cards on a 1080p phone stream cost ~100 ms per
# frame when each card ran its own Lucas-Kanade calls (pyramids rebuilt per
# card). Now all cards share one forward and one backward call (~7 ms for 350
# points), JPEG decoding is the floor (~14 ms at 1080p), and frames are skipped
# while the tracker is behind so it never takes more than about half of the
# reader thread. Lighter parameters (15 px window, 2 levels, 4x6 grid) saved
# only 5 ms and doubled the corner error on the ten-card probe; not worth it.


def grid_points(corners):
    """Interior sample points of a quadrilateral, away from the border."""
    src=np.float32([[0,0],[1,0],[1,1],[0,1]]);matrix=cv2.getPerspectiveTransform(src,np.float32(corners))
    u=np.linspace(.12,.88,GRID[0]);v=np.linspace(.1,.9,GRID[1])
    unit=np.float32([[x,y] for y in v for x in u]).reshape(-1,1,2)
    return cv2.perspectiveTransform(unit,matrix).reshape(-1,2)


class LiveTracker:
    def __init__(self,width=640,history=45,min_inliers=8,max_silent_s=2.5,max_load=.5):
        self.lock=threading.Lock();self.width=width;self.min_inliers=min_inliers;self.max_silent_s=max_silent_s;self.max_load=max_load
        self.frames=deque(maxlen=history)  # (captured_at, grey, scale)
        # Track ids become the duel's copy_ids and the duel survives restarts: start each run
        # at a new number (milliseconds) so a fresh track never reuses a card's id from the saved duel.
        self.tracks={};self.next_id=int(time.time()*1000);self.frame_count=0;self.skipped=0;self.last_update_ms=0.;self.next_allowed=0.

    # --- frames ---------------------------------------------------------------
    def decode(self,jpeg):
        # Phone frames are 1080p or more: let the JPEG decoder produce a half or
        # quarter size image directly instead of decoding full size and resizing.
        header=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_REDUCED_GRAYSCALE_2)
        if header is None:return None,1.
        image=header;factor=2.
        if image.shape[1]>=2*self.width:
            quarter=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_REDUCED_GRAYSCALE_4)
            if quarter is not None:image=quarter;factor=4.
        if image.shape[1]*factor<self.width:
            # Small frames (tests, thumbnails): full decode keeps enough detail.
            full=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_GRAYSCALE)
            if full is None:return None,1.
            image=full;factor=1.
        original_w=image.shape[1]*factor;original_h=image.shape[0]*factor
        s=min(1.,self.width/original_w)  # small-image pixels per original pixel
        target=(round(original_w*s),round(original_h*s))
        small=cv2.resize(image,target,interpolation=cv2.INTER_AREA) if target!=(image.shape[1],image.shape[0]) else image
        return small,small.shape[1]/original_w

    def update(self,jpeg,captured_at):
        """Advance every track to this frame. Returns the number of live tracks.

        Skips frames while the previous update is still "paying for itself":
        after an update of t seconds the next frame is accepted only when its
        capture time is t/max_load later, so tracking never monopolises the
        stream reader thread. Capture time, not wall clock: tests replay
        recorded frames faster than real time.
        """
        started=time.perf_counter()
        if self.tracks and captured_at<self.next_allowed:
            self.skipped+=1;return len(self.tracks)
        grey,scale=self.decode(jpeg)
        if grey is None:return len(self.tracks)
        with self.lock:
            if self.frames and captured_at<=self.frames[-1][0]:return len(self.tracks)
            previous=self.frames[-1] if self.frames else None
            self.frames.append((captured_at,grey,scale));self.frame_count+=1
            if previous is not None:self._flow(previous[1],grey,captured_at,scale)
            elapsed=time.perf_counter()-started
            self.last_update_ms=round(elapsed*1000,1);self.next_allowed=captured_at+elapsed/self.max_load
            return len(self.tracks)

    def _flow(self,prev_grey,grey,captured_at,scale):
        if not self.tracks:return
        # One forward and one backward Lucas-Kanade call for every card at once:
        # the pyramids are built once per frame instead of once per card.
        keys=list(self.tracks);seeds=[];spans=[]
        for key in keys:
            pts=grid_points(np.float32(self.tracks[key]['corners'])*scale)
            spans.append((len(seeds),len(seeds)+len(pts)));seeds.extend(pts)
        seeds=np.float32(seeds).reshape(-1,1,2)
        moved,status,_=cv2.calcOpticalFlowPyrLK(prev_grey,grey,seeds,None,**LK)
        back,status_back,_=cv2.calcOpticalFlowPyrLK(grey,prev_grey,moved,None,**LK)
        ok_all=(status.ravel()==1)&(status_back.ravel()==1)&(np.linalg.norm((back-seeds).reshape(-1,2),axis=1)<1.5)
        h,w=grey.shape[:2];dead=[]
        for key,(a,b) in zip(keys,spans):
            track=self.tracks[key];ok=ok_all[a:b]
            if ok.sum()<self.min_inliers:dead.append(key);continue
            src=seeds[a:b][ok].reshape(-1,2);dst=moved[a:b][ok].reshape(-1,2)
            matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,2.5)
            if matrix is None or mask is None or int(mask.sum())<self.min_inliers:dead.append(key);continue
            points=np.float32(track['corners'])*scale
            corners=cv2.perspectiveTransform(points.reshape(-1,1,2),matrix).reshape(-1,2)
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
            # The replay may already have lost a card that left the frame since the analysis.
            return [self.tracks[k] for k in fresh if k in self.tracks]

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
