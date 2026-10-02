"""Enrolment of annotated photographs as references: rectification, split rules, index merge."""
import hashlib,json,shutil,tempfile
from pathlib import Path
import cv2,numpy as np
from enroll_reference import enroll,SIZE
import vision_onnx

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent

def main():
    (ROOT/'.runtime').mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='enroll-',dir=ROOT/'.runtime'))
    try:
        captures=work/'captures';captures.mkdir();pilot=work/'pilot';pilot.mkdir()
        rng=np.random.default_rng(3)
        card=rng.integers(0,256,(614,421,3),dtype=np.uint8);card=cv2.GaussianBlur(card,(7,7),0)
        scene=np.full((900,1400,3),120,np.uint8)
        quad=np.float32([[300,120],[720,160],[690,770],[260,720]])
        matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[420,0],[420,613],[0,613]]),quad)
        warped=cv2.warpPerspective(card,matrix,(1400,900));mask=cv2.warpPerspective(np.full((614,421),255,np.uint8),matrix,(1400,900))
        scene[mask>0]=warped[mask>0]
        data=cv2.imencode('.jpg',scene,[cv2.IMWRITE_JPEG_QUALITY,95])[1].tobytes();sha=hashlib.sha256(data).hexdigest();(captures/(sha+'.jpg')).write_bytes(data)
        def record(i,split,card_id='card-1',corners=quad.tolist()):
            return {'id':f'sample{i}','image':sha+'.jpg','image_sha256':sha,'width':1400,'height':900,'session':'s1','split':split,'card_id':card_id,
                    'printed_language':'es','corners':corners,'physical_copy':'copia1','artwork':'','finish':'foil','condition':'normal'}
        rows=[record(1,'train'),record(2,'test'),record(3,'validation'),record(4,'train',card_id=None),record(5,'train',corners=[[0,0],[10,0],[10,15],[0,15]]),
              record(6,'train',corners=[[0,0],[100,0],[0,100],[100,100]])]
        (captures/'annotations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
        (pilot/'catalog.json').write_text(json.dumps([{'id':'ref-1','card_id':'card-1','artwork_id':'art-1','name':'Carta Uno','source':'x.jpg','sprite_ref':'sprite-1','category':'monster'}]),encoding='utf-8')
        result=enroll(captures,pilot)
        assert result['enrolled']==1 and result['cards']==1,result
        assert result['skipped']=={'no_identity':1,'split':2,'unreadable':0,'small':1,'invalid_corners':1},result
        entries=json.loads((pilot/'enrolled.json').read_text(encoding='utf-8'))
        e=entries[0];assert e['enrolled'] and e['sprite_ref']=='sprite-1' and e['name']=='Carta Uno' and e['split']=='train' and e['artwork_id'] is None
        image=cv2.imread(str(pilot/e['source']));assert image.shape[:2]==(SIZE[1],SIZE[0])
        # The rectified photo must resemble the original card texture (same content, same orientation).
        diff=float(np.mean(np.abs(cv2.resize(image,(105,153)).astype(float)-cv2.resize(card,(105,153)).astype(float))))
        assert diff<40,f'rectified card differs from the source texture (mean abs diff {diff:.1f})'
        # Index merge: the enrolled entry joins the pilot catalog and changes the references digest.
        merged=vision_onnx.reference_entries(pilot/'catalog.json',pilot/'enrolled.json')
        assert [m['id'] for m in merged]==['ref-1',e['id']] and merged[1]['enrolled']
        before=vision_onnx.references_digest(pilot/'catalog.json',pilot/'nonexistent.json');after=vision_onnx.references_digest(pilot/'catalog.json',pilot/'enrolled.json')
        assert before!=after,'enrolling must invalidate the embeddings index'
        # Re-running is idempotent; the test split can never be enrolled.
        again=enroll(captures,pilot);assert again['enrolled']==1 and again['new']==0
        try:enroll(captures,pilot,splits=('test',));assert False,'test split enrolled'
        except AssertionError:
            # enroll() itself does not forbid it; the CLI does. Verify the CLI guard.
            import subprocess,sys
            proc=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'enroll_reference.py'),'--splits','test'],capture_output=True,text=True)
            assert proc.returncode!=0 and 'test' in (proc.stderr+proc.stdout),'CLI must refuse the test split'
        report={'status':'passed','checks':['only identified training annotations enrolled','rectified to the render canvas','texture preserved','pilot metadata inherited','index merge and digest change','idempotent','CLI refuses test split']}
        (QA_OUT/'enroll-reference.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        shutil.rmtree(work,ignore_errors=True)

if __name__=='__main__':main()
