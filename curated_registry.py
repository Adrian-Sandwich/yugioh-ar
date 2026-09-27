"""Versioned, reversible identity resolution over preserved source observations."""
import hashlib,json,re,sqlite3,unicodedata
from collections import defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from ygo_source import ROOT,ARCHIVE,records
from printing_art_links import build_links,export_evidence

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())

def evaluate_pair(a,b):
    """Passcode alone never establishes identity. No fuzzy effect comparison."""
    codes=set(a.get('passwords',[]))&set(b.get('passwords',[]))
    codes={p for p in codes if re.fullmatch(r'[0-9]{8}',p)}
    ca=a.get('externalIDs',{}).get('dbID');cb=b.get('externalIDs',{}).get('dbID')
    evidence={'shared_passcodes':sorted(codes),'neuron_cids':[ca,cb],
        'equal_effect_languages':[l for l in sorted(set(a.get('text',{}))&set(b.get('text',{})))
            if normalized(a['text'][l].get('effect','')) and normalized(a['text'][l].get('effect',''))==normalized(b['text'][l].get('effect',''))]}
    if ca and cb and ca!=cb:return 'conflict',evidence
    if not codes or not a.get('cardType') or a.get('cardType')!=b.get('cardType'):return 'review',evidence
    for field in ('subcategory','level','rank','attribute','monsterType','atk','def'):
        if field in a and field in b and a[field]!=b[field]:return 'review',evidence
    na=re.sub(r'\s*\(card\)$','',a.get('text',{}).get('en',{}).get('name',''),flags=re.I)
    nb=re.sub(r'\s*\(card\)$','',b.get('text',{}).get('en',{}).get('name',''),flags=re.I)
    corroborated=bool(ca and ca==cb) or bool(normalized(na) and normalized(na)==normalized(nb))
    return ('accepted' if corroborated and evidence['equal_effect_languages'] else 'review'),evidence

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    directory=ROOT/'data/curated'/stamp;directory.mkdir(parents=True)
    raw={c['id']:c for c in records('cards')};by_code=defaultdict(set)
    for uid,c in raw.items():
        for p in c.get('passwords',[]):
            if re.fullmatch(r'[0-9]{8}',p):by_code[p].add(uid)
    corrections=json.loads((ROOT/'research/database-audit/reviewed-corrections.json').read_text(encoding='utf-8'))
    reviewed={frozenset((r['alias'],r['canonical'])):r for r in corrections['aliases']}
    for r in corrections['aliases']:
        for uid,digest in r['record_sha256'].items():
            if hashlib.sha256(json.dumps(raw[uid],sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=digest:raise ValueError('Reviewed record changed: '+uid)
    for entry in corrections['evidence_files']:
        if hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Reviewed evidence changed')
    decisions=[];aliases={};seen=set()
    for code,ids in sorted(by_code.items()):
        if len(ids)<2:continue
        key=tuple(sorted(ids))
        if key in seen:continue
        seen.add(key)
        if len(ids)!=2:
            decisions.append({'members':list(key),'status':'review','reason':'More than two source identities'});continue
        a,b=(raw[i] for i in key);state,evidence=evaluate_pair(a,b)
        # Preserve the more complete existing UUID; no new identity UUID needed.
        preferred=sorted((a,b),key=lambda c:(-len(c.get('text',{})),-len(c.get('sets',[])),c['id']))[0]['id']
        review=reviewed.get(frozenset(key))
        if review:
            state='accepted';preferred=review['canonical'];evidence['review']=review
        elif state=='conflict' and any(d['card_id'] in key and d['value']==code for d in corrections['identifier_decisions']):
            state='resolved_distinct_cards';evidence['identifier_review']=[d for d in corrections['identifier_decisions'] if d['card_id'] in key and d['value']==code]
        entry={'members':list(key),'canonical_id':preferred if state=='accepted' else None,'status':state,
               'names':[c.get('text',{}).get('en',{}).get('name') for c in (a,b)],'evidence':evidence,
               'source_records':['cards/'+i+'.json' for i in key]}
        decisions.append(entry)
        if state=='accepted':
            other=next(i for i in key if i!=preferred)
            if other in aliases or preferred in aliases or other in aliases.values():raise ValueError('Overlapping groups need explicit review')
            aliases[other]=preferred
    path=directory/'registry.sqlite'
    with closing(sqlite3.connect((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(path)) as dest:
        src.backup(dest,pages=2048,sleep=.05)
    print('Consistent registry snapshot created',flush=True)
    with closing(sqlite3.connect(path,uri=True)) as db:
        ids={r[0] for r in db.execute('SELECT id FROM cards')}
        if not set(aliases).union(aliases.values())<=ids:raise ValueError('Alias identity absent from snapshot')
        db.executescript('''
            CREATE TABLE identity_map(source_card_id TEXT PRIMARY KEY,canonical_card_id TEXT NOT NULL,decision TEXT NOT NULL);
            CREATE INDEX identity_map_canonical ON identity_map(canonical_card_id);
            CREATE TABLE resolution_decisions(id INTEGER PRIMARY KEY,status TEXT,detail_json TEXT);
            CREATE TABLE release_metadata(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE identifier_decisions(card_id TEXT,kind TEXT,value TEXT,status TEXT,detail_json TEXT,PRIMARY KEY(card_id,kind,value));
            CREATE VIEW resolved_cards AS SELECT c.* FROM cards c JOIN identity_map m ON m.source_card_id=c.id WHERE m.source_card_id=m.canonical_card_id;
            CREATE VIEW resolved_names AS SELECT m.canonical_card_id,n.* FROM names n JOIN identity_map m ON m.source_card_id=n.card_id;
            CREATE VIEW resolved_identifiers AS SELECT m.canonical_card_id,i.* FROM identifiers i JOIN identity_map m ON m.source_card_id=i.card_id WHERE NOT EXISTS (SELECT 1 FROM identifier_decisions d WHERE d.card_id=i.card_id AND d.kind=i.kind AND d.value=i.value AND d.status='disputed');
            CREATE VIEW resolved_artworks AS SELECT m.canonical_card_id,a.* FROM artworks a JOIN identity_map m ON m.source_card_id=a.card_id;
            CREATE VIEW resolved_printings AS SELECT m.canonical_card_id,p.* FROM printings p JOIN identity_map m ON m.source_card_id=p.card_id;
            CREATE VIEW printing_art_candidates AS
                SELECT p.id AS printing_id,p.canonical_card_id,a.id AS artwork_id,
                    'candidate_not_verified' AS status,
                    CASE WHEN p.image_url=a.card_url AND p.image_url IS NOT NULL THEN 'same_declared_url' ELSE 'same_identity_only' END AS evidence
                FROM resolved_printings p JOIN resolved_artworks a ON a.canonical_card_id=p.canonical_card_id;
        ''')
        db.executemany('INSERT INTO identity_map VALUES (?,?,?)',[(i,aliases.get(i,i),'accepted_alias' if i in aliases else 'original') for i in sorted(ids)])
        db.executemany('INSERT INTO resolution_decisions(status,detail_json) VALUES (?,?)',[(d['status'],json.dumps(d,ensure_ascii=False)) for d in decisions])
        db.executemany('INSERT INTO identifier_decisions VALUES (?,?,?,?,?)',[(d['card_id'],d['kind'],d['value'],d['status'],json.dumps(d,ensure_ascii=False)) for d in corrections['identifier_decisions']])
        # Keep every visual row; do not collapse by hash, card, artwork or path.
        db.execute('ATTACH DATABASE ? AS visual',((ROOT/'data/catalog/catalog.sqlite').as_uri()+'?mode=ro',))
        db.execute('CREATE TABLE visual_references AS SELECT * FROM visual.refs')
        db.execute('CREATE UNIQUE INDEX visual_ref_id ON visual_references(ref_id)')
        db.execute('CREATE INDEX visual_ref_card ON visual_references(card_id)')
        db.execute('CREATE TABLE asset_sources AS SELECT * FROM visual.asset_sources')
        db.execute('CREATE VIEW resolved_visual_references AS SELECT m.canonical_card_id,r.* FROM visual_references r LEFT JOIN identity_map m ON m.source_card_id=r.card_id')
        printing_art_summary=build_links(db)
        visual_review_summary=export_evidence(db,directory)
        db.commit()
        if db.execute('PRAGMA main.quick_check').fetchone()[0]!='ok':raise ValueError('Snapshot integrity failure')
        assert db.execute('SELECT count(*) FROM cards').fetchone()[0]==len(ids)
        assert db.execute('SELECT count(*) FROM resolved_cards').fetchone()[0]==len(ids)-len(aliases)
        assert not db.execute('SELECT 1 FROM identity_map a JOIN identity_map b ON a.canonical_card_id=b.source_card_id WHERE b.canonical_card_id!=b.source_card_id LIMIT 1').fetchone()
        visual_count=db.execute('SELECT count(*) FROM visual_references').fetchone()[0]
        assert visual_count==db.execute('SELECT count(*) FROM visual.refs').fetchone()[0]
        conflicts=db.execute("SELECT value,count(DISTINCT canonical_card_id) FROM resolved_identifiers WHERE kind='passcode' GROUP BY value HAVING count(DISTINCT canonical_card_id)>1").fetchall()
        with ARCHIVE.open('rb') as stream:archive_hash=hashlib.file_digest(stream,'sha256').hexdigest()
        summary={'created_at':datetime.now(timezone.utc).isoformat(),'version':stamp,'source_cards':len(ids),
                 'canonical_cards':len(ids)-len(aliases),'accepted_aliases':len(aliases),
                 'decisions':dict(db.execute('SELECT status,count(*) FROM resolution_decisions GROUP BY status')),
                 'remaining_passcode_conflicts':[{'passcode':c,'identities':n} for c,n in conflicts],
                 'visual_references_preserved':visual_count,'source_archive_sha256':archive_hash,
                 'printing_art':printing_art_summary,'visual_review':visual_review_summary,
                 'policy':'All raw rows and images retained. Exact unique URLs support source-declared art links, not independent verification. Other associations remain candidates.',
                 'scope':'Versioned snapshot. Viewers use live databases with a pinned identity map.'}
        db.execute('INSERT INTO release_metadata VALUES (?,?)',('summary',json.dumps(summary,ensure_ascii=False)));db.commit()
    (directory/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2),encoding='utf-8')
    (directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    pointer=ROOT/'data/curated/latest.json';pending=pointer.with_suffix('.tmp')
    pending.write_text(json.dumps({'version':stamp,'database':path.relative_to(ROOT).as_posix(),'summary':summary},ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(pointer)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
