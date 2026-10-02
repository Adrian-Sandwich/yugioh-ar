"""Multilingual title OCR and conservative registry evidence, independent of art IDs."""
import difflib,sqlite3,time
from pathlib import Path
import cv2
import numpy as np
from identity_resolution import IDENTITIES,canonical
try:from rapidfuzz import fuzz,process
except ImportError:process=None

import settings
DB=settings.REGISTRY_DB
LANGUAGES=('en','es','de','fr','pt')
NAME_REGION=(.04,.035,.88,.14)
NAME_TIGHT_REGION=(.035,.04,.86,.105)
MIN_SCORE=.85


from names import name_key  # noqa: E402,F401  (name_ocr.name_key)


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
            by_id={};owners={}
            for uid,_,name in rows:
                key=name_key(name,True);by_id.setdefault(canonical(uid),set()).add(key);owners.setdefault(key,set()).add(canonical(uid))
            self.index=index;self.prefix=prefix;self.by_id=by_id;self.owners=owners;self.all_keys=list(owners)
            self.signature=signature;self.available=True
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


# Title OCR as a second, independent vote among the recognizer's own candidates. Searching only
# its top candidates (not 14,000 names) lets a misread title still name the card: a Ghost Rare
# Naturia Barkion read as "NČHIRIA BARKION" was 5th visually and absent from the exact index.
NAME_PICK_MIN=.72
NAME_PICK_MARGIN=.12


def pick_by_name(registry,text,candidate_ids,min_similarity=NAME_PICK_MIN,margin=NAME_PICK_MARGIN):
    """The candidate whose name (any language) the title text resembles most, if it clearly wins:
    {'card_id', 'similarity', 'runner_up'} or None."""
    query=name_key(text or '',True)
    if len(query)<6 or not registry.refresh():return None
    scored=[]
    for cid in dict.fromkeys(canonical(c) for c in candidate_ids if c):
        names=getattr(registry,'by_id',{}).get(cid,())
        best=max((difflib.SequenceMatcher(None,query,n,autojunk=False).ratio() for n in names),default=0.)
        scored.append((best,cid))
    scored.sort(key=lambda s:-s[0])
    if not scored or scored[0][0]<min_similarity:return None
    runner_up=scored[1][0] if len(scored)>1 else 0.
    if scored[0][0]-runner_up<margin:return None
    # The title must also be closest to that card in the whole registry: "Aroma Gardening" misread
    # must not become "Aroma Garden" just because only the latter was among the candidates.
    best,cid=scored[0];floor=best-.03
    keys=getattr(registry,'all_keys',[])
    if process is not None:
        # rapidfuzz's ratio (longest common subsequence) is never below difflib's, so this C scan of
        # 65k names (~2 ms instead of 100-170 ms) keeps every name difflib would accept; difflib decides.
        close=[k for k,_,_ in process.extract(query,keys,scorer=fuzz.ratio,score_cutoff=max(.5,floor)*100,limit=None)]
    else:close=difflib.get_close_matches(query,keys,n=5,cutoff=max(.5,floor))
    for key in close:
        if cid not in registry.owners.get(key,()) and difflib.SequenceMatcher(None,query,key,autojunk=False).ratio()>=floor:
            return None
    return {'card_id':cid,'similarity':round(best,3),'runner_up':round(runner_up,3)}


# A clear title names the card on its own: Ghost Rare art can fall out of the recognizer's top 5
# altogether (Naturia Barkion on 02/10/2026: read "NATURIA BAIKION" at 0.89, nowhere among the
# candidates). Stricter than the in-candidates pick: the card must win over every other name in
# the registry by NAME_GLOBAL_MARGIN, and the OCR reading itself must be confident.
NAME_GLOBAL_MIN=.88
NAME_GLOBAL_MARGIN=.12
NAME_GLOBAL_OCR=.85


def pick_global(registry,text,min_similarity=NAME_GLOBAL_MIN,margin=NAME_GLOBAL_MARGIN):
    """The one card whose name (any language) the title resembles, searched in the whole registry:
    {'card_id', 'similarity', 'runner_up', 'scope': 'global'} or None when not clear enough."""
    query=name_key(text or '',True)
    if len(query)<6 or not registry.refresh():return None
    keys=getattr(registry,'all_keys',[])
    floor=max(.5,min_similarity-margin)*100
    if process is not None:close=[k for k,_,_ in process.extract(query,keys,scorer=fuzz.ratio,score_cutoff=floor,limit=None)]
    else:close=difflib.get_close_matches(query,keys,n=20,cutoff=floor/100)
    best={}
    for key in close:
        sim=difflib.SequenceMatcher(None,query,key,autojunk=False).ratio()
        for cid in registry.owners.get(key,()):
            if sim>best.get(cid,0.):best[cid]=sim
    ranked=sorted(best.items(),key=lambda kv:-kv[1])
    if not ranked or ranked[0][1]<min_similarity:return None
    runner_up=ranked[1][1] if len(ranked)>1 else 0.
    if ranked[0][1]-runner_up<margin:return None
    return {'card_id':ranked[0][0],'similarity':round(ranked[0][1],3),'runner_up':round(runner_up,3),'scope':'global'}


class TitleReader:
    def __init__(self,engine,registry=None):
        self.engine=engine;self.registry=registry if registry is not None else NameRegistry()

    def read(self,rectified,turns=(0,2)):
        observations=[]
        available=self.registry.refresh()
        for turns in turns:
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
