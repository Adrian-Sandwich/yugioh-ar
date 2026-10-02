"""Capture-page annotations converted into detector scenes that import_annotations.py accepts."""
import hashlib,json,shutil,sys,tempfile
from pathlib import Path
import cv2,numpy as np

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research/yolo11_pose'))
from from_captures import convert
from import_annotations import build

def main():
    (ROOT/'.runtime').mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='pose-captures-',dir=ROOT/'.runtime'))
    try:
        captures=work/'captures';captures.mkdir()
        rng=np.random.default_rng(5);rows=[]
        def photo(n,session,split,cards):
            image=rng.integers(0,256,(480,640,3),dtype=np.uint8);data=cv2.imencode('.jpg',image)[1].tobytes()
            sha=hashlib.sha256(data).hexdigest();name=sha+'.jpg';(captures/name).write_bytes(data)
            for i,corners in enumerate(cards):
                rows.append({'id':f'{n}-{i}','image':name,'image_sha256':sha,'width':640,'height':480,'session':session,'split':split,'card_id':'card-x' if i==0 else None,
                             'printed_language':None,'corners':corners,'physical_copy':'','artwork':'','finish':'','condition':'normal','label_source':'test'})
        quad=lambda x,y:[[x,y],[x+120,y],[x+120,y+170],[x,y+170]]
        photo(1,'s_train','train',[quad(50,40),quad(300,120)])
        photo(2,'s_train','train',[quad(200,200)])
        photo(3,'s_val','validation',[quad(80,60)])
        photo(4,'s_test','test',[quad(90,90)])
        photo(5,'s_partial','train',[quad(10,10)])   # not certified as exhaustive
        (captures/'annotations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
        out=work/'scenes'
        result=convert(captures,out,['s_train','s_val','s_test'])
        assert result['scenes']==4 and result['cards']==5 and result['by_split']=={'train':2,'val':1,'test':1},result
        assert result['skipped']['session_not_certified']==1
        scene=json.loads(next(out.glob('*.pose.json')).read_text(encoding='utf-8'))
        assert scene['exhaustive'] is True and scene['reviewed'] is True and scene['corner_order']==['TL','TR','BR','BL']
        assert all(o['visibility']==[2,2,2,2] for o in scene['objects']) and any(o['card_id'] is None for s in [json.loads(p.read_text(encoding='utf-8')) for p in out.glob('*.pose.json')] for o in s['objects']),'unknown cards still count as cards'
        dataset=work/'dataset';built=build(out,dataset)
        assert built['images']==4 and built['train_ready'] is True,built
        manifest=json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
        assert {r['split'] for r in manifest['records']}=={'train','val','test'}
        label=next((dataset/'labels/train').glob('*.txt')).read_text().strip().splitlines()
        assert all(len(l.split())==1+4+12 for l in label),'YOLO pose rows: class, box, 4 keypoints with visibility'
        try:convert(captures,work/'again',['s_train','s_val','s_test']);convert(captures,work/'again',['s_train']);raise AssertionError('non-empty output accepted')
        except ValueError:pass
        report={'status':'passed','checks':['only certified sessions converted','validation mapped to val','one scene per image with all its cards','unknown identity kept as card','import_annotations accepts the output','YOLO pose label format','non-empty output refused']}
        (QA_OUT/'pose-from-captures.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        shutil.rmtree(work,ignore_errors=True)

if __name__=='__main__':main()
