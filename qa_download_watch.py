"""Completion requires expected identities in both cache and imported sources."""
import json,shutil,sqlite3,sys,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research'))
import watch_download

root=ROOT/'research/qa'/('download-watch-'+uuid.uuid4().hex)
cache=root/'data/registry/neuron';cache.mkdir(parents=True)
(cache/'index-en-1.json').write_text(json.dumps({'language':'en','cards':[{'cid':1},{'cid':2}]}))
for name in ('card-en-1.json','card-en-99.json'):(cache/name).write_text('{}')
db=sqlite3.connect(root/'data/registry/registry.sqlite');db.execute('CREATE TABLE sources(id)')
db.execute("INSERT INTO sources VALUES ('neuron:card-en-1')");db.commit()
status={'progress_age_seconds':1,'reported_state':'complete_with_errors','remaining_files':0,'total_discovered':2}
with patch.object(watch_download,'ROOT',root),patch.object(watch_download,'status',return_value=status):
    first,terminal=watch_download.inspect();assert terminal and first['watch_state']=='finished_with_pending_work'
    assert first['expected_missing_files']==['card-en-2']
    (cache/'card-en-2.json').write_text('{}')
    assert watch_download.inspect()[0]['watch_state']=='finished_with_pending_work'
    db.execute("INSERT INTO sources VALUES ('neuron:card-en-2')");db.commit()
    assert watch_download.inspect()[0]['watch_state']=='complete_pending_content_audit'
db.close();shutil.rmtree(root)
print('PASS: equal file count cannot hide a missing expected card; cache and import must both cover index')
