"""Build/query multilingual identity and printing observations with provenance."""
import argparse, csv, hashlib, json, re, sqlite3, uuid, zipfile
from datetime import datetime, timezone
from ygo_source import ROOT, ARCHIVE, records
DATA=ROOT/'data/registry'
DB=DATA/'registry.sqlite'
LANGS=('en','es','de','fr','pt')
def now(): return datetime.now(timezone.utc).isoformat()
def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def connect(path=DB):
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db
SCHEMA='''
CREATE TABLE sources(id TEXT PRIMARY KEY,url TEXT,artifact TEXT,sha256 TEXT,observed_at TEXT,metadata_json TEXT);
CREATE TABLE cards(id TEXT PRIMARY KEY,card_type TEXT,neuron_cid INTEGER,origin TEXT);
CREATE INDEX cards_cid ON cards(neuron_cid);
CREATE TABLE card_facts(card_id TEXT PRIMARY KEY REFERENCES cards(id),facts_json TEXT,source TEXT REFERENCES sources(id));
CREATE TABLE names(card_id TEXT REFERENCES cards(id),language TEXT,name TEXT,description TEXT,source TEXT REFERENCES sources(id),record_key TEXT,PRIMARY KEY(card_id,language,name,source));
CREATE TABLE identifiers(card_id TEXT REFERENCES cards(id),kind TEXT,value TEXT,source TEXT REFERENCES sources(id),record_key TEXT,PRIMARY KEY(card_id,kind,value,source));
CREATE TABLE artworks(id TEXT PRIMARY KEY,card_id TEXT REFERENCES cards(id),image_source_id TEXT,art_url TEXT,card_url TEXT,source TEXT REFERENCES sources(id));
CREATE TABLE products(id TEXT PRIMARY KEY,names_json TEXT,source TEXT REFERENCES sources(id));
CREATE TABLE printings(id TEXT PRIMARY KEY,card_id TEXT REFERENCES cards(id),product_id TEXT REFERENCES products(id),language TEXT,locale TEXT,set_code TEXT,rarity TEXT,edition TEXT,artwork_id TEXT,release_date TEXT,image_url TEXT,source TEXT REFERENCES sources(id),record_key TEXT,evidence_json TEXT);
CREATE INDEX names_card ON names(card_id,language);
CREATE INDEX identifiers_value ON identifiers(value,kind);
CREATE INDEX printings_card ON printings(card_id,language);
CREATE INDEX printings_code ON printings(set_code);
CREATE TABLE issues(kind TEXT,source TEXT,record_key TEXT,detail TEXT);
'''
def source(db,sid,url,path,meta=None):
    db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?)',(sid,url,str(path.relative_to(ROOT)),digest(path),now(),json.dumps(meta or {},ensure_ascii=False)))
def identifier(db,card,kind,value,sid,key):
    if value is not None: db.execute('INSERT OR IGNORE INTO identifiers VALUES (?,?,?,?,?)',(card,kind,str(value),sid,key))
