"""Reproducible offline diagnostic sample; never promotes catalog proposals."""
import hashlib
import json
import sqlite3
import sys
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from art_verify import ArtVerifier,ART_REGION,MIN_INLIERS,MIN_RATIO,MIN_COVERAGE,MARGIN
from printing_art_links import visual_triage


def score_image(verifier,image,candidates):
    h,w=image.shape[:2];x0,y0,x1,y1=ART_REGION
    crop=image[round(y0*h):round(y1*h),round(x0*w):round(x1*w)]
    keypoints,descriptors=verifier.sift.detectAndCompute(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),None)
    points=np.float32([p.pt for p in keypoints]) if keypoints else np.empty((0,2),np.float32)
    scored=[]
    for uid in candidates:
        for art_id,path in verifier.arts.get(uid,[]):
            reference=verifier.reference(art_id,path)
            if reference is not None:
                scored.append({**verifier.match(points,descriptors,reference),
                               'card_id':uid,'artwork_id':art_id,'reference_path':path.relative_to(ROOT).as_posix()})
    scored.sort(key=lambda r:(-r['inliers'],r['artwork_id']))
    if not scored:return {'status':'no_reference','scores':[]}
    best=scored[0]
    passes=best['inliers']>=MIN_INLIERS and best['ratio']>=MIN_RATIO and best['coverage']>=MIN_COVERAGE
    second=scored[1]['inliers'] if len(scored)>1 else 0
    status=('unverified' if not passes else 'ambiguous_art' if best['inliers']<MARGIN*max(second,1)
            else 'visual_support_needs_review')
    return {'status':status,'scores':scored}


def main():
    pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    out=ROOT/'research/database-audit'/('visual-sample-'+pointer['version']);out.mkdir(exist_ok=True)
    verifier=ArtVerifier()
    with closing(sqlite3.connect((ROOT/pointer['database']).as_uri()+'?mode=ro',uri=True)) as db:
        queue=visual_triage(db)
        metadata={r[0]:r[1:] for r in db.execute('SELECT ref_id,kind,width,height,sha256 FROM visual_references')}
        names=dict(db.execute("SELECT canonical_card_id,min(name) FROM resolved_names WHERE language='en' GROUP BY canonical_card_id"))
    buckets=defaultdict(list)
    for row in queue:
        kind,w,h,digest=metadata[row['ref_id']]
        if kind!='card':continue
        buckets[(row['source'],row['triage'])].append(row)
    sample=[]
    for key,rows in sorted(buckets.items()):
        sample.extend(sorted(rows,key=lambda r:hashlib.sha256(r['ref_id'].encode()).hexdigest())[:4])
    results=[]
    for n,row in enumerate(sample,1):
        path=(ROOT/row['path']).resolve()
        if not path.is_relative_to((ROOT/'downloads').resolve()):raise ValueError('Path outside assets')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        expected=metadata[row['ref_id']][3]
        if expected and digest!=expected:raise ValueError('Catalog hash mismatch: '+row['ref_id'])
        image=cv2.imread(str(path))
        if image is None:raise ValueError('Unreadable image: '+row['ref_id'])
        cv2.setRNGSeed(42)
        result={**row,'sample_index':n,'sha256':digest,'width':image.shape[1],'height':image.shape[0],
                'candidate_names':[names.get(c,c) for c in row['canonical_candidates']],
                **score_image(verifier,image,row['canonical_candidates'])}
        if result['scores']:
            best=result['scores'][0]
            best['reference_sha256']=hashlib.sha256((ROOT/best['reference_path']).read_bytes()).hexdigest()
            blank=score_image(verifier,np.full_like(image,127),row['canonical_candidates'])
            result['blank_control_status']=blank['status']
            assert blank['status']=='unverified',blank
        results.append(result)
        print(f"{n}/{len(sample)} {row['source']} {result['status']}",flush=True)
    # Read-only comparison sheets, with separate source and reference panels.
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14)
    for start in range(0,len(results),6):
        sheet=Image.new('RGB',(1200,1320),'white');draw=ImageDraw.Draw(sheet)
        for j,r in enumerate(results[start:start+6]):
            x=(j%2)*600;y=(j//2)*440
            draw.text((x+8,y+6),f"#{r['sample_index']} {r['source']} / {r['status']}",font=font,fill='black')
            with Image.open(ROOT/r['path']) as im:
                im=im.convert('RGB');im.thumbnail((230,345));sheet.paste(im,(x+8,y+38))
            if r['scores']:
                best=r['scores'][0]
                with Image.open(ROOT/best['reference_path']) as im:
                    im=im.convert('RGB');im.thumbnail((330,270));sheet.paste(im,(x+255,y+45))
                draw.text((x+250,y+323),f"inliers={best['inliers']} ratio={best['ratio']} cov={best['coverage']}",font=small,fill='black')
                draw.text((x+250,y+348),names.get(best['card_id'],'')[:43],font=small,fill='black')
            else:
                draw.text((x+250,y+70),'Sin referencia comparable',font=font,fill='black')
            draw.text((x+8,y+390),'Candidatos: '+ ' / '.join(r['candidate_names'])[:78],font=small,fill='black')
            draw.text((x+8,y+412),r['ref_id'][:85],font=small,fill='black')
        sheet.save(out/f'comparison-{start//6+1}.jpg',quality=92)
    summary={'version':pointer['version'],'sample_size':len(results),
             'selection':'Up to four full-card refs per source/triage bucket, sorted by SHA256(ref_id). Not representative of languages or rarities.',
             'results':dict(Counter(r['status'] for r in results)),
             'thresholds':{'inliers':MIN_INLIERS,'ratio':MIN_RATIO,'coverage':MIN_COVERAGE,'art_margin':MARGIN},
             'blank_controls':sum('blank_control_status' in r for r in results),
             'promoted':0,'limitations':'Scores are diagnostics, not independent identity or printing labels; blank controls do not measure false-positive rate on real cards.',
             'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'art_verifier_sha256':hashlib.sha256((ROOT/'art_verify.py').read_bytes()).hexdigest()}
    (out/'results.json').write_text(json.dumps({'summary':summary,'items':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
