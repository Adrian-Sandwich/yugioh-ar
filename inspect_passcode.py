"""Run actual OCR on a known capture and save inspectable crops (no training)."""
import json,time
from pathlib import Path
import cv2
from passcode_ocr import NumberReader,rectify,region,REGIONS,ROOT
out=ROOT/'research/qa/passcode';out.mkdir(parents=True,exist_ok=True)
ref=json.loads((ROOT/'data/references/catalog.json').read_text(encoding='utf-8'))[0]
image=cv2.imread(str((ROOT/'data/references'/ref['source']).resolve()))
rectified,w,h=rectify(image,ref['corners'])
cv2.imwrite(str(out/'real-rectified.png'),rectified)
cv2.imwrite(str(out/'real-passcode.png'),region(rectified,REGIONS['wide']))
reader=NumberReader();started=time.monotonic();best,ambiguous,observations=reader.read(rectified)
result={'sample':ref['source'],'native_card_size':[w,h],'best':best,'ambiguous':ambiguous,'observations':observations,'processing_ms':round((time.monotonic()-started)*1000)}
(out/'real-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
