"""Corner tracking on a synthetic moving card: follows motion, dies when the card is gone."""
import json,time
from pathlib import Path
import cv2,numpy as np
from live_tracking import LiveTracker,grid_points
import vision_onnx

ROOT=Path(__file__).resolve().parent
W,H=1280,720

def scene(rng,card_corners,texture,background):
    frame=background.copy()
    matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[420,0],[420,610],[0,610]]),np.float32(card_corners))
    warped=cv2.warpPerspective(texture,matrix,(W,H));mask=cv2.warpPerspective(np.full((610,420),255,np.uint8),matrix,(W,H))
    frame[mask>0]=warped[mask>0]
    return cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,88])[1].tobytes()

def main():
    rng=np.random.default_rng(7)
    texture=rng.integers(0,256,(610,420,3),dtype=np.uint8);texture=cv2.GaussianBlur(texture,(5,5),0)
    background=rng.integers(90,140,(H,W,3),dtype=np.uint8);background=cv2.GaussianBlur(background,(31,31),0)
    base=np.float32([[300,150],[560,170],[540,540],[280,520]])
    def corners_at(i):
        angle=np.radians(1.2*i);c,s=np.cos(angle),np.sin(angle)
        centre=base.mean(0)+[9*i,4*i]
        return ((base-base.mean(0))@np.float32([[c,-s],[s,c]]).T+centre)
    tracker=LiveTracker()
    t0=time.time();frames=[(t0+i*.066,corners_at(i)) for i in range(28)]
    for ts,corners in frames[:4]:tracker.update(scene(rng,corners,texture,background),ts)
    assert tracker.snapshot()==[],'No tracks before an analysis'
    # The analysis refers to frame 1 (already superseded); sync must replay to frame 3.
    detection={'card_id':'card-a','name':'Carta A','sprite_ref':'sprite-a','corners':frames[1][1].tolist(),'stable':True,'score':.93,'rotation':0,'top5':[{'card_id':'card-a','score':.93}]}
    fresh=tracker.sync([detection],frames[1][0])
    assert len(fresh)==1 and fresh[0]['card_id']=='card-a'
    replayed=np.float32(tracker.snapshot()[0]['corners']);err=np.linalg.norm(replayed-frames[3][1],axis=1).max()
    assert err<6,f'replay to the newest frame drifted {err:.1f} px'
    errors=[]
    for ts,corners in frames[4:20]:
        tracker.update(scene(rng,corners,texture,background),ts)
        snap=tracker.snapshot();assert len(snap)==1,'track lost while the card is visible'
        errors.append(float(np.linalg.norm(np.float32(snap[0]['corners'])-corners,axis=1).max()))
    assert max(errors)<8,f'tracking error {max(errors):.1f} px'
    # Fresh enough to reuse the identity, then too old.
    assert tracker.reuse_candidates(frames[19][0],vision_onnx.REUSE_MAX_AGE_S)[0]['track_id']==fresh[0]['track_id']
    assert tracker.reuse_candidates(frames[19][0]+60,vision_onnx.REUSE_MAX_AGE_S)==[]
    # A second analysis confirms the same card: same track id, corners refreshed.
    again=tracker.sync([{**detection,'corners':frames[19][1].tolist()}],frames[19][0])
    assert again[0]['track_id']==fresh[0]['track_id'] and len(tracker.snapshot())==1
    # An analysis without the card, later than max_silent_s: the track is dropped.
    tracker.sync([],frames[19][0]+3);assert tracker.snapshot()==[],'unconfirmed old track kept'
    # Card removed from the scene: flow finds nothing to follow and the track dies.
    tracker.sync([{**detection,'corners':frames[19][1].tolist()}],frames[19][0]+3.01)
    for i in range(3):tracker.update(scene(rng,corners_at(19),texture,background) if i==0 else cv2.imencode('.jpg',background)[1].tobytes(),frames[19][0]+3.1+i*.066)
    assert tracker.snapshot()==[],'track survived the card disappearing'
    # A late analysis whose card already left: the replay kills the fresh track and sync must not crash (KeyError seen live 27/09).
    late=frames[19][0]+3.1
    fresh_late=tracker.sync([{**detection,'corners':corners_at(19).tolist()}],late)
    assert fresh_late==[] and tracker.snapshot()==[],'a track lost during replay must be reported as gone'
    # Sample points stay inside the quad.
    pts=grid_points(base);assert all(cv2.pointPolygonTest(base,(float(x),float(y)),False)>0 for x,y in pts)
    report={'status':'passed','frames':len(frames),'max_corner_error_px':round(max(errors),2),'replay_error_px':round(float(err),2),
            'last_update_ms':tracker.last_update_ms,'checks':['no tracks before analysis','late analysis replayed to newest frame','follows translation and rotation',
            'reuse freshness window','same track on re-confirmation','silent track dropped','track dies when card disappears','late sync after the card left does not crash','grid points inside quad'],
            'note':'Synthetic frames with a textured card on a smooth background; real cards, glare and hands are not covered.'}
    (ROOT/'research/qa/live-tracking.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
