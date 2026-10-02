"""Local read-only download watcher; writes completion report, never sends messages."""
import argparse,json,sqlite3,time
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from download_status import ROOT,status

def write(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)

def inspect():
    report=status();report['watch_checked_at']=datetime.now(timezone.utc).isoformat()
    report['watch_state']='downloading' if report['progress_age_seconds']<180 else 'stale_progress'
    terminal=report['reported_state'] in ('complete','complete_with_errors','stopped','access_blocked')
    if terminal:
        files={p.stem for p in (ROOT/'data/registry/neuron').glob('card-*.json')}
        expected=set()
        for path in (ROOT/'data/registry/neuron').glob('index-??-[0-9]*.json'):
            page=json.loads(path.read_text(encoding='utf-8'))
            expected.update(f"card-{page['language']}-{c['cid']}" for c in page['cards'])
        with closing(sqlite3.connect((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
            imported={r[0].removeprefix('neuron:') for r in db.execute("SELECT id FROM sources WHERE id LIKE 'neuron:card-%'")}
        report['cached_not_imported']=sorted(files-imported)
        report['expected_missing_files']=sorted(expected-files)
        report['expected_not_imported']=sorted(expected-imported)
        complete=len(expected)==report['total_discovered'] and not expected-files and not expected-imported
        report['watch_state']='complete_pending_content_audit' if complete else 'finished_with_pending_work'
        if report['reported_state'] in ('stopped','access_blocked'):report['watch_state']=report['reported_state']
    return report,terminal

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    output=ROOT/'.runtime/download-watch.json';output.parent.mkdir(exist_ok=True)
    while True:
        try:
            report,terminal=inspect();write(output,report)
            if terminal:write(ROOT/'research/database-audit/download-completion.json',report)
            if terminal or args.once:print(json.dumps(report,ensure_ascii=False));return
        except (OSError,ValueError,sqlite3.Error) as exc:
            write(output,{'watch_state':'error','error':str(exc),'watch_checked_at':datetime.now(timezone.utc).isoformat()})
            if args.once:raise
        time.sleep(60)

if __name__=='__main__':main()
