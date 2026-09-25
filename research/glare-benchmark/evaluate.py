"""Compare restoration with unchanged pilot retrieval and local OCR, never database-guided decoding."""
import argparse,json,sys,time
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from vision_onnx import Encoder
from passcode_ocr import NumberReader

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--variant',required=True)
    args=parser.parse_args();encoder=Encoder();reader=NumberReader()
    vectors=np.load(ROOT/'data/pilot/embeddings.npy')
    metadata=json.loads((ROOT/'data/pilot/embeddings.json').read_text())['rows']
    names={r['card_id']:r['name'] for r in json.loads((ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))}
    dest=OUT/'outputs'/args.variant;dest.mkdir(parents=True,exist_ok=True)
    rows=[]
    for sample in json.loads((OUT/'samples.json').read_text(encoding='utf-8'))['samples']:
        source=OUT/sample['file'] if args.variant in ('original','clahe') else dest/f'{sample["sample"]}.png'
        image=cv2.imread(str(source))
        if image is None:raise FileNotFoundError(source)
        start=time.perf_counter()
        if args.variant=='clahe':
            lab=cv2.cvtColor(image,cv2.COLOR_BGR2LAB);lab[:,:,0]=cv2.createCLAHE(2.0,(8,8)).apply(lab[:,:,0]);image=cv2.cvtColor(lab,cv2.COLOR_LAB2BGR)
        cv2.imwrite(str(dest/f'{sample["sample"]}.png'),image)
        options=[]
        for rotation in (0,2):
            _,z=encoder.predict(np.ascontiguousarray(np.rot90(image,rotation)));scores=vectors@z;grouped={}
            for i in np.argsort(scores)[::-1]:grouped.setdefault(metadata[i]['card_id'],float(scores[i]))
            ranked=list(grouped.items());options.append((ranked[0][1],rotation,ranked))
        score,rotation,ranked=max(options,key=lambda x:x[0]);uid=ranked[0][0];margin=score-ranked[1][1]
        accepted=score>=.80 and margin>=.07
        best,ambiguous,observations=reader.read(cv2.resize(image,(630,920),interpolation=cv2.INTER_CUBIC))
        expected=sample.get('expected_passcodes') or [sample.get('expected_passcode')]
        row={'sample':sample['sample'],'expected_name':sample.get('expected_name','Dragón Blanco de Ojos Azules'),
             'predicted':names.get(uid,uid),'top1_correct':uid==sample['expected_card_id'],
             'accepted':accepted,'accepted_correct':accepted and uid==sample['expected_card_id'],
             'false_accept':accepted and uid!=sample['expected_card_id'],'score':round(score,5),'margin':round(margin,5),
             'rotation':rotation*90,'ocr_best':best,'ocr_ambiguous':ambiguous,
             'ocr_matches_expected':bool(best and best['passcode'] in expected and not ambiguous),
             'ocr_observations':observations,'evaluation_ms':round((time.perf_counter()-start)*1000,1)}
        rows.append(row)
        (dest/'evaluation.json').write_text(json.dumps({'variant':args.variant,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
        print(args.variant,row['sample'],row['predicted'],row['accepted'],row['score'],row['margin'],best['passcode'] if best else '-',flush=True)

if __name__=='__main__':main()
