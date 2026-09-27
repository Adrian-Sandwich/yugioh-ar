"""Literal printing-code OCR; exact indexed lookup, never O/0 correction."""
import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path
import cv2
import numpy as np
from identity_resolution import IDENTITIES

DB=Path(__file__).resolve().parent/'data/registry/registry.sqlite'
SET_REGIONS=((.52,.714,.96,.752),(.52,.742,.96,.785),(.52,.91,.96,.949))

def codes(text):
    text=unicodedata.normalize('NFKC',text).upper()
    text=re.sub(r'\s*[-\u2010-\u2014]\s*','-',text)
    return sorted(set(re.findall(r'(?<![A-Z0-9])([A-Z0-9]{2,10}-(?:[A-Z]{2})?[0-9]{2,4})(?![A-Z0-9])',text)))

def lookup_set(code,path=DB):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        rows=db.execute('SELECT DISTINCT card_id,language,rarity,edition FROM printings WHERE set_code=?',(code,)).fetchall()
    grouped={}
    for uid,lang,rarity,edition in rows:
        grouped.setdefault(uid,{'card_id':uid,'printings':[]})['printings'].append({'language':lang,'rarity':rarity,'edition':edition})
    return IDENTITIES.merge(list(grouped.values()))

class SetReader:
    def __init__(self,engine,path=DB):self.engine=engine;self.path=path

    def read(self,image):
        observations=[]
        for turns in (0,2):
            oriented=np.ascontiguousarray(np.rot90(image,turns));h,w=oriented.shape[:2]
            for index,(x0,y0,x1,y1) in enumerate(SET_REGIONS):
                crop=oriented[round(y0*h):round(y1*h),round(x0*w):round(x1*w)]
                if cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY).std()<4:continue
                result=self.engine(crop,use_det=False,use_cls=False,use_rec=True)
                for text,score in zip(result.txts or [],result.scores or []):
                    if not np.isfinite(float(score)):continue
                    observations.append({'text':text,'score':float(score),'codes':codes(text),'orientation':turns*90,'region':index})
        qualified={code for o in observations if o['score']>=.85 for code in o['codes']}
        out={'status':'unreadable','code':None,'matches':[],'raw_observations':observations}
        if len(qualified)>1:return {**out,'status':'ambiguous'}
        if not qualified:return out
        code=next(iter(qualified));out['code']=code
        try:out['matches']=lookup_set(code,self.path)
        except (OSError,sqlite3.Error):return {**out,'status':'registry_unavailable'}
        out['status']='matched' if len(out['matches'])==1 else 'ambiguous' if out['matches'] else 'not_in_registry'
        # Multiple rarities/editions can share one set code. Do not select one.
        return out
