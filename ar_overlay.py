"""Conservative temporal IDs and a planar sprite overlay using card geometry."""
import time
from collections import OrderedDict
import cv2
import numpy as np
from catalog import connect,asset_path


class Tracker:
    def __init__(self,max_age=10):
        self.tracks={};self.next_id=1;self.max_age=max_age

    def update(self,detections,now=None):
        now=time.monotonic() if now is None else now
        available={k:v for k,v in self.tracks.items() if now-v['time']<self.max_age}
        current={}
        for detection in detections:
            identity=detection.get('card_id') or detection.get('id')
            if identity is None:
                detection.update(stable=False)
                continue
            corners=np.float32(detection['corners']);center=corners.mean(axis=0)
            size=max(np.linalg.norm(corners[0]-corners[2]),1)
            options=[(np.linalg.norm(center-v['center'])/size,k) for k,v in available.items() if v['identity']==identity]
            distance,key=min(options) if options else (float('inf'),None)
            ambiguous=len(options)>1 and sorted(options)[1][0]-distance<.10
            if distance<.35 and not ambiguous:
                previous=available.pop(key)
                hits=previous['hits']+1
            else:
                key=self.next_id;self.next_id+=1;hits=1
            current[key]={'identity':identity,'center':center,'time':now,'hits':hits}
            detection.update(track_id=key,stable=hits>=2)
        # An absent object is not propagated; reappearance must be confirmed anew.
        self.tracks=current
        return detections


class SpriteOverlay:
    def __init__(self,prepared_limit=16):
        if prepared_limit<1: raise ValueError('prepared_limit must be positive')
        self.cache={}
        # 16 portrait canvases use at most 16.4 MB of additional pixel storage.
        self.prepared=OrderedDict();self.prepared_limit=prepared_limit

    def clear_cache(self,ref=None):
        """Invalidate after an asset update; cached source arrays are immutable.

        Missing or undecodable sprites are cached as None so a stable detection
        does not query the catalog on every frame; adding the asset later also
        requires clearing.
        """
        if ref is None:
            self.cache.clear();self.prepared.clear()
        else:
            self.cache.pop(ref,None);self.prepared.pop(ref,None)

    def prepared_canvas(self,ref,sprite):
        cached=self.prepared.get(ref)
        if cached is not None and cached[0] is sprite:
            self.prepared.move_to_end(ref)
            return cached[1]
        # Place the sprite within a portrait plane without stretching its aspect.
        canvas=np.zeros((610,420,4),np.uint8)
        h,w=sprite.shape[:2];scale=min(390/w,520/h)
        sw,sh=round(w*scale),round(h*scale)
        x,y=(420-sw)//2,(610-sh)//2
        canvas[y:y+sh,x:x+sw]=cv2.resize(sprite,(sw,sh))
        self.prepared[ref]=(sprite,canvas)
        self.prepared.move_to_end(ref)
        while len(self.prepared)>self.prepared_limit:
            self.prepared.popitem(last=False)
        return canvas

    def render(self,frame,detections,transparent=False):
        output=np.zeros((*frame.shape[:2],4),np.uint8) if transparent else frame.copy()
        composed_bounds=None
        for detection in detections:
            ref=detection.get('sprite_ref')
            if not ref or not detection.get('stable'): continue
            if ref not in self.cache:
                with connect() as conn:
                    row=conn.execute('SELECT * FROM refs WHERE ref_id=? AND kind=\'sprite\'',(ref,)).fetchone()
                self.cache[ref]=None if row is None else cv2.imdecode(np.frombuffer(asset_path(row).read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
            sprite=self.cache[ref]
            if sprite is None or sprite.ndim!=3 or sprite.shape[2]!=4: continue
            canvas=self.prepared_canvas(ref,sprite)
            matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[419,0],[419,609],[0,609]]),np.float32(detection['corners']))
            warped=cv2.warpPerspective(canvas,matrix,(frame.shape[1],frame.shape[0]))
            x,y,w,h=cv2.boundingRect(warped[:,:,3])
            bounds=(x,y,x+w,y+h) if w and h else None
            # Include prior transparent content to retain exactly the original
            # float/uint8 rounding for overlapping layers and previous pixels.
            if transparent and composed_bounds is not None:
                a,b,c,d=composed_bounds
                bounds=(min(x,a),min(y,b),max(x+w,c),max(y+h,d)) if bounds else composed_bounds
            if bounds is None: continue
            x,y,right,bottom=bounds
            composed_bounds=bounds
            foreground=warped[y:bottom,x:right]
            background=output[y:bottom,x:right]
            alpha=foreground[:,:,3:4].astype(np.float32)/255
            if transparent:
                previous=background[:,:,3:4].astype(np.float32)/255
                combined=alpha+previous*(1-alpha)
                rgb=(foreground[:,:,:3]*alpha+background[:,:,:3]*previous*(1-alpha))/np.maximum(combined,1e-8)
                output[y:bottom,x:right]=np.concatenate((rgb,combined*255),axis=2).clip(0,255).astype(np.uint8)
            else:
                output[y:bottom,x:right]=(foreground[:,:,:3]*alpha+background*(1-alpha)).astype(np.uint8)
        return output
