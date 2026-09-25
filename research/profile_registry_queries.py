"""Read-only diagnostic of current registry queries while the crawler is active."""
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from registry_server import connection, search
from passcode_ocr import lookup


def measure(call):
    call()  # Separate cache warmup from the seven diagnostic samples.
    elapsed=[]
    for _ in range(7):
        start=time.perf_counter()
        result=call()
        elapsed.append((time.perf_counter()-start)*1000)
    return {'median_ms':round(statistics.median(elapsed),3),
            'min_ms':round(min(elapsed),3),'max_ms':round(max(elapsed),3)},result


def main():
    db=connection()
    db.execute('PRAGMA query_only=ON')
    try:
        plans={}
        for name,sql,args in [
            ('name_contains','SELECT card_id FROM names WHERE name LIKE ?',('%Dragón%',)),
            ('passcode_exact',"SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?",('89631139',)),
            ('set_exact','SELECT DISTINCT card_id FROM printings WHERE set_code=?',('LOB-EN001',))]:
            plans[name]=[dict(r) for r in db.execute('EXPLAIN QUERY PLAN '+sql,args)]
        searches={}
        for term in ('89631139','LOB-EN001','Dragón','no-such-card-xyz'):
            metrics,result=measure(lambda:search(db,term,0))
            statements=[]
            db.set_trace_callback(statements.append)
            search(db,term,0)
            db.set_trace_callback(None)
            searches[term]={**metrics,'total':result['total'],'page_items':len(result['items']),
                            'sql_statements':len(statements)}
        exact,ids=measure(lambda:db.execute("SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?",('89631139',)).fetchall())
        ocr,matches=measure(lambda:lookup('89631139'))
        report={'generated_at':datetime.now(timezone.utc).isoformat(),
            'conditions':'7 warm-cache samples, active crawler/services; diagnostic only, no language comparison',
            'search_endpoint_function':searches,'exact_passcode_ids_only':{**exact,'matches':len(ids)},
            'actual_ocr_lookup_with_names_and_connection':{**ocr,'matches':len(matches)},'plans':plans,
            'warning':'ID-only lookup is not semantically equivalent to the general search endpoint.'}
        out=ROOT/'research/qa/registry-query-profile.json'
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True,indent=2))
    finally:
        db.close()


if __name__=='__main__': main()
