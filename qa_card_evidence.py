"""Replacement, crossing, stale-frame and independent evidence regressions."""
import copy
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from card_evidence import EvidenceSession,describe,fuse
from set_ocr import codes,lookup_set,SetReader

def card(offset=0,appearance=100,uid='a'):
    return {'corners':[[offset,0],[offset+100,0],[offset+100,150],[offset,150]],
        '_appearance':np.full((48,32,3),appearance,np.uint8),'visual_card_id':uid,
        'frame_quality':{'score':10},'name_ocr':{'status':'matched','matches':[{'card_id':uid}]}}

def step(session,items,t,h):
    session.associate(items,t)
    return session.finish(items,t,h)

def verify_real():
    """Real photograph against self-hosted YGOPRODeck art; skipped when not downloaded."""
    import json
    from art_verify import ArtVerifier,MANIFEST
    from passcode_ocr import ROOT,rectify,lookup
    if not MANIFEST.exists():
        print('SKIP art verification: run research/download_ygoprodeck_art.py first');return
    ref=json.loads((ROOT/'data/references/catalog.json').read_text(encoding='utf-8'))[0]
    image=cv2.imread(str(ROOT/'data/references'/ref['source']))
    rectified,_,_=rectify(image,ref['corners'])
    pilot=json.loads((ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))
    by_name={e['name']:e['card_id'] for e in pilot}
    blue=lookup('89631139')[0]['card_id'];others=[by_name['Mago Oscuro'],by_name['Dragón Negro de Ojos Rojos']]
    verifier=ArtVerifier()
    if blue not in verifier.arts:
        print('SKIP art verification: pilot artwork not downloaded yet');return
    result=verifier.verify(rectified,[others[0],blue,others[1]])
    assert result['status']=='matched' and result['card_id']==blue,result
    assert result['matches'][0]['inliers']>=MIN_INLIERS_SEEN,result
    upside=verifier.verify(np.ascontiguousarray(np.rot90(rectified,2)),[blue,*others])
    assert upside['status']=='matched' and upside['orientation']==180,upside
    negative=verifier.verify(rectified,others)
    assert negative['status']=='unverified' and negative['card_id'] is None,negative
    assert verifier.verify(rectified,[])['status']=='skipped'
    blank=np.full_like(rectified,150)
    assert verifier.verify(blank,[blue])['status']=='unverified'
    print('art verification on real photo:',{k:result[k] for k in ('status','processing_ms')},result['matches'][0])

MIN_INLIERS_SEEN=60

