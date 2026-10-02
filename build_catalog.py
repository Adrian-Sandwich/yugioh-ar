"""Build a reproducible catalog without turning proposed matches into ground truth."""
import collections
import json
import re
import sqlite3
import zipfile
from catalog import ROOT, DATA, DB, LANGS, normalized, init_reviews, export_pilot


def main():
    if DB.exists():
        # Preserve accumulated references and every duplicate image association.
        from sync_catalog import main as sync_existing
        return sync_existing()
    init_reviews()
    from ygo_source import records
    cards = list(records('cards'))
    ids, names, arts = collections.defaultdict(set), collections.defaultdict(set), {}
    by_uuid = {c['id']:c for c in cards}
    temp = DATA/'catalog.build.sqlite'
    if temp.exists():
        temp.unlink()
    db = sqlite3.connect(temp)
    db.executescript('''
        CREATE TABLE cards(id TEXT PRIMARY KEY,name_en TEXT,name_es TEXT,search TEXT,category TEXT,texts_json TEXT);
        CREATE TABLE refs(ref_id TEXT PRIMARY KEY,source TEXT,source_id TEXT,kind TEXT,path TEXT,name TEXT,
            sha256 TEXT,width INTEGER,height INTEGER,card_id TEXT,artwork_id TEXT,status TEXT,reason TEXT,candidates_json TEXT);
        CREATE TABLE localizations(card_id TEXT,source_id TEXT,language TEXT,name TEXT,description TEXT,source TEXT);
        CREATE INDEX refs_card ON refs(card_id); CREATE INDEX refs_hash ON refs(sha256);
        CREATE INDEX refs_status ON refs(status); CREATE INDEX loc_card ON localizations(card_id);
    ''')
    for card in cards:
        uid, texts = card['id'], card.get('text', {})
        name_en = texts.get('en',{}).get('name','')
        category = card.get('cardType','unknown') + ':' + ','.join(card.get('classifications',[]))
        db.execute('INSERT INTO cards VALUES (?,?,?,?,?,?)', (uid,name_en,texts.get('es',{}).get('name',''),
                   normalized(' '.join(t.get('name','') for t in texts.values())),category,json.dumps(texts,ensure_ascii=False)))
        values = list(card.get('passwords',[])) + [card.get('externalIDs',{}).get('ygoprodeck',{}).get('id')]
        for image in card.get('images',[]):
            value = image.get('password')
            values.append(value)
            if value is not None and str(value).isdigit():
                arts[(uid,str(int(value)))] = image['id']
        for value in values:
            if value is not None and str(value).isdigit():
                ids[str(int(value))].add(uid)
        for t in texts.values():
            if t.get('name'):
                names[normalized(t['name'])].add(uid)
    local = sqlite3.connect((ROOT/'downloads/tdoane-reference/YGOPRO/cdb/cards.cdb').as_uri()+'?mode=ro',uri=True)
    sim = {str(row[0]): {'alias':str(row[1]),'name':row[2]} for row in local.execute('SELECT d.id,d.alias,t.name FROM datas d JOIN texts t USING(id)')}
    local.close()
    def resolve(source_id):
        row = sim.get(source_id)
        direct = ids.get(source_id,set())
        if len(direct)==1 and row and next(iter(direct)) in names.get(normalized(row['name']),set()):
            uid = next(iter(direct))
            return uid,arts.get((uid,source_id)),'linked','ID y nombre concordantes',list(direct)
        seen, cursor = set(),source_id
        while cursor in sim and sim[cursor]['alias']!='0' and cursor not in seen:
            seen.add(cursor)
            cursor = sim[cursor]['alias']
        candidates = ids.get(cursor,set()) | direct
        if not candidates and row:
            candidates = names.get(normalized(row['name']),set())
        candidate = next(iter(candidates)) if len(candidates)==1 else None
        return candidate,None,'proposed' if candidates else 'unresolved','Alias/nombre requiere revisión',sorted(candidates)
    manifest = json.loads((ROOT/'reference/tdoane/manifest.json').read_text(encoding='utf-8'))
    resolutions = {}
    for item in manifest:
        path = item['path']
        if '/picture/' not in path or not path.lower().endswith(('.jpg','.png')):
            continue
        from pathlib import Path
        p = Path(path)
        kind = {'card':'card','closeup':'sprite','field':'field'}.get(p.parent.name,'other')
        sid = p.stem
        uid, art, status, reason, candidates = resolve(sid) if sid.isdigit() else (None,None,'unresolved','Sin ID numérico',[])
        resolutions[sid] = (uid,status)
        db.execute('INSERT INTO refs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (f'tdoane:{kind}:{p.name}','tdoane',sid,kind,'downloads/tdoane-reference/'+path,
                    sim.get(sid,{}).get('name',p.name),item['sha256'],item['width'],item['height'],uid,art,status,reason,json.dumps(candidates)))
    localized = json.loads((ROOT/'reference/tdoane/catalog-localized.json').read_text(encoding='utf-8'))
    langs = {'English':'en','Spanish':'es','German':'de','French':'fr'}
    for row in localized:
        uid,status = resolutions.get(str(row['source_id']),(None,None))
        if uid and status=='linked':
            for language,text in row['localizations'].items():
                db.execute('INSERT INTO localizations VALUES (?,?,?,?,?,?)',(uid,str(row['source_id']),langs[language],text['name'],text['description'],'tdoane'))
    drive = json.loads((ROOT/'downloads/cardsoricabr/manifest.json').read_text(encoding='utf-8'))
    audit = json.loads((ROOT/'downloads/cardsoricabr/audit.json').read_text(encoding='utf-8'))
    dimensions = {i['id']:i for i in audit['images']}
    for sid,item in drive['files'].items():
        title = re.sub(r'\s*\(\d+\)$','',item['name'].rsplit('.',1)[0])
        candidates = names.get(normalized(title),set())
        # Rush Duel has a separate scope; filenames alone must not link it to TCG identities.
        if '/Rush Duel' in item['source_path']:
            candidates = set()
        uid = next(iter(candidates)) if len(candidates)==1 else None
        dim = dimensions[sid]
        db.execute('INSERT INTO refs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('cardsoricabr:'+sid,'cardsoricabr',sid,'card','downloads/cardsoricabr/'+item['path'],
                    item['name'],item['sha256'],dim['width'],dim['height'],uid,None,
                    'proposed' if candidates else 'unresolved','Nombre de archivo; revisar imagen',json.dumps(sorted(candidates))))
    db.commit()
    counts = dict(db.execute('SELECT status,count(*) FROM refs GROUP BY status'))
    coverage = {lang:sum(bool(c.get('text',{}).get(lang,{}).get('name')) for c in cards) for lang in LANGS}
    summary = {'cards':len(cards),'references':sum(counts.values()),'statuses':counts,'names_by_language':coverage,
               'duplicate_hash_groups':db.execute('SELECT count(*) FROM (SELECT sha256 FROM refs GROUP BY sha256 HAVING count(*)>1)').fetchone()[0],
               'note':'Linked means agreeing source identifiers and names, not a visual review. Proposed images are excluded from the pilot.'}
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    db.close()
    temp.replace(DB)
    (DATA/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if not (ROOT/'data/pilot/selection.json').exists():
        summary['pilot'] = export_pilot()
    print(json.dumps(summary,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