def printing(db,sid,key,card,product=None,language=None,locale=None,code=None,rarity=None,edition=None,art=None,date=None,image=None,evidence=None):
    fields=(card,product,language,locale,code,rarity,edition,art,date,image,sid,key,json.dumps(evidence or {},ensure_ascii=False))
    pid=hashlib.sha256(json.dumps(fields,ensure_ascii=False).encode()).hexdigest()
    db.execute('INSERT OR IGNORE INTO printings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,*fields))
def build():
    DATA.mkdir(parents=True,exist_ok=True)
    staging=DATA/'registry.build.sqlite'
    if staging.exists(): staging.unlink()
    db=connect(staging); db.executescript(SCHEMA)
    with zipfile.ZipFile(ARCHIVE) as z:
        bad=z.testzip()
        if bad: raise ValueError(f'ZIP corrupto: {bad}')
        meta=json.loads(z.read('meta.json'))
    sid='ygojson-individual-20260925'
    source(db,sid,'https://github.com/iconmaster5326/YGOJSON/releases/download/v1/individual.zip',ARCHIVE,meta)
    for c in records('cards'):
        cid=c['id']; key=f'cards/{cid}.json'; ext=c.get('externalIDs',{})
        db.execute('INSERT INTO cards VALUES (?,?,?,?)',(cid,c.get('cardType'),ext.get('dbID'),'ygojson'))
        db.execute('INSERT INTO card_facts VALUES (?,?,?)',(cid,json.dumps({k:v for k,v in c.items() if k not in ('text','images','sets')},ensure_ascii=False),sid))
        for lang,t in c.get('text',{}).items():
            if t.get('name'): db.execute('INSERT OR IGNORE INTO names VALUES (?,?,?,?,?,?)',(cid,lang,t['name'],t.get('effect'),sid,key))
        for p in c.get('passwords',[]):
            p=str(p)
            if re.fullmatch(r'\d{1,8}',p): identifier(db,cid,'passcode',p.zfill(8),sid,key)
            else: db.execute('INSERT INTO issues VALUES (?,?,?,?)',('invalid_passcode',sid,key,p))
        identifier(db,cid,'neuron_cid',ext.get('dbID'),sid,key)
        identifier(db,cid,'ygoprodeck_card_id',ext.get('ygoprodeck',{}).get('id'),sid,key)
        for a in c.get('images',[]):
            db.execute('INSERT INTO artworks VALUES (?,?,?,?,?,?)',(a['id'],cid,str(a['password']) if a.get('password') is not None else None,a.get('art'),a.get('card'),sid))
            identifier(db,cid,'image_source_id',a.get('password'),sid,key)
    print('Cartas importadas',flush=True)
    for s in records('sets'):
        product=s['id']
        db.execute('INSERT INTO products VALUES (?,?,?)',(product,json.dumps(s.get('name',{}),ensure_ascii=False),sid))
        for block in s.get('contents',[]):
            # No physical printing is invented for virtual sets without locales.
            for locale in block.get('locales',[]):
                loc=s.get('locales',{}).get(locale,{})
                for p in block.get('cards',[]):
                    lang=p.get('language') or loc.get('language')
                    prefix,suffix=loc.get('prefix'),p.get('suffix')
                    code=prefix+suffix if prefix is not None and suffix is not None else None
                    evidence={'set_editions':loc.get('editions',block.get('editions',[])),'formats':loc.get('formats',block.get('formats',[])),'replica':p.get('replica',False)}
                    editions=[(edition or None,info[p['id']].get('image')) for edition,info in loc.get('cardInfo',{}).items() if p['id'] in info]
                    for edition,image in editions or [(None,None)]:
                        printing(db,sid,f"sets/{product}.json#{p['id']}",p['card'],product,lang,locale,code,p.get('rarity'),edition,p.get('imageID'),loc.get('date'),image,evidence)
    for cid,count in db.execute('SELECT neuron_cid,count(*) FROM cards WHERE neuron_cid IS NOT NULL GROUP BY neuron_cid HAVING count(*)>1').fetchall():
        db.execute('INSERT INTO issues VALUES (?,?,?,?)',('duplicate_neuron_cid',sid,str(cid),str(count)))
    import_game(db)
    for path in sorted((DATA/'neuron').glob('index-??-[0-9]*.json')): import_neuron_index(db,path)
    for path in sorted((DATA/'neuron').glob('card-*.json')): import_neuron(db,path)
    db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    db.close(); staging.replace(DB); export()
def import_game(db):
    game=ROOT/'downloads/tdoane-reference/YGOPRO/pack/pack.db'; catpath=ROOT/'data/catalog/catalog.sqlite'
    if not game.exists() or not catpath.exists(): return
    sid='tdoane-pack'
    source(db,sid,None,game,{'scope':'One row per game ID, partial printing history'})
    with sqlite3.connect(catpath.as_uri()+'?mode=ro',uri=True) as cat:
        mapping=dict(cat.execute("SELECT source_id,card_id FROM refs WHERE source='tdoane' AND kind='card' AND status='linked'"))
        source(db,'tdoane-localizations',None,catpath,{'mapping':'linked refs only'})
        for r in cat.execute('SELECT card_id,source_id,language,name,description FROM localizations'):
            if db.execute('SELECT 1 FROM cards WHERE id=?',(r[0],)).fetchone():
                db.execute('INSERT OR IGNORE INTO names VALUES (?,?,?,?,?,?)',(r[0],r[2],r[3],r[4],'tdoane-localizations',r[1]))
    with sqlite3.connect(game.as_uri()+'?mode=ro',uri=True) as con:
        for game_id,code,pack,rarity,date in con.execute('SELECT id,pack_id,pack,rarity,date FROM pack'):
            card=mapping.get(str(game_id))
            if not card:
                db.execute('INSERT INTO issues VALUES (?,?,?,?)',('unmapped_game_pack',sid,str(game_id),code)); continue
            identifier(db,card,'game_id',game_id,sid,str(game_id))
            m=re.search(r'-(EN|SP|DE|FR|PT)\w*$',code or '')
            lang={'EN':'en','SP':'es','DE':'de','FR':'fr','PT':'pt'}.get(m.group(1)) if m else None
            iso=date if re.fullmatch(r'\d{4}-\d{2}-\d{2}',date or '') else None
            printing(db,sid,str(game_id),card,language=lang,code=code,rarity=rarity,date=iso,evidence={'pack_name':pack,'raw_date':date,'language_evidence':'code' if lang else 'unknown'})
def import_neuron(db,path):
    item=json.loads(path.read_text(encoding='utf-8')); sid='neuron:'+path.stem
    source(db,sid,item['url'],path,{'fetched_at':item['fetched_at'],'html_sha256':item['html_sha256'],'parser_version':item['parser_version']})
    matches=db.execute('SELECT id FROM cards WHERE neuron_cid=?',(item['cid'],)).fetchall()
    if len(matches)>1:
        db.execute('INSERT INTO issues VALUES (?,?,?,?)',('ambiguous_neuron_cid',sid,str(item['cid']),json.dumps([r[0] for r in matches])))
        return
    row=matches[0] if matches else None
    cid=row[0] if row else str(uuid.uuid5(uuid.NAMESPACE_URL,f"https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid={item['cid']}"))
    if not row: db.execute('INSERT INTO cards VALUES (?,?,?,?)',(cid,None,item['cid'],'neuron'))
    identifier(db,cid,'neuron_cid',item['cid'],sid,'detail')
    db.execute('INSERT OR IGNORE INTO names VALUES (?,?,?,?,?,?)',(cid,item['language'],item['name'],None,sid,'#cardname'))
    for i,p in enumerate(item['printings']):
        printing(db,sid,str(i),cid,language=item['language'],code=p['set_code'],rarity=p['rarity'],date=p['release_date'],evidence={'product_name':p['product_name'],'product_url':p['product_url'],'rarity_id':p['rarity_id']})
def import_neuron_index(db,path):
    item=json.loads(path.read_text(encoding='utf-8')); sid='neuron:'+path.stem
    source(db,sid,item['url'],path,{'fetched_at':item['fetched_at'],'html_sha256':item['html_sha256'],'parser_version':item['parser_version']})
    for c in item['cards']:
        matches=db.execute('SELECT id FROM cards WHERE neuron_cid=?',(c['cid'],)).fetchall()
        if len(matches)>1:
            db.execute('INSERT INTO issues VALUES (?,?,?,?)',('ambiguous_neuron_cid',sid,str(c['cid']),json.dumps([r[0] for r in matches])))
            continue
        cid=matches[0][0] if matches else str(uuid.uuid5(uuid.NAMESPACE_URL,f"https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid={c['cid']}"))
        if not matches: db.execute('INSERT INTO cards VALUES (?,?,?,?)',(cid,None,c['cid'],'neuron'))
        identifier(db,cid,'neuron_cid',c['cid'],sid,str(c['cid']))
        db.execute('INSERT OR IGNORE INTO names VALUES (?,?,?,?,?,?)',(cid,item['language'],c['name'],c.get('description'),sid,str(c['cid'])))
def export():
    out=DATA/'exports'; out.mkdir(exist_ok=True); db=connect()
    for table in ('names','identifiers','artworks','products','printings','sources','issues','card_facts'):
        cur=db.execute('SELECT * FROM '+table)
        with (out/(table+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f); w.writerow([x[0] for x in cur.description]); w.writerows(cur)
    query="SELECT c.id,c.card_type,c.neuron_cid,(SELECT group_concat(value,'|') FROM (SELECT DISTINCT value FROM identifiers WHERE card_id=c.id AND kind='passcode')) AS passcodes,"+','.join(f"(SELECT name FROM names WHERE card_id=c.id AND language='{l}' ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 WHEN source LIKE 'ygojson%' THEN 1 ELSE 2 END LIMIT 1) AS name_{l}" for l in LANGS)+' FROM cards c ORDER BY c.id'
    cur=db.execute(query)
    with (out/'cards.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow([x[0] for x in cur.description]); w.writerows(cur)
    summary={'generated_at':now(),'counts':{t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('cards','names','identifiers','artworks','products','printings','sources','issues')},
        'names_by_language':{l:db.execute('SELECT count(DISTINCT card_id) FROM names WHERE language=?',(l,)).fetchone()[0] for l in LANGS},
        'printings_by_language':{l:db.execute('SELECT count(*) FROM printings WHERE language=?',(l,)).fetchone()[0] for l in LANGS},
        'printings_by_source':dict(db.execute("SELECT CASE WHEN source LIKE 'neuron:%' THEN 'neuron' ELSE source END,count(*) FROM printings GROUP BY 1")),
        'cards_without_passcode':db.execute("SELECT count(*) FROM cards c WHERE NOT EXISTS(SELECT 1 FROM identifiers WHERE card_id=c.id AND kind='passcode')").fetchone()[0],
        'distinct_passcodes':db.execute("SELECT count(DISTINCT value) FROM identifiers WHERE kind='passcode'").fetchone()[0],
        'coverage_warning':'Printing observations, not unique physical printings. Neuron coverage: neuron/progress.json. Missing translations do not prove a printing exists.'}
    summary_tmp=DATA/'summary.json.tmp'
    summary_tmp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    summary_tmp.replace(DATA/'summary.json')
    with (out/'gaps.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['card_id','neuron_cid','missing_name_en','missing_name_es','missing_name_de','missing_name_fr','missing_name_pt','missing_passcode'])
        for row in db.execute('SELECT id,neuron_cid FROM cards'):
            missing=[not db.execute('SELECT 1 FROM names WHERE card_id=? AND language=?',(row[0],l)).fetchone() for l in LANGS]
            pw=not db.execute("SELECT 1 FROM identifiers WHERE card_id=? AND kind='passcode'",(row[0],)).fetchone()
            if any(missing) or pw: w.writerow([*row,*map(int,missing),int(pw)])
    db.close(); print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
def lookup(term):
    db=connect()
    rows=db.execute('''SELECT c.* FROM cards c WHERE c.id=? OR EXISTS(SELECT 1 FROM names n WHERE n.card_id=c.id AND n.name LIKE ?) OR EXISTS(SELECT 1 FROM identifiers i WHERE i.card_id=c.id AND i.value=?) OR EXISTS(SELECT 1 FROM printings p WHERE p.card_id=c.id AND p.set_code=?) LIMIT 20''',(term,'%'+term+'%',term,term)).fetchall()
    result=[]
    for row in rows:
        c=dict(row)
        c['names']=[dict(r) for r in db.execute('SELECT language,name,source FROM names WHERE card_id=? AND language IN (?,?,?,?,?)',(c['id'],*LANGS))]
        c['passcodes']=[r[0] for r in db.execute("SELECT DISTINCT value FROM identifiers WHERE card_id=? AND kind='passcode'",(c['id'],))]
        c['printing_counts']=dict(db.execute("SELECT coalesce(language,'unknown'),count(*) FROM printings WHERE card_id=? GROUP BY language",(c['id'],)))
        result.append(c)
    db.close(); return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['build','export','lookup']); p.add_argument('query',nargs='?'); a=p.parse_args()
    if a.action=='build': build()
    elif a.action=='export': export()
    else: print(json.dumps(lookup(a.query or '89631139'),ensure_ascii=False,indent=2))