def main():
    session=EvidenceSession()
    a=step(session,[card()],0,'a')[0]
    assert a['evidence']['status']=='corroborated'
    b=step(session,[card(3)],.5,'b')[0]
    assert b['evidence']['status']=='repeated'
    assert b['evidence_track_id']==a['evidence_track_id']
    c=step(session,[card(3,200)],1,'c')[0]
    assert c['evidence_track_id']!=b['evidence_track_id'] and c['evidence']['consistent_frames']==1
    d=step(session,[card(3,200,'b')],1.5,'d')[0]
    assert d['evidence_track_id']!=c['evidence_track_id']
    assert step(session,[card(3,200,'b')],8,'e')[0]['evidence']['consistent_frames']==1
    session=EvidenceSession();step(session,[card()],0,'a')
    items=[card(1),card(2)];session.associate(items,.5)
    assert all(i['_track']!=1 for i in items),'Competing copies inherited an old track'
    session=EvidenceSession();step(session,[card(0),card(250)],0,'a')
    moved=step(session,[card(252),card(2)],.5,'b')
    assert [i['evidence_track_id'] for i in moved]==[2,1]
    session=EvidenceSession();step(session,[card()],0,'a');step(session,[],.5,'b')
    assert step(session,[card()],1,'c')[0]['evidence']['consistent_frames']==1
    session=EvidenceSession();step(session,[card()],0,'same')
    assert step(session,[card()],.5,'same')[0]['evidence']['consistent_frames']==1
    assert step(session,[card()],.5,'changed')[0]['evidence']['consistent_frames']==1
    session=EvidenceSession()
    for t in (0,.5):
        same=card();same['ocr_image_hash']='same-card-pixels'
        assert step(session,[same],t,str(t))[0]['evidence']['consistent_frames']==1
    sample=card();sample['name_ocr']['matches']=[{'card_id':'b'}]
    assert fuse(sample)['status']=='conflict'
    sample['name_ocr']['status']='not_in_registry';sample['name_ocr']['suggestions']=[{'card_id':'b'}]
    assert fuse(sample)['card_id']=='a' and fuse(sample)['agreeing_sources']==1
    sample['set_ocr']={'status':'matched','matches':[{'card_id':'b'}]}
    assert fuse(sample)['status']=='conflict'
    session=EvidenceSession();step(session,[card()],0,'a')
    poor=card();poor['frame_quality']['score']=3;session.associate([poor],.5)
    cached=session.cached(poor,.5,'b');assert cached and cached['ocr_reused']
    result=session.finish([cached],.5,'b')[0]
    assert result['evidence']['consistent_frames']==1 and result['evidence_captured_at']==0
    assert session.cached(poor,2,'c') is None
    # Artwork verification: corroborates the image, conflicts when it disagrees,
    # and never earns 'repeated' by itself (visual-only, no text read).
    sample=card();del sample['name_ocr'];sample['art_match']={'status':'matched','card_id':'a','matches':[{'card_id':'a'}]}
    assert fuse(sample)['status']=='candidate' and fuse(sample)['agreeing_sources']==2
    session=EvidenceSession()
    first=copy.deepcopy(sample);assert step(session,[first],0,'a')[0]['evidence']['status']=='corroborated'
    again=copy.deepcopy(sample);again['corners']=[[3,0],[103,0],[103,150],[3,150]]
    assert step(session,[again],.5,'b')[0]['evidence']['status']=='corroborated','Visual-only evidence must not become repeated'
    wrong=card();wrong['art_match']={'status':'matched','card_id':'b','matches':[{'card_id':'b'}]}
    assert fuse(wrong)['status']=='conflict'
    unverified=card();unverified['art_match']={'status':'unverified','card_id':None,'matches':[]}
    assert 'art' not in fuse(unverified)['sources']
    verify_real()
    image=np.random.default_rng(1).integers(0,255,(920,630,3),dtype=np.uint8)
    assert describe(image,600)[1]['score']>describe(cv2.GaussianBlur(image,(31,31),10),600)[1]['score']
    assert codes('LOB - EN001')==['LOB-EN001']
    assert codes('SDK-001')==['SDK-001'] and codes('LOB-ENO01')==[]
    with tempfile.TemporaryDirectory() as tmp:
        dbpath=Path(tmp)/'registry.sqlite'
        with sqlite3.connect(dbpath) as db:
            db.execute('CREATE TABLE printings(card_id,language,rarity,edition,set_code)')
            db.executemany('INSERT INTO printings VALUES (?,?,?,?,?)',[
                ('a','en','ultra','first','LOB-EN001'),('a','en','secret',None,'LOB-EN001')])
        db.close()
        matches=lookup_set('LOB-EN001',dbpath)
        assert len(matches)==1 and len(matches[0]['printings'])==2
        class Engine:
            def __call__(self,*args,**kwargs):return SimpleNamespace(txts=['LOB-EN001'],scores=[.98])
        assert SetReader(Engine(),dbpath).read(image)['status']=='matched'
        with sqlite3.connect(dbpath) as db:db.execute("INSERT INTO printings VALUES ('b','en',NULL,NULL,'LOB-EN001')")
        db.close()
        assert SetReader(Engine(),dbpath).read(image)['status']=='ambiguous'
    print('PASS: association, replacement, competing copies, absence, expiry, duplicate frames, quality reuse, conflicts, exact printing codes')

if __name__=='__main__':main()
