"""Cumulative download count survives crawler restarts; does not mutate progress."""
import json,os,sqlite3
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def status():
    cache=ROOT/'data/registry/neuron';progress=json.loads((cache/'progress.json').read_text(encoding='utf-8'))
    queue=json.loads((cache/'detail-queue.json').read_text(encoding='utf-8'))
    total=queue['total_discovered'];cached=sum(e.name.startswith('card-') and e.name.endswith('.json') for e in os.scandir(cache))
    db=sqlite3.connect((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',uri=True)
    try:retried_imported=bool(db.execute("SELECT 1 FROM sources WHERE id='neuron:card-pt-15519'").fetchone())
    finally:db.close()
    updated=progress.get('updated_at',progress['started_at'])
    return {'observed_at':datetime.now(timezone.utc).isoformat(),'cached_detail_files':cached,'total_discovered':total,
        'remaining_files':max(0,total-cached),'percent':round(100*cached/total,2),
        'current_run_completed':progress['completed'],'current_run_scheduled':progress.get('scheduled'),
        'reported_state':progress['status'],'progress_age_seconds':round((datetime.now(timezone.utc)-datetime.fromisoformat(updated)).total_seconds()),
        'current_run_errors':progress['errors'],'retry_pt_15519_cached':(cache/'card-pt-15519.json').exists(),
        'retry_pt_15519_imported':retried_imported,'note':'File count, not full content audit. Reported running state alone does not prove a live process.'}


if __name__=='__main__':print(json.dumps(status(),ensure_ascii=False,indent=2))
