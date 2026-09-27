"""Read-only inventory of live registries; writes reports, never source databases."""
import csv,json,os,sqlite3,time
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/database-audit'
LANGS=('en','es','de','fr','pt')

def connect(path):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db

def rows(db,sql):return [dict(r) for r in db.execute(sql)]
def scalar(db,sql):return db.execute(sql).fetchone()[0]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'observed_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Read snapshots per database, not an atomic snapshot of all files. Download remains active.'}
    with closing(connect(ROOT/'data/registry/registry.sqlite')) as db:
        db.execute('BEGIN')
        r={};report['registry']=r
        r['counts']={t:scalar(db,f'SELECT count(*) FROM {t}') for t in ('cards','names','identifiers','artworks','products','printings','sources','issues')}
        r['quick_check']=scalar(db,'PRAGMA quick_check')
        r['foreign_key_violations']=rows(db,'PRAGMA foreign_key_check')[:25]
        r['origins']=rows(db,'SELECT origin,count(*) AS n FROM cards GROUP BY origin')
        r['types']=rows(db,'SELECT card_type,count(*) AS n FROM cards GROUP BY card_type')
        r['name_coverage']=rows(db,'SELECT language,count(*) AS observations,count(DISTINCT card_id) AS cards FROM names GROUP BY language ORDER BY language')
        r['distinct_names']=scalar(db,'SELECT count(*) FROM (SELECT DISTINCT card_id,language,name FROM names)')
        r['name_variants']=rows(db,'SELECT language,count(*) AS cards_with_multiple_spellings FROM (SELECT language,card_id FROM names GROUP BY language,card_id HAVING count(DISTINCT name)>1) GROUP BY language')
        r['identifiers']=rows(db,'SELECT kind,count(*) AS observations,count(DISTINCT value) AS values_count,count(DISTINCT card_id) AS cards FROM identifiers GROUP BY kind')
        r['cards_without_passcode']=scalar(db,"SELECT count(*) FROM cards WHERE id NOT IN (SELECT card_id FROM identifiers WHERE kind='passcode' AND card_id IS NOT NULL)")
        r['invalid_passcodes']=rows(db,"SELECT DISTINCT card_id,value FROM identifiers WHERE kind='passcode' AND (length(value)!=8 OR value GLOB '*[^0-9]*')")
        r['passcode_collisions']=rows(db,"SELECT value,count(DISTINCT card_id) AS identities FROM identifiers WHERE kind='passcode' GROUP BY value HAVING count(DISTINCT card_id)>1")
        r['multiple_passcodes']=scalar(db,"SELECT count(*) FROM (SELECT card_id FROM identifiers WHERE kind='passcode' GROUP BY card_id HAVING count(DISTINCT value)>1)")
        r['neuron_collisions']=rows(db,'SELECT neuron_cid,count(*) AS identities FROM cards WHERE neuron_cid IS NOT NULL GROUP BY neuron_cid HAVING count(*)>1')
        r['printings_by_source']=rows(db,"SELECT CASE WHEN source LIKE 'neuron:%' THEN 'neuron' ELSE source END AS source_family,count(*) AS observations FROM printings GROUP BY source_family")
        r['printings_by_language']=rows(db,'SELECT language,count(*) AS observations,count(DISTINCT card_id) AS cards,count(DISTINCT set_code) AS set_codes FROM printings GROUP BY language')
        r['printing_missing_fields']={f:scalar(db,f"SELECT count(*) FROM printings WHERE {f} IS NULL OR {f}=''") for f in ('set_code','language','rarity','edition','artwork_id','image_url','release_date','product_id')}
        r['printing_distinct_observed_tuples']=scalar(db,'SELECT count(*) FROM (SELECT DISTINCT card_id,product_id,language,locale,set_code,rarity,edition,artwork_id,release_date,image_url FROM printings)')
        r['printing_card_code_language_groups']=scalar(db,"SELECT count(*) FROM (SELECT DISTINCT card_id,set_code,language FROM printings WHERE set_code IS NOT NULL AND set_code!='')")
        r['set_codes_multiple_identities']=scalar(db,"SELECT count(*) FROM (SELECT set_code FROM printings WHERE set_code IS NOT NULL AND set_code!='' GROUP BY set_code HAVING count(DISTINCT card_id)>1)")
        r['set_code_collision_examples']=rows(db,"SELECT set_code,count(DISTINCT card_id) AS identities FROM printings WHERE set_code IS NOT NULL AND set_code!='' GROUP BY set_code HAVING count(DISTINCT card_id)>1 LIMIT 15")
        r['artwork_cards']=scalar(db,'SELECT count(DISTINCT card_id) FROM artworks')
        r['cards_multiple_artworks']=scalar(db,'SELECT count(*) FROM (SELECT card_id FROM artworks GROUP BY card_id HAVING count(*)>1)')
        r['issues']=rows(db,'SELECT kind,count(*) AS n FROM issues GROUP BY kind')
        r['issue_examples']=rows(db,'SELECT * FROM issues LIMIT 15')
        imported={x[0].removeprefix('neuron:')+'.json' for x in db.execute("SELECT id FROM sources WHERE id LIKE 'neuron:card-%'")}
        identities=rows(db,'SELECT id,neuron_cid,card_type FROM cards ORDER BY id')
        names=defaultdict(lambda:defaultdict(set));codes=defaultdict(set)
        for uid,lang,name in db.execute('SELECT DISTINCT card_id,language,name FROM names'):
            if lang in LANGS:names[uid][lang].add(name)
        for uid,code in db.execute("SELECT DISTINCT card_id,value FROM identifiers WHERE kind='passcode'"):codes[uid].add(code)
        r['all_five_languages']=sum(all(names[c['id']][l] for l in LANGS) for c in identities)
        db.rollback()
    with (OUT/'identities.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream);writer.writerow(['card_id','neuron_cid','card_type','passcodes',*LANGS])
        for c in identities:
            uid=c['id'];writer.writerow([uid,c['neuron_cid'],c['card_type'],json.dumps(sorted(codes[uid])),*[json.dumps(sorted(names[uid][l]),ensure_ascii=False) for l in LANGS]])
    registry_ids={c['id'] for c in identities}
    with closing(connect(ROOT/'data/catalog/catalog.sqlite')) as db:
        db.execute('BEGIN');c={};report['catalog']=c
        c['counts']={t:scalar(db,f'SELECT count(*) FROM {t}') for t in ('cards','refs','localizations')}
        c['references_by_source_status']=rows(db,'SELECT source,status,count(*) AS n FROM refs GROUP BY source,status')
        c['distinct_image_hashes']=scalar(db,"SELECT count(DISTINCT sha256) FROM refs WHERE sha256 IS NOT NULL AND sha256!=''")
        c['duplicate_hash_groups']=scalar(db,"SELECT count(*) FROM (SELECT sha256 FROM refs WHERE sha256 IS NOT NULL AND sha256!='' GROUP BY sha256 HAVING count(*)>1)")
        c['linked_cards']=scalar(db,'SELECT count(DISTINCT card_id) FROM refs WHERE card_id IS NOT NULL')
        refs=rows(db,'SELECT ref_id,path,card_id,artwork_id,status FROM refs');catalog_ids={x[0] for x in db.execute('SELECT id FROM cards')};db.rollback()
    c['cards_missing_from_registry']=len(catalog_ids-registry_ids);c['registry_cards_missing_from_catalog']=len(registry_ids-catalog_ids)
    c['missing_files']=[];c['unsafe_paths']=[]
    for ref in refs:
        if not ref['path']:c['missing_files'].append(ref['ref_id']);continue
        p=(ROOT/ref['path']).resolve()
        if not p.is_relative_to(ROOT):c['unsafe_paths'].append(ref['ref_id'])
        elif not p.is_file():c['missing_files'].append(ref['ref_id'])
    c['reference_ids_missing_from_registry']=sorted({x['card_id'] for x in refs if x['card_id'] and x['card_id'] not in registry_ids})
    with closing(connect(ROOT/'data/catalog/reviews.sqlite')) as db:
        report['reviews']={'decisions':rows(db,'SELECT action,count(*) AS n FROM decisions GROUP BY action')}
        decisions=rows(db,'SELECT ref_id,action,card_id FROM decisions')
        ref_ids={x['ref_id'] for x in refs}
        report['reviews']['orphan_references']=[d for d in decisions if d['ref_id'] not in ref_ids]
        report['reviews']['invalid_approved_ids']=[d for d in decisions if d['action']=='approve' and d['card_id'] not in registry_ids]
    cached={e.name for e in os.scandir(ROOT/'data/registry/neuron') if e.name.startswith('card-') and e.name.endswith('.json')}
    report['neuron_cache']={'cached_details':len(cached),'imported_detail_sources':len(imported),
        'cached_not_imported':sorted(cached-imported),'imported_without_cache':sorted(imported-cached),
        'warning':'File scan follows SQLite snapshot; a small import lag can be normal during download. Contents/hashes not revalidated here.'}
    report['download_folders']={}
    for folder in (ROOT/'downloads').iterdir():
        if not folder.is_dir():continue
        count=0;size=0;extensions=Counter()
        for base,dirs,files in os.walk(folder):
            for filename in files:
                p=Path(base)/filename
                try:size+=p.stat().st_size
                except OSError:continue
                count+=1;extensions[p.suffix.lower()]+=1
        report['download_folders'][folder.name]={'files':count,'bytes':size,'extensions':dict(extensions.most_common(10))}
    report['database_files']={str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'wal_bytes':Path(str(p)+'-wal').stat().st_size if Path(str(p)+'-wal').exists() else 0} for p in (ROOT/'data').rglob('*.sqlite')}
    report['completed_at']=datetime.now(timezone.utc).isoformat()
    (OUT/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
