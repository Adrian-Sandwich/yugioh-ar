"""Traceable additive repairs; no source claims, references or image files deleted."""
import json,re,sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from registry import ROOT,DB,connect,source,identifier,printing,import_neuron,import_neuron_index,resolved_neuron_matches

def main():
    out=ROOT/'research/database-audit';plan=[]
    with closing(connect()) as db,closing(sqlite3.connect((ROOT/'downloads/tdoane-reference/YGOPRO/cdb/cards.cdb').as_uri()+'?mode=ro',uri=True)) as game:
        for issue in db.execute("SELECT * FROM issues WHERE kind IN ('invalid_passcode','unmapped_game_pack')").fetchall():
            item=dict(issue)
            if issue['kind']=='invalid_passcode':
                m=re.fullmatch(r'([0-9]{8})<!--.*-->',issue['detail'],re.S)
                uid=Path(issue['record_key']).stem
                exists=m and db.execute("SELECT 1 FROM identifiers WHERE card_id=? AND kind='passcode' AND value=?",(uid,m[1])).fetchone()
                item.update(status='already_present_clean' if exists else 'review',card_id=uid,clean_value=m[1] if m else None)
            else:
                code=issue['detail'];gid=issue['record_key'];cursor=int(gid);seen=set();terminal_name=None
                while cursor not in seen:
                    seen.add(cursor);row=game.execute('SELECT d.alias,t.name FROM datas d JOIN texts t USING(id) WHERE d.id=?',(cursor,)).fetchone()
                    if row is None:break
                    terminal_name=row[1]
                    if not row[0]:break
                    cursor=row[0]
                set_ids={r[0] for r in db.execute('SELECT DISTINCT card_id FROM printings WHERE set_code=?',(code,))}
                name_ids={r[0] for r in db.execute("SELECT DISTINCT card_id FROM names WHERE language='en' AND name=?",(terminal_name,))} if terminal_name and terminal_name!='Token' else set()
                serial_ids={r[0] for r in db.execute("SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?",(gid,))}
                candidates=set_ids&(name_ids|serial_ids)
                if len(candidates)==1:item.update(status='printing_recovered',card_id=next(iter(candidates)))
                elif len(name_ids)==1:item.update(status='game_identity_only',card_id=next(iter(name_ids)))
                else:item.update(status='review',card_id=None)
                item.update(game_name=terminal_name,alias_chain=sorted(seen),set_candidates=sorted(set_ids))
            plan.append(item)
    evidence=out/'import-repairs.json';evidence.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f');backup=out/('registry-before-repairs-'+stamp+'.sqlite')
    with closing(sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
    with closing(connect()) as db,closing(sqlite3.connect((ROOT/'downloads/tdoane-reference/YGOPRO/pack/pack.db').as_uri()+'?mode=ro',uri=True)) as packs:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS issue_resolutions(kind TEXT,source TEXT,record_key TEXT,detail TEXT,status TEXT,evidence_json TEXT,PRIMARY KEY(kind,source,record_key,detail))')
        sid='local-review:import-repairs-20260926';source(db,sid,None,evidence,{'policy':'additive; physical printing requires matching set plus identity evidence'})
        for item in plan:
            if item['kind']=='unmapped_game_pack' and item['card_id']:
                identifier(db,item['card_id'],'game_id',item['record_key'],sid,item['record_key'])
                if item['status']=='printing_recovered':
                    for code,pack,rarity,date in packs.execute('SELECT pack_id,pack,rarity,date FROM pack WHERE id=?',(item['record_key'],)):
                        m=re.search(r'-(EN|SP|DE|FR|PT)\w*$',code or '')
                        lang={'EN':'en','SP':'es','DE':'de','FR':'fr','PT':'pt'}.get(m[1]) if m else None
                        printing(db,sid,item['record_key'],item['card_id'],language=lang,code=code,rarity=rarity,date=date if re.fullmatch(r'\d{4}-\d{2}-\d{2}',date or '') else None,evidence={'pack_name':pack,'review':item,'raw_date':date})
            db.execute('INSERT OR REPLACE INTO issue_resolutions VALUES (?,?,?,?,?,?)',(item['kind'],item['source'],item['record_key'],item['detail'],item['status'],json.dumps(item,ensure_ascii=False)))
        skipped=db.execute("SELECT * FROM issues WHERE kind='ambiguous_neuron_cid'").fetchall();replayed=set();resolved=0
        for issue in skipped:
            matches=resolved_neuron_matches(db,int(issue['record_key']))
            if len(matches)!=1:continue
            path=ROOT/'data/registry/neuron'/(issue['source'].removeprefix('neuron:')+'.json')
            if path not in replayed:
                (import_neuron if path.name.startswith('card-') else import_neuron_index)(db,path);replayed.add(path)
            db.execute('INSERT OR REPLACE INTO issue_resolutions VALUES (?,?,?,?,?,?)',(issue['kind'],issue['source'],issue['record_key'],issue['detail'],'replayed_with_alias',json.dumps({'canonical_id':matches[0][0],'cached_source':str(path)})))
            resolved+=1
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Registry validation failed')
        db.commit()
    report={'statuses':dict(Counter(p['status'] for p in plan)),'neuron_issues_resolved':resolved,'cached_sources_replayed':len(replayed),'backup':str(backup),'images':'unchanged'}
    (out/'import-repairs-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
