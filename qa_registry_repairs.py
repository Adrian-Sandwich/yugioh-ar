"""Verify additive repair publication against its backup and source evidence."""
import json,sqlite3
from contextlib import closing
from registry import ROOT,DB

report=json.loads((ROOT/'research/database-audit/import-repairs-result.json').read_text(encoding='utf-8'))
with closing(sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)) as db:
    db.execute('ATTACH DATABASE ? AS previous',(report['backup'],))
    for table in ('cards','artworks','names','identifiers','printings','issues'):
        assert not db.execute(f'SELECT * FROM previous.{table} EXCEPT SELECT * FROM main.{table} LIMIT 1').fetchone(),table
    assert not db.execute('PRAGMA main.foreign_key_check').fetchone()
    assert db.execute('PRAGMA main.quick_check').fetchone()[0]=='ok'
    statuses=dict(db.execute('SELECT status,count(*) FROM issue_resolutions GROUP BY status'))
    assert statuses['already_present_clean']==3 and statuses['printing_recovered']==10
    assert statuses['game_identity_only']==7 and statuses['replayed_with_alias']==90
    count=db.execute("SELECT count(*) FROM printings WHERE source='local-review:import-repairs-20260926'").fetchone()[0]
    assert count==10,count
    assert db.execute("SELECT count(*) FROM identifiers WHERE source='local-review:import-repairs-20260926' AND kind='game_id'").fetchone()[0]==17
    plan=json.loads((ROOT/'research/database-audit/import-repairs.json').read_text(encoding='utf-8'))
    for item in plan:
        if item['status']=='game_identity_only':
            assert not db.execute("SELECT 1 FROM printings WHERE source='local-review:import-repairs-20260926' AND record_key=?",(item['record_key'],)).fetchone()
    additions={t:db.execute(f'SELECT count(*) FROM main.{t}').fetchone()[0]-db.execute(f'SELECT count(*) FROM previous.{t}').fetchone()[0] for t in ('names','identifiers','printings')}
result={'status':'passed','all_original_observations_preserved':True,'statuses':statuses,'additions':additions,'foreign_keys':'ok','quick_check':'ok'}
(ROOT/'research/database-audit/import-repairs-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
