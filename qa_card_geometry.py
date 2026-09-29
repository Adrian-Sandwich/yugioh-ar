"""Geometry regression: known perspective, cut cards, blank scenes and live photo.

Live annotations are approximate manual outer corners for this single capture,
not an accuracy benchmark or evidence of generalization across camera poses.
Candidate 4 (foil card on light wood, inflated detector box) is resolved only by
the chroma edge-snapping fallback; its corners were read from zoomed crops.
"""
import json,time
from pathlib import Path
import cv2
import numpy as np
from card_geometry import GeometryRefiner
from passcode_ocr import rectify,region,REGIONS,PasscodeWorker

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'research/qa/corner-refinement'


def error(actual,expected):
    a=np.float32(actual);b=np.float32(expected)
    return min(float(np.linalg.norm(np.roll(a,k,axis=0)-b,axis=1).mean()) for k in range(4))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    truth=np.float32([[260,120],[576,169],[547,670],[225,611]])
    image=np.full((800,800,3),170,np.uint8)
    cv2.fillConvexPoly(image,truth.astype(np.int32),(45,70,115))
    # A high contrast illustration must not replace the outer card boundary.
    center=truth.mean(0);inner=center+(truth-center)*.73
    cv2.fillConvexPoly(image,inner.astype(np.int32),(240,220,210))
    loose=center+(truth-center)*1.13
    refined=GeometryRefiner(image).refine(loose)
    assert refined.get('corners') and error(refined['corners'],truth)<8,refined
    rotated=GeometryRefiner(image).refine(np.roll(loose,2,axis=0))
    assert error(rotated['corners'],truth)<8
    assert np.linalg.norm(np.float32(rotated['corners'][0])-truth[2])<8,'Lost caller orientation'
    blank=np.full_like(image,170)
    assert 'corners' not in GeometryRefiner(blank).refine(loose)
    # Luminance-matched card: only chroma separates it from the table, and the
    # detector box is far taller than the card. Contours fail; edge snapping must
    # still return the outer border and nothing on the blank table.
    table=np.full((900,900,3),(150,190,220),np.uint8);card=np.float32([[300,150],[560,152],[558,532],[298,530]])
    cv2.fillConvexPoly(table,card.astype(np.int32),(200,200,200))
    cv2.rectangle(table,(330,180),(528,330),(60,90,140),-1)  # inner illustration frame
    inflated=np.float32([[290,120],[575,122],[570,700],[285,698]])
    plain=GeometryRefiner(table,snap_edges=False).refine(inflated)
    snapped=GeometryRefiner(table).refine(inflated)
    assert 'corners' not in plain,plain
    assert snapped.get('geometry_source')=='snapped_edges' and error(snapped['corners'],card)<4,snapped
    assert 'corners' not in GeometryRefiner(np.full_like(table,(150,190,220))).refine(inflated)
    clipped=image.copy();clipped=np.roll(clipped,-190,axis=0)
    shifted=loose-[0,190]
    assert GeometryRefiner(clipped).refine(shifted)['geometry_status']=='frame_edge'
    class Reader:
        def read(self,image,**_):raise AssertionError('OCR ran without observed geometry')
    worker=PasscodeWorker(Reader)
    try:
        worker.submit(cv2.imencode('.jpg',blank)[1].tobytes(),[{'corners':loose.tolist()}])
        deadline=time.monotonic()+5
        while not worker.snapshot().get('sequence') and time.monotonic()<deadline:time.sleep(.02)
        payload=worker.snapshot();item=payload['items'][0]
        assert item['ocr_skipped']=='uncertain_geometry' and 'crop' not in item and 'name_crop' not in item,payload
    finally:worker.close();worker.thread.join(3)
    image=cv2.imread(str(OUT/'current.jpg'))
    boxes=json.loads((OUT/'detected.json').read_text())
    # Visual manual approximation on this frozen image, in arbitrary start order.
    annotations={
        3:[[1488,219],[1767,497],[1577,682],[1294,419]],
        4:[[1032,57],[1314,81],[1272,493],[996,476]],
        5:[[600,347],[985,454],[906,708],[521,590]],
        6:[[272,590],[533,681],[392,1051],[140,954]],
        7:[[265,105],[514,238],[332,595],[84,472]],
    }
    start=time.perf_counter();refiner=GeometryRefiner(image)
    results=[refiner.refine(b['corners']) for b in boxes]
    ms=(time.perf_counter()-start)*1000
    metrics=[];canvas=image.copy();tiles=[]
    for i,(box,result) in enumerate(zip(boxes,results)):
        cv2.polylines(canvas,[np.int32(box['corners'])],True,(30,160,240),2)
        if result.get('corners'):
            cv2.polylines(canvas,[np.int32(result['corners'])],True,(80,240,60),3)
            # Use same orientation for comparison. Layout inspection, not OCR truth.
            before,_,_=rectify(image,box['corners'])
            after,_,_=rectify(image,result['corners'])
            tiles.append(np.hstack([cv2.resize(before,(189,276)),cv2.resize(after,(189,276))]))
        if i in annotations:
            before=error(box['corners'],annotations[i]);after=error(result['corners'],annotations[i])
            assert after<before and after<18,(i,before,after)
            metrics.append({'candidate':i,'before_corner_error_px':round(before,1),'after_corner_error_px':round(after,1)})
    assert results[0]['geometry_status']=='frame_edge' and results[1]['geometry_status']=='frame_edge','Cropped card accepted'
    assert not results[8].get('corners'),'Overlapping card unexpectedly treated as resolved'
    assert results[4].get('geometry_source')=='snapped_edges','Foil card must come from edge snapping'
    assert all(r.get('geometry_source')=='contours_lines' for i,r in enumerate(results) if i in (3,5,6,7)),'Contour results changed source'
    cv2.imwrite(str(OUT/'comparison.jpg'),canvas)
    cv2.imwrite(str(OUT/'crop-comparison.jpg'),np.vstack(tiles))
    report={'status':'passed','geometry_ms_single_run':round(ms,1),'refined':sum(bool(r.get('corners')) for r in results),
            'snapped':sum(r.get('geometry_source')=='snapped_edges' for r in results),
            'total':len(results),'manual_approximation_not_benchmark':metrics,'results':results,
            'limitations':'Single real scene; conservative abstention; no learned segmentation; thresholds uncalibrated.'}
    (OUT/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))


if __name__=='__main__':main()
