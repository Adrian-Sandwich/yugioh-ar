"""Multilingual title OCR and conservative registry evidence, independent of art IDs."""
import difflib,sqlite3,time,unicodedata
from pathlib import Path
import cv2
import numpy as np
from identity_resolution import IDENTITIES,canonical

DB=Path(__file__).resolve().parent/'data/registry/registry.sqlite'
LANGUAGES=('en','es','de','fr','pt')
NAME_REGION=(.04,.035,.88,.14)
NAME_TIGHT_REGION=(.035,.04,.86,.105)
MIN_SCORE=.85


def name_key(text,fold_accents=False):
    text=unicodedata.normalize('NFKC',text).casefold()
    if fold_accents:
        text=''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))
    return ''.join(c for c in text if c.isalnum())


def groups(rows):
    result={}
    for uid,language,name in rows:
        item=result.setdefault(uid,{'card_id':uid,'names':[]})
        value={'language':language,'name':name}
        if value not in item['names']:item['names'].append(value)
    return IDENTITIES.merge(list(result.values()))


class NameRegistry:
    """Read-only index. Refresh at most once/minute during the active crawl."""
    def __init__(self,path=DB,refresh_seconds=60):
        self.path=Path(path);self.refresh_seconds=refresh_seconds
        self.checked=-float('inf');self.signature=None;self.index={};self.prefix={};self.available=False

    def refresh(self):
        if time.monotonic()-self.checked<self.refresh_seconds:return self.available
        self.checked=time.monotonic()
        try:
            signature=tuple((p.stat().st_size,p.stat().st_mtime_ns) if p.exists() else None
                for p in (self.path,Path(str(self.path)+'-wal')))
            if signature==self.signature and self.available:return True
            if not self.path.exists():raise FileNotFoundError(self.path)
            db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
            try:rows=db.execute('SELECT DISTINCT card_id,language,name FROM names WHERE language IN (?,?,?,?,?)',LANGUAGES).fetchall()
            finally:db.close()
            index={}
            for row in rows:
                key=name_key(row[2])
                if key:index.setdefault(key,[]).append(row)
            prefix={}
            for key in index:prefix.setdefault(name_key(key,True)[:2],[]).append(key)
            self.index=index;self.prefix=prefix;self.signature=signature;self.available=True
        except (OSError,sqlite3.Error):self.available=False
        return self.available

    def suggestions(self,text):
        query=name_key(text,True)
        if len(query)<6:return []
        options=[]
        for key in self.prefix.get(query[:2],[]):
            folded=name_key(key,True)
            if abs(len(folded)-len(query))>max(2,len(query)*.15):continue
            score=difflib.SequenceMatcher(None,query,folded,autojunk=False).ratio()
            if score>=.88:options.append((score,key))
        rows=[];seen=set()
        for score,key in sorted(options,reverse=True):
            for item in groups(self.index[key]):
                if item['card_id'] in seen:continue
                seen.add(item['card_id']);rows.append({**item,'similarity':round(score,3)})
                if len(rows)==3:return rows
        return rows

    def resolve(self,observations):
        available=self.refresh()
        entries=[]
        for obs in observations:
            key=name_key(obs['text'])
            matches=groups(self.index.get(key,[])) if available and len(key)>=3 else []
            entries.append({**obs,'matches':matches})
        if not entries:return {'status':'unreadable','text':None,'score':None,'matches':[],'suggestions':[],'raw_observations':[]}
        # Registry evidence chooses among literal observations; never substitutes
        # the name expected from the visual recognizer or from the serial.
        qualified=[e for e in entries if e['score']>=MIN_SCORE and e['matches']]
        best=max(qualified or entries,key=lambda e:e['score'])
        identities={m['card_id'] for e in qualified for m in e['matches']}
        ambiguous=len(identities)>1
        if best['score']<MIN_SCORE:state='low_confidence'
        elif len(name_key(best['text']))<3:state='too_short'
        elif not available:state='registry_unavailable'
        elif ambiguous:state='ambiguous'
        elif best['matches']:state='matched'
        else:state='not_in_registry'
        return {**best,'status':state,'ambiguous':ambiguous,'match_kind':'normalized' if best['matches'] else None,
            'suggestions':self.suggestions(best['text']) if available and not best['matches'] and best['score']>=.65 else [],
            'raw_observations':observations,'registry_available':available}


class TitleReader:
    def __init__(self,engine,registry=None):
        self.engine=engine;self.registry=registry if registry is not None else NameRegistry()

    def read(self,rectified):
        observations=[]
        available=self.registry.refresh()
        for turns in (0,2):
            oriented=np.ascontiguousarray(np.rot90(rectified,turns));h,w=oriented.shape[:2]
            for variant,box in (('original',NAME_REGION),('tight_contrast',NAME_TIGHT_REGION)):
                x0,y0,x1,y1=box;crop=oriented[round(y0*h):round(y1*h),round(x0*w):round(x1*w)].copy()
                gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
                if float(gray.std())<4:continue
                if variant=='tight_contrast':crop=cv2.cvtColor(cv2.createCLAHE(2.,(4,2)).apply(gray),cv2.COLOR_GRAY2BGR)
                result=self.engine(crop,use_det=False,use_cls=False,use_rec=True)
                for text,score in zip(result.txts or [],result.scores or []):
                    if not text.strip() or not np.isfinite(float(score)):continue
                    observations.append({'text':text.strip(),'score':round(float(score),4),'variant':variant,'orientation':turns*90})
                # A confidently misread word still deserves the alternate crop.
                if any(o['score']>=.90 and available and name_key(o['text']) in self.registry.index
                       for o in observations if o['orientation']==turns*90):break
        return self.registry.resolve(observations)


def mark_conflicts(reading,visual_id,serial_matches,serial_qualified=False):
    """Conflicts are explicit; name OCR never mutates the visual/serial identity."""
    ids={canonical(m['card_id']) for m in reading.get('matches',[])}
    visual_id=canonical(visual_id)
    qualified=reading.get('status')=='matched'
    visual_conflict=bool(qualified and visual_id and visual_id not in ids)
    serial_ids={canonical(m['card_id']) for m in serial_matches}
    serial_conflict=bool(qualified and serial_qualified and serial_ids and not ids&serial_ids)
    reading.update(visual_conflict=visual_conflict,serial_conflict=serial_conflict)
    if visual_conflict or serial_conflict:reading['status']='conflict'
    return reading
