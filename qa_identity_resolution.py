"""All evidence uses one alias version while unresolved identities stay distinct."""
import copy,json,sqlite3
from identity_resolution import IDENTITIES,IdentityMap,normalize_detection,canonical
from name_ocr import NameRegistry,mark_conflicts
from passcode_ocr import lookup
from set_ocr import lookup_set,DB
from card_evidence import fuse

def main():
    assert len(IDENTITIES.aliases)==12,IDENTITIES.info()
    for old,new in IDENTITIES.aliases.items():
        assert canonical(old)==new and canonical(new)==new
        d=normalize_detection({'card_id':old,'top5':[{'card_id':old},{'card_id':new}]})
        assert d['card_id']==new and d['source_card_id']==old
        assert len(d['top5'])==2,'Reference hypotheses must not be deleted'
        title={'status':'matched','matches':[{'card_id':new}]}
        assert mark_conflicts(title,old,[{'card_id':new}],True)['status']=='matched'
        item={'visual_card_id':old,'ocr_score':.99,'matches':[{'card_id':new}],
            'name_ocr':title,'set_ocr':{'status':'matched','matches':[{'card_id':old}]},'art_match':{'status':'matched','card_id':old}}
        assert fuse(item)['card_id']==new and fuse(item)['agreeing_sources']==5
    serial=lookup('06798031');assert len(serial)==1 and len(serial[0]['source_card_ids'])==2
    assert len(lookup('55154344'))==1
    assert lookup('55154344')[0]['card_id']!=lookup('81549048')[0]['card_id']
    assert not IDENTITIES.allows('cc08efa1-bf81-4c5e-aadb-6143dedea851','passcode','55154344')
    for code in ('20726052','20938824','20415050'):assert len(lookup(code))==1
    registry=NameRegistry();name=registry.resolve([{'text':'Ryzeal Cross','score':.99,'orientation':0,'variant':'test'}])
    assert name['status']=='matched' and name['matches'][0]['card_id']==serial[0]['card_id']
    db=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
    try:
        code=db.execute('SELECT set_code FROM printings WHERE card_id=? AND set_code IS NOT NULL LIMIT 1',(serial[0]['card_id'],)).fetchone()[0]
    finally:db.close()
    assert serial[0]['card_id'] in {m['card_id'] for m in lookup_set(code)}
    assert canonical('brand-new-crawler-id')=='brand-new-crawler-id'
    assert IdentityMap().canonical(next(iter(IDENTITIES.aliases)))==next(iter(IDENTITIES.aliases))
    for bad in ({'a':'a'},{'a':'b','b':'a'},{'a':'b','b':'c'}):
        try:IdentityMap(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid map accepted')
    print(json.dumps({'status':'passed','version':IDENTITIES.version,'aliases':len(IDENTITIES.aliases),'serial_name_set_visual_art':'consistent','disputed_serial':'excluded without merging distinct cards','new_ids':'passed_through','rollback':'raw map tested'}))

if __name__=='__main__':main()
