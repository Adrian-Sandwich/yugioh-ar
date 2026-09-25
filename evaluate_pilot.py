"""Compare existing methods on two real captures and explicitly synthetic smoke scenes."""
import collections
import json
from pathlib import Path

import cv2
import numpy as np

from recognition import PilotRecognizer
from vision_onnx import ResearchRecognizer
from ar_overlay import Tracker,SpriteOverlay
from catalog import connect,EFFECTIVE,asset_path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'research/pilot-evaluation'
BLUE='e0404755-1ade-4c7c-9a2a-b29b7755d860'


def fixtures():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))
    blue=next(e for e in catalog if e['card_id']==BLUE)
    other=next(e for e in catalog if e['card_id']!=BLUE and e.get('sprite_ref'))
    scene=np.full((900,1600,3),(45,65,40),np.uint8)
    quads=[[[90,110],[365,75],[390,545],[70,575]],[[600,260],[835,180],[960,605],[715,675]],[[1130,100],[1440,150],[1390,610],[1090,550]]]
    for entry,quad in zip([blue,blue,other],quads):
        image=cv2.imread(str(ROOT/'data/pilot'/entry['source']))
        h,w=image.shape[:2]
        matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),np.float32(quad))
        warped=cv2.warpPerspective(image,matrix,(1600,900))
        mask=cv2.warpPerspective(np.full((h,w),255,np.uint8),matrix,(1600,900))
        scene[mask>0]=warped[mask>0]
    cv2.imwrite(str(OUT/'synthetic-multiple.jpg'),scene)
    samples=[('synthetic-multiple',scene,[BLUE,BLUE,other['card_id']],'synthetic; gallery images reused, not accuracy evidence')]
    shadow=np.linspace(.45,1.0,1600)[None,:,None]
    altered=np.rot90((scene*shadow).astype(np.uint8),2).copy()
    cv2.imwrite(str(OUT/'synthetic-shadow-rotation.jpg'),altered)
    samples.append(('synthetic-shadow-rotation',altered,[BLUE,BLUE,other['card_id']],'synthetic geometry/illumination smoke test'))
    samples.append(('blank',np.zeros((720,1280,3),np.uint8),[],'controlled negative'))
    pilot_ids={r['card_id'] for r in catalog}
    with connect() as conn:
        outside=next(dict(r) for r in conn.execute('SELECT * FROM ('+EFFECTIVE+") WHERE kind='card' AND effective_status='linked' AND width>=400 ORDER BY ref_id") if r['effective_card_id'] not in pilot_ids)
    unknown=cv2.imdecode(np.frombuffer(asset_path(outside).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    unknown=cv2.resize(unknown,(300,438))
    table=np.full((720,1280,3),40,np.uint8);table[120:558,480:780]=unknown
    cv2.imwrite(str(OUT/'synthetic-outside-pilot.jpg'),table)
    samples.append(('synthetic-outside-pilot',table,[outside['effective_card_id']],'synthetic; identity excluded from pilot, present in full catalog'))
    # Identity labels from the user captures; no manually annotated corner ground truth yet.
    for name in ['carta-2026-09-25T04-15-11-032Z.jpg','carta-2026-09-25T04-13-54-278Z.jpg']:
        samples.append((name,cv2.imread(str(ROOT/'data/captures'/name)),[BLUE],'real capture; one identity, one session'))
    return samples


def main():
    samples=fixtures()
    methods={'sift':PilotRecognizer(),'draw2-small':ResearchRecognizer('classifier'),'embeddings':ResearchRecognizer('embedding')}
    results=[]
    for method,recognizer in methods.items():
        for name,image,expected,source in samples:
            result=recognizer.detect(image)
            accepted=[d for d in result['detections'] if d.get('accepted',True)]
            actual=collections.Counter(d['card_id'] for d in accepted)
            if name=='synthetic-outside-pilot' and method!='draw2-small': expected=[]
            target=collections.Counter(expected)
            row={'method':method,'sample':name,'source':source,'expected':expected,'accepted_count':len(accepted),
                 'correct_identity_instances':sum((actual&target).values()),'false_identity_instances':sum((actual-target).values()),**result}
            results.append(row)
            print(method,name,row['correct_identity_instances'],'/',len(expected),'false',row['false_identity_instances'],result['processing_ms'],'ms',flush=True)
            if method=='sift' and name=='synthetic-multiple':
                tracker=Tracker();tracker.update(accepted,now=0);tracker.update(accepted,now=.5)
                cv2.imwrite(str(OUT/'ar-synthetic.jpg'),SpriteOverlay().render(image,accepted))
            if method=='sift' and name.endswith('.jpg'):
                tracker=Tracker();tracker.update(accepted,now=0);tracker.update(accepted,now=.5)
                cv2.imwrite(str(OUT/('ar-'+name)),SpriteOverlay().render(image,accepted))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Evaluación inicial del piloto','',
           'Dos capturas reales de una sola identidad y sesión, más escenas sintéticas reutilizando referencias. No mide precisión general, rarezas ni soporte multilingüe. Umbrales ONNX experimentales, sin calibrar. Tiempos de CPU tras cargar modelos; excluyen captura y arranque.',
           '', '| Método | Caso | Identidades/instancias correctas | Falsas aceptaciones | ms |','|---|---|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['method']} | {r['sample']} | {r['correct_identity_instances']}/{len(r['expected'])} | {r['false_identity_instances']} | {r['processing_ms']} |")
    (OUT/'RESULTADOS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__': main()
