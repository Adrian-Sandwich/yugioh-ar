"""Freeze native-resolution card crops; original scene is never overwritten."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from vision_onnx import Detector
OUT=Path(__file__).resolve().parent
(OUT/'inputs').mkdir(exist_ok=True)
scene=cv2.imread(str(OUT/'table-original.jpg'))
if scene is None: raise ValueError('Missing original table capture')
boxes=Detector().detect(scene)
boxes.sort(key=lambda d: float(d['corners'][:,0].mean()))
rows=[];tiles=[]
for i,box in enumerate(boxes,1):
    p=box['corners'];w=round(float(np.linalg.norm(p[1]-p[0])));h=round(float(np.linalg.norm(p[2]-p[1])))
    if w<20 or h<20: continue
    transform=cv2.getPerspectiveTransform(p.astype(np.float32),np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]))
    card=cv2.warpPerspective(scene,transform,(w,h))
    if w>h:card=cv2.rotate(card,cv2.ROTATE_90_CLOCKWISE)
    name=f'table-{i:02}'
    cv2.imwrite(str(OUT/'inputs'/f'{name}.png'),card)
    rows.append({'sample':name,'file':f'inputs/{name}.png','corners':p.tolist(),
                 'shape':list(card.shape),'expected_card_id':None,'expected_passcode':None,
                 'label_source':'pending visual review','detector_score':box['score']})
    tile=cv2.resize(card,(170,248));cv2.putText(tile,name,(5,25),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,0),2);tiles.append(tile)
close=cv2.imread(str(ROOT/'research/qa/passcode/real-rectified.png'))
cv2.imwrite(str(OUT/'inputs/close-blue.png'),close)
rows.append({'sample':'close-blue','file':'inputs/close-blue.png','shape':list(close.shape),
             'expected_card_id':'e0404755-1ade-4c7c-9a2a-b29b7755d860','expected_passcode':'89631139',
             'label_source':'previously reviewed close photograph; separate session'})
cv2.imwrite(str(OUT/'contact-sheet.png'),np.hstack(tiles))
(OUT/'samples.json').write_text(json.dumps({'scene_sha256':hashlib.sha256((OUT/'table-original.jpg').read_bytes()).hexdigest(),
    'note':'Exploratory samples, not an independent statistical test set. No clean paired ground truth.', 'samples':rows},indent=2),encoding='utf-8')
print('Saved',len(boxes),'table crops and one close reference',flush=True)
