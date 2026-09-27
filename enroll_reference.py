"""Photographs of the owner's physical cards as extra recognizer references.

The pilot references are flat digital renders; a foil printing photographed on
the table scored 0.42-0.76 against them (research/qa/art-verification). A
photo of the same physical card, rectified with its four annotated corners,
is the reference that looks most like what the camera sees. Sources are the
annotations of the capture page (data/pilot/captures/annotations.jsonl):
only records with a card identity and only from the training split, so the
validation and test splits keep measuring generalisation.

Writes data/pilot/enrolled/<card>-<sha>.jpg and data/pilot/enrolled.json,
which vision_onnx.reference_entries() merges with the pilot catalog. Rebuild
the index afterwards:

    .venv-eval/Scripts/python.exe -X utf8 enroll_reference.py
    .venv-eval/Scripts/python.exe -X utf8 vision_onnx.py
"""
import argparse,hashlib,json,os
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parent
PILOT=ROOT/'data/pilot'
SIZE=(421,614)  # same canvas as the TDOANE renders of the pilot


def rectify(image,corners):
    points=np.float32(corners)
    if points.shape!=(4,2) or not np.isfinite(points).all() or not cv2.isContourConvex(points):raise ValueError('Esquinas inválidas')
    dst=np.float32([[0,0],[SIZE[0]-1,0],[SIZE[0]-1,SIZE[1]-1],[0,SIZE[1]-1]])
    return cv2.warpPerspective(image,cv2.getPerspectiveTransform(points,dst),SIZE,flags=cv2.INTER_CUBIC)


def enroll(captures=PILOT/'captures',pilot=PILOT,splits=('train',),min_height=200):
    annotations=captures/'annotations.jsonl'
    rows=[json.loads(l) for l in annotations.read_text(encoding='utf-8').splitlines() if l.strip()] if annotations.exists() else []
    catalog=json.loads((pilot/'catalog.json').read_text(encoding='utf-8')) if (pilot/'catalog.json').exists() else []
    by_card={}
    for entry in catalog:by_card.setdefault(entry['card_id'],entry)
    out_dir=pilot/'enrolled';out_dir.mkdir(parents=True,exist_ok=True)
    existing={e['id']:e for e in json.loads((pilot/'enrolled.json').read_text(encoding='utf-8'))} if (pilot/'enrolled.json').exists() else {}
    entries=[];skipped={'no_identity':0,'split':0,'unreadable':0,'small':0,'invalid_corners':0}
    for r in rows:
        if not r.get('card_id'):skipped['no_identity']+=1;continue
        if r.get('split') not in splits:skipped['split']+=1;continue
        image=cv2.imread(str(captures/r['image']))
        if image is None:skipped['unreadable']+=1;continue
        try:card=rectify(image,r['corners'])
        except ValueError:skipped['invalid_corners']+=1;continue
        corners=np.float32(r['corners']);height=float((np.linalg.norm(corners[3]-corners[0])+np.linalg.norm(corners[2]-corners[1]))/2)
        if height<min_height:skipped['small']+=1;continue
        ref_id=f"enrolled:{r['id']}"
        path=out_dir/f"{r['card_id'][:8]}-{r['image_sha256'][:12]}-{r['id'][:8]}.jpg"
        if not path.exists():cv2.imwrite(str(path),card,[cv2.IMWRITE_JPEG_QUALITY,95])
        base=by_card.get(r['card_id'],{})
        entries.append({'id':ref_id,'card_id':r['card_id'],'artwork_id':None,'name':base.get('name',r['card_id']),
                        'source':os.path.relpath(path,pilot).replace('\\','/'),'sprite_ref':base.get('sprite_ref'),'category':base.get('category'),
                        'enrolled':True,'session':r.get('session'),'split':r.get('split'),'printed_language':r.get('printed_language'),
                        'finish':r.get('finish'),'physical_copy':r.get('physical_copy'),'native_height_px':round(height),
                        'capture_sha256':r['image_sha256'],'reference_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'note':'photograph of a physical card; identity from human annotation, artwork unverified'})
    (pilot/'enrolled.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'enrolled':len(entries),'new':sum(1 for e in entries if e['id'] not in existing),'skipped':skipped,'cards':len({e['card_id'] for e in entries}),'output':str(pilot/'enrolled.json')}


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--splits',nargs='+',default=['train'],help='annotation splits allowed as references (never test)')
    args=parser.parse_args()
    if 'test' in args.splits:parser.error('La partición test queda reservada para evaluar; no se inscribe como referencia')
    result=enroll(splits=tuple(args.splits))
    print(json.dumps(result,ensure_ascii=False))
    print('Reconstruye el índice: .venv-eval/Scripts/python.exe -X utf8 vision_onnx.py',flush=True)


if __name__=='__main__':main()
