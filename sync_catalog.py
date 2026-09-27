"""Add registry identities and artwork assets without deleting images or references."""
import hashlib,json,sqlite3
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image
from catalog import ROOT,DB,normalized

def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)

def enrich(db,registry,asset_root,manifest,extra=()):
    """Mutates only the supplied staging connection. Original media are read-only.

    `asset_root`/`manifest` is the YGOPRODeck cropped-art download; `extra` adds
    more downloads of the same format as (asset_root, manifest, kind), e.g. the
    whole-card images (kind 'card', which the pilot can use)."""
    stats={'added_cards':0,'added_refs':0,'repaired_paths':[],'unavailable':[],
           'policy':'Keep every file and reference; hashes are descriptive, never deduplication keys.'}
    db.execute('CREATE TABLE IF NOT EXISTS asset_sources(ref_id TEXT PRIMARY KEY,source_url TEXT,manifest_path TEXT,metadata_json TEXT,availability TEXT)')
    known={r[0] for r in db.execute('SELECT id FROM cards')}
    with closing(readonly(registry)) as reg:
        reg.execute('BEGIN')
        identities=reg.execute('SELECT id,card_type FROM cards').fetchall()
        names={}
        for uid,lang,name,description in reg.execute("SELECT card_id,language,name,description FROM names ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 ELSE 1 END,source,name"):
            names.setdefault(uid,{}).setdefault(lang,{'name':name,'effect':description})
        arts=dict(reg.execute('SELECT id,card_id FROM artworks'))
        for uid,kind in identities:
            if uid in known:continue
            texts=names.get(uid,{})
            db.execute('INSERT INTO cards VALUES (?,?,?,?,?,?)',(uid,texts.get('en',{}).get('name',''),texts.get('es',{}).get('name',''),
                normalized(' '.join(t['name'] for t in texts.values())),kind or 'unknown',json.dumps(texts,ensure_ascii=False)))
            stats['added_cards']+=1;known.add(uid)
    # A broken filename can be repaired only with an exact content-hash match.
    for ref_id,path,digest in db.execute("SELECT ref_id,path,sha256 FROM refs WHERE source='cardsoricabr'").fetchall():
        if (ROOT/path).is_file():continue
        sid=ref_id.split(':',1)[1]
        candidates=list((ROOT/'downloads/cardsoricabr/files').glob(sid+'__*'))
        valid=[p for p in candidates if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest]
        if len(valid)==1:
            new=valid[0].relative_to(ROOT).as_posix()
            db.execute('UPDATE refs SET path=? WHERE ref_id=?',(new,ref_id))
            stats['repaired_paths'].append({'ref_id':ref_id,'old':path,'new':new})
    for asset_root,manifest,kind in [(asset_root,manifest,'art'),*extra]:
        if not Path(manifest).exists():continue
        manifest=json.loads(Path(manifest).read_text(encoding='utf-8'))
        for art,item in manifest['items'].items():
            ref_id=f'ygoprodeck:{kind}:'+art
            uid=item['card_id'];path=(asset_root/item['path']).resolve()
            if not path.is_relative_to(asset_root.resolve()):raise ValueError('Asset path escapes source directory')
            state='missing'
            if item.get('status')=='ok' and path.is_file():
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                if digest!=item.get('sha256'):raise ValueError('Asset hash mismatch: '+str(path))
                with Image.open(path) as im:
                    width,height=im.size;im.verify()
                if uid not in known or arts.get(art)!=uid:raise ValueError('Invalid artwork identity: '+art)
                values=(ref_id,'ygoprodeck',item.get('image_source_id'),kind,path.relative_to(ROOT).as_posix(),
                    names.get(uid,{}).get('en',{}).get('name',art),digest,width,height,uid,art,'linked',
                    'Registry artwork UUID and source URL manifest; not human visual review',json.dumps([uid]))
                existing=db.execute('SELECT * FROM refs WHERE ref_id=?',(ref_id,)).fetchone()
                if existing is None:
                    db.execute('INSERT INTO refs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values);stats['added_refs']+=1
                elif tuple(existing)!=values:raise ValueError('Existing reference differs; review required: '+ref_id)
                state='available'
            else:stats['unavailable'].append(ref_id)
            db.execute('INSERT INTO asset_sources VALUES (?,?,?,?,?) ON CONFLICT(ref_id) DO UPDATE SET source_url=excluded.source_url,manifest_path=excluded.manifest_path,metadata_json=excluded.metadata_json,availability=excluded.availability',
                       (ref_id,item.get('url'),str(asset_root/'manifest.json'),json.dumps(item,ensure_ascii=False),state))
    if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Invalid staging database')
    if db.execute('SELECT count(*) FROM refs r LEFT JOIN cards c ON c.id=r.card_id WHERE r.card_id IS NOT NULL AND c.id IS NULL').fetchone()[0]:raise ValueError('Dangling identity')
    return stats

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    target=ROOT/'research/database-audit'/('sync-'+stamp);target.mkdir(parents=True)
    before=target/'catalog-before.sqlite';stage=target/'catalog-stage.sqlite'
    with closing(readonly(DB)) as source,closing(sqlite3.connect(before)) as backup:source.backup(backup)
    with closing(readonly(before)) as source,closing(sqlite3.connect(stage)) as dest:source.backup(dest)
    with closing(sqlite3.connect(stage)) as db:
        stats=enrich(db,ROOT/'data/registry/registry.sqlite',ROOT/'downloads/ygoprodeck-art',ROOT/'downloads/ygoprodeck-art/manifest.json',
                     extra=[(ROOT/'downloads/ygoprodeck-cards',ROOT/'downloads/ygoprodeck-cards/manifest.json','card')])
        db.commit()
    # Publish additions and verified path repairs atomically. Existing rows are
    # compared with the backup first; no DROP, DELETE or replacement of media.
    with closing(sqlite3.connect(DB,timeout=15)) as live:
        live.execute('ATTACH DATABASE ? AS baseline',(str(before),));live.execute('ATTACH DATABASE ? AS staged',(str(stage),))
        live.execute('BEGIN IMMEDIATE')
        try:
            for table in ('cards','refs','localizations'):
                for a,b in (('main','baseline'),('baseline','main')):
                    if live.execute(f'SELECT 1 FROM (SELECT * FROM {a}.{table} EXCEPT SELECT * FROM {b}.{table}) LIMIT 1').fetchone():raise RuntimeError('Catalog changed during preparation; retry sync')
            live.execute('INSERT INTO cards SELECT s.* FROM staged.cards s WHERE NOT EXISTS (SELECT 1 FROM main.cards c WHERE c.id=s.id)')
            live.execute('INSERT INTO refs SELECT s.* FROM staged.refs s WHERE NOT EXISTS (SELECT 1 FROM main.refs r WHERE r.ref_id=s.ref_id)')
            for repair in stats['repaired_paths']:live.execute('UPDATE refs SET path=? WHERE ref_id=?',(repair['new'],repair['ref_id']))
            live.execute('CREATE TABLE IF NOT EXISTS asset_sources(ref_id TEXT PRIMARY KEY,source_url TEXT,manifest_path TEXT,metadata_json TEXT,availability TEXT)')
            for row in live.execute('SELECT * FROM staged.asset_sources').fetchall():
                live.execute('INSERT INTO asset_sources VALUES (?,?,?,?,?) ON CONFLICT(ref_id) DO UPDATE SET source_url=excluded.source_url,manifest_path=excluded.manifest_path,metadata_json=excluded.metadata_json,availability=excluded.availability',row)
            live.commit()
        except BaseException:live.rollback();raise
        stats['total_cards']=live.execute('SELECT count(*) FROM cards').fetchone()[0]
        stats['total_refs']=live.execute('SELECT count(*) FROM refs').fetchone()[0]
        stats['statuses']=dict(live.execute('SELECT status,count(*) FROM refs GROUP BY status'))
    stats.update(completed_at=datetime.now(timezone.utc).isoformat(),backup=str(before),stage=str(stage))
    (target/'result.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    summary_path=ROOT/'data/catalog/summary.json'
    summary=json.loads(summary_path.read_text(encoding='utf-8'));summary.update(cards=stats['total_cards'],references=stats['total_refs'],statuses=stats['statuses'],last_sync=stats['completed_at'])
    # Historical language coverage is not reused as current coverage.
    with closing(readonly(DB)) as db:
        texts=[json.loads(r[0]) for r in db.execute('SELECT texts_json FROM cards')]
        summary['names_by_language']={l:sum(bool(t.get(l,{}).get('name')) for t in texts) for l in ('en','es','de','fr','pt')}
        summary['duplicate_hash_groups']=db.execute('SELECT count(*) FROM (SELECT sha256 FROM refs GROUP BY sha256 HAVING count(*)>1)').fetchone()[0]
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in stats.items() if k!='unavailable'},ensure_ascii=False,indent=2));print('Unavailable manifest entries:',len(stats['unavailable']))

if __name__=='__main__':main()
