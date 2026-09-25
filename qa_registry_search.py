"""Compare old/new semantics on one read snapshot, including empty pages and typed IDs."""
import json,statistics,time
from registry_server import connection,search
from registry import ROOT,LANGS


def previous(db,term,page):
    match='SELECT card_id FROM names WHERE name LIKE ? UNION SELECT card_id FROM identifiers WHERE value=? UNION SELECT card_id FROM printings WHERE set_code=? UNION SELECT id FROM cards WHERE id=?'
    args=('%'+term+'%',term,term,term)
    total=db.execute('SELECT count(*) FROM ('+match+')',args).fetchone()[0]
    ids=db.execute('SELECT card_id FROM ('+match+') ORDER BY card_id LIMIT 30 OFFSET ?',(*args,page*30)).fetchall()
    items=[]
    for row in ids:
        names={}
        for r in db.execute("SELECT language,name FROM names WHERE card_id=? ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 WHEN source LIKE 'ygojson%' THEN 1 ELSE 2 END",(row[0],)):
            if r['language'] in LANGS:names.setdefault(r['language'],r['name'])
        items.append({'id':row[0],'names':names,'passcodes':[r[0] for r in db.execute("SELECT DISTINCT value FROM identifiers WHERE card_id=? AND kind='passcode'",(row[0],))]})
    return {'items':items,'total':total,'page':page}


def timing(call):
    call();times=[]
    for _ in range(5):
        start=time.perf_counter();call();times.append((time.perf_counter()-start)*1000)
    return round(statistics.median(times),3)


def main():
    db=connection();db.execute('BEGIN');results=[]
    try:
        for term in ('89631139','89631140','LOB-EN001','Dragón','Blue-Eyes',"D'",'_%','no-such-card-xyz',''):
            for page in (0,1,10000):
                a=previous(db,term,page);b=search(db,term,page)
                assert a==b,(term,page,a,b)
        uid=search(db,'89631139',0,'passcode')['items'][0]['id']
        assert not search(db,'89631140',0,'passcode')['items'],'Artwork ID accepted as passcode'
        assert search(db,'4007',0,'cid')['items'][0]['id']==uid
        assert uid in {r['id'] for r in search(db,'LOB-EN001',0,'set')['items']}
        zero=db.execute("SELECT value FROM identifiers WHERE kind='passcode' AND value LIKE '0%' LIMIT 1").fetchone()[0]
        assert search(db,zero,0,'passcode')['items'],'Leading zero lost'
        try:search(db,'x',0,'bad')
        except ValueError:pass
        else:raise AssertionError('Invalid mode accepted')
        for term in ('89631139','LOB-EN001','Dragón','no-such-card-xyz'):
            old_ms=timing(lambda:previous(db,term,0));new_ms=timing(lambda:search(db,term,0))
            traces=[];db.set_trace_callback(traces.append);search(db,term,0);db.set_trace_callback(None)
            assert len(traces)<=5,traces
            mode={'89631139':'passcode','LOB-EN001':'set'}.get(term)
            results.append({'term':term,'old_median_ms':old_ms,'new_median_ms':new_ms,'statements_including_savepoint':len(traces),
                'exact_mode_median_ms':timing(lambda:search(db,term,0,mode)) if mode else None})
        assert db.in_transaction,'Nested savepoint committed caller transaction'
    finally:db.rollback();db.close()
    result={'status':'passed','conditions':'5 warm samples on same read snapshot; active services, not hardware benchmark',
            'equivalent_cases':27,'typed_ids_and_leading_zeros':True,'measurements':results}
    (ROOT/'research/qa/registry-search-optimized.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
