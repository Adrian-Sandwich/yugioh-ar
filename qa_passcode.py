"""OCR geometry, real pixels, exact identity lookup, consensus and nonblocking queue."""
import copy,json,threading,time
from pathlib import Path
import cv2,numpy as np
from passcode_ocr import ROOT,SIZE,rectify,numbers,lookup,NumberReader,Consensus,PasscodeWorker

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    out=QA_OUT/'passcode';out.mkdir(parents=True,exist_ok=True)
    assert numbers('00123456 1st Edition')==['00123456']
    assert numbers('0012 3456')==['00123456']
    assert numbers('1234567')==[] and numbers('123456789')==[] and numbers('O0123456')==[]
    matches=lookup('89631139');assert len(matches)==1 and 'Azules' in matches[0]['name']
    assert not lookup('89631140'),'An image ID must not be accepted as passcode evidence'
    reader=NumberReader()
    card=np.full((SIZE[1],SIZE[0],3),225,np.uint8)
    cv2.putText(card,'00123456',(8,910),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,0),2,cv2.LINE_AA)
    corners=np.float32([[300,60],[1050,130],[980,1000],[260,960]])
    matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[629,0],[629,919],[0,919]]),corners)
    photo=cv2.warpPerspective(card,matrix,(1400,1080))
    for shift in (0,2):
        corrected,w,h=rectify(photo,np.roll(corners,shift,axis=0));best,ambiguous,_=reader.read(corrected)
        assert best and best['passcode']=='00123456' and not ambiguous,(shift,best)
    best,_,_=reader.read(np.full((920,630,3),220,np.uint8));assert best is None,'Blank image produced a passcode'
    try:rectify(photo,[[-2,0],[100,0],[100,200],[0,200]])
    except ValueError:pass
    else:raise AssertionError('Clipped card accepted')
    fixture=json.loads((ROOT/'data/references/catalog.json').read_text(encoding='utf-8'))[0]
    image=cv2.imread(str((ROOT/'data/references'/fixture['source']).resolve()))
    rectified,_,_=rectify(image,fixture['corners']);best,ambiguous,raw=reader.read(rectified)
    assert best and best['passcode']=='89631139' and not ambiguous,best
    sample={'corners':corners.tolist(),'passcode':'89631139','ocr_score':.95,'ambiguous':False,'estimated_digit_height':12,'matches':matches,'visual_card_id':matches[0]['card_id']}
    def vote(c,key,now,**changes):return c.update([{**copy.deepcopy(sample),**changes}],key,now)[0]
    consensus=Consensus()
    assert vote(consensus,'same',0)['status']=='candidate'
    assert vote(consensus,'same',1)['consistent_frames']==1,'Same pixels counted twice'
    assert vote(consensus,'different',2)['status']=='repeated_match'
    assert vote(consensus,'third',3,visual_card_id='other-card')['status']=='visual_conflict'
    assert vote(consensus,'fourth',4,passcode=None,matches=[])['consistent_frames']==0
    assert vote(consensus,'fifth',5)['status']=='candidate'
    assert vote(consensus,'sixth',6,matches=matches*2)['status']=='ambiguous_identity'
    small=Consensus();vote(small,'a',0,estimated_digit_height=3)
    assert vote(small,'b',1,estimated_digit_height=3)['status']=='candidate'
    # Two physical copies at different locations must not accumulate each other's votes.
    copies=Consensus();second=copy.deepcopy(sample);second['corners']=(corners+[1400,0]).tolist()
    initial=copies.update([copy.deepcopy(sample),second],'a',0)
    assert initial[0]['track_id']!=initial[1]['track_id']
    assert all(x['consistent_frames']==1 for x in initial)
    started=threading.Event();release=threading.Event()
    class BlockingReader:
        calls=0
        def read(self,image,**_):
            self.calls+=1
            if self.calls==1:started.set();release.wait(5)
            return None,False,[]
    worker=PasscodeWorker(BlockingReader);jpeg=cv2.imencode('.jpg',photo)[1].tobytes();boxes=[{'corners':corners.tolist(),'geometry_status':'contour_refined'}]
    worker.submit(jpeg,boxes);assert started.wait(3)
    t=time.monotonic();worker.submit(jpeg,boxes);worker.submit(jpeg,boxes)
    assert time.monotonic()-t<.1,'Submission blocked camera inference'
    release.set();deadline=time.monotonic()+5
    while worker.snapshot().get('sequence')!=3 and time.monotonic()<deadline:time.sleep(.05)
    assert worker.snapshot().get('sequence')==3,'Queue did not keep newest job'
    worker.close()
    result={'status':'passed','real_passcode':best['passcode'],'real_ocr_score':best['score'],
        'checks':['projective rectification','180-degree orientation fallback','leading zeroes','blank rejection','clipped card rejection','real photograph reading','typed passcode lookup, not image IDs','distinct-frame consensus','conflict and ambiguity handling','small-text confirmation guard','separate physical copies','nonblocking latest-frame queue']}
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
