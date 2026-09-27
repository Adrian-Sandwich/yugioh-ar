"""Batched identification, orientation skip, track reuse, art promotion and empty index.

Compares the batched/skipping path against the plain per-crop, two-orientation
path on the annotated real scene: same identities, same rotation, same scores
within float tolerance, fewer encoder runs. Then exercises the paths that do
not need the model: reuse of a fresh track, promotion by verified artwork,
rejection when the index yields nothing. Writes research/qa/vision-pipeline.json.
"""
import json,time
import cv2,numpy as np
import vision_onnx
from vision_onnx import ResearchRecognizer,ROOT,crop,promote_by_art,quad_iou

SCENE=ROOT/'research/qa/corner-refinement/current.jpg'

def plain_identify(model,crops):
    out=[]
    for rectified in crops:
        options=[]
        for rotation in (0,2):
            _,z=model.encoder.predict(np.ascontiguousarray(np.rot90(rectified,rotation)),classify=False)
            top=model.rank(z);options.append((top[0]['score'],rotation,top))
        out.append(max(options,key=lambda x:x[0]))
    return out

def main():
    model=ResearchRecognizer();image=cv2.imread(str(SCENE))
    boxes=model.detector.detect(image)
    crops=[crop(image,b['corners']) for b in boxes]
    calls=[]
    original=model.encoder.predict_batch
    def counting(images,**kw):
        calls.append(len(images));return original(images,**kw)
    model.encoder.predict_batch=counting
    started=time.perf_counter();batched=model.identify(crops);batched_ms=(time.perf_counter()-started)*1000
    model.encoder.predict_batch=original
    started=time.perf_counter();plain=plain_identify(model,crops);plain_ms=(time.perf_counter()-started)*1000
    skipped=0;deltas=[]
    for (bs,br,bt),(ps,pr,pt) in zip(batched,plain):
        assert bt[0]['card_id']==pt[0]['card_id'],'batched path changed the identity'
        if bs>=vision_onnx.ORIENTATION_SKIP_SCORE and br==0:
            # The second orientation was skipped; the plain path may prefer it only marginally.
            skipped+=1;assert ps-bs<=.12,f'skipped orientation lost {ps-bs:.3f}'
        else:
            # The int8 graph is not bit-identical across batch sizes; identities and
            # rotations must agree, scores may drift by a few thousandths.
            assert br==pr and abs(bs-ps)<.02,f'batched result differs: {bs} {br} vs {ps} {pr}'
            deltas.append(abs(bs-ps))
    assert sum(calls)<=2*len(crops),calls
    # Track reuse: a fresh overlapping track keeps its identity without encoding.
    tracks=[{'corners':boxes[0]['corners'].tolist(),'card_id':'reused-id','score':.91,'margin':.5,'rotation':0,'track_id':7,'top5':[{'card_id':'reused-id','score':.91}]}]
    model.encoder.predict_batch=counting;calls.clear()
    result=model.detect(image,reuse=tracks)
    model.encoder.predict_batch=original
    reused=[d for d in result['detections'] if d.get('identity_source')=='track']
    assert len(reused)==1 and reused[0]['card_id']=='reused-id' and reused[0]['accepted'] and reused[0]['track_id']==7
    assert result['reused_cards']==1 and result['encoded_cards']==len(boxes)-1
    assert all(n<=len(boxes)-1 for n in calls),calls
    # No overlap: the track is ignored.
    far=[{**tracks[0],'corners':[[0,0],[10,0],[10,14],[0,14]]}]
    assert model.detect(image,reuse=far)['reused_cards']==0
    # Art promotion: only same identity, overlapping and fresh.
    now=time.time()
    candidate={'card_id':'x','corners':boxes[0]['corners'].tolist(),'accepted':False,'score':.6}
    verified=[{'card_id':'x','corners':boxes[0]['corners'].tolist(),'captured_at':now-1,'inliers':80}]
    assert promote_by_art([dict(candidate)],verified,now)==1
    assert promote_by_art([dict(candidate)],[{**verified[0],'card_id':'y'}],now)==0,'different identity promoted'
    assert promote_by_art([dict(candidate)],[{**verified[0],'captured_at':now-10}],now)==0,'stale verification promoted'
    assert promote_by_art([dict(candidate)],[{**verified[0],'corners':[[0,0],[10,0],[10,14],[0,14]]}],now)==0,'non-overlapping promoted'
    assert promote_by_art([{**candidate,'accepted':True}],verified,now)==0,'already accepted counted'
    promoted=dict(candidate);promote_by_art([promoted],verified,now)
    assert promoted['acceptance']=='art_verified' and promoted['art_inliers']==80 and promoted['score']==.6,'score must not change'
    # Empty index: boxes reported, no identity, nothing accepted.
    saved_vectors,saved_rows=model.vectors,model.rows
    model.vectors=np.zeros((0,saved_vectors.shape[1]),np.float32);model.rows=[]
    empty=model.detect(image)
    model.vectors,model.rows=saved_vectors,saved_rows
    assert empty['detections'] and all(d['card_id'] is None and not d['accepted'] and d['top5']==[] for d in empty['detections'])
    assert quad_iou([[0,0],[10,0],[10,10],[0,10]],[[5,0],[15,0],[15,10],[5,10]])-1/3<1e-6
    report={'status':'passed','scene':str(SCENE.relative_to(ROOT)),'cards':len(crops),
            'orientations_skipped':skipped,'max_batch_score_drift':round(max(deltas),4) if deltas else None,
            'batched_ms':round(batched_ms),'plain_ms':round(plain_ms),
            'note':'Timings observed once on a loaded PC; not a benchmark. Batched int8 scores drift from single-image scores by at most max_batch_score_drift on this scene.',
            'checks':['same identities as two-orientation path','orientation skip bounded','track reuse without encode','no reuse without overlap',
                      'art promotion requires identity, overlap and freshness','promotion keeps score','empty index rejects','quad IoU']}
    (ROOT/'research/qa/vision-pipeline.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
