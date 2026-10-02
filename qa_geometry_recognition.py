"""Frozen-photo comparison: same detector/encoder, before vs edge refinement."""
import json
from unittest.mock import patch
import cv2
import vision_onnx
from passcode_ocr import ROOT


class Unrefined:
    def __init__(self,image):pass
    def refine(self,corners,snap=True):return {'geometry_status':'unresolved'}
    def refine_all(self,boxes,snap=None):return [self.refine(b) for b in boxes]


from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    model=vision_onnx.ResearchRecognizer()
    report=[]
    for source in ('research/qa/corner-refinement/current.jpg','data/captures/carta-2026-09-25T04-13-54-278Z.jpg','data/captures/carta-2026-09-25T04-15-19-512Z.jpg'):
        image=cv2.imread(str(ROOT/source))
        with patch.object(vision_onnx,'GeometryRefiner',Unrefined):before=model.detect(image)
        after=model.detect(image)
        rows=[]
        for i,(a,b) in enumerate(zip(before['detections'],after['detections'])):
            rows.append({'candidate':i,'geometry':b['geometry_status'],'same_top_identity':a['card_id']==b['card_id'],
                'before':{k:a[k] for k in ('card_id','score','margin','accepted')},
                'after':{k:b[k] for k in ('card_id','score','margin','accepted')}})
        report.append({'source':source,'before_ms':before['processing_ms'],'after_ms':after['processing_ms'],
                       'geometry_ms':after['geometry_ms'],'candidates':rows})
        print(json.dumps({**{k:v for k,v in report[-1].items() if k!='candidates'},'changes':[r for r in rows if r['geometry']=='contour_refined']}),flush=True)
    (QA_OUT/'corner-refinement').mkdir(exist_ok=True)
    (QA_OUT/'corner-refinement/recognition-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
