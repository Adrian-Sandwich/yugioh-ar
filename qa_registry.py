"""Registry invariants and actual Neuron parser fixtures; no network required."""
import json
from pathlib import Path
from registry import DATA, connect, LANGS
from scrape_neuron import parse_card,parse_index
from registry_server import search,detail

def main():
    db=connect()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    blue=db.execute('SELECT id FROM cards WHERE neuron_cid=4007').fetchone()[0]
    pw={r[0] for r in db.execute("SELECT value FROM identifiers WHERE card_id=? AND kind='passcode'",(blue,))}
    assert pw=={'89631139'},pw
    assert db.execute("SELECT 1 FROM identifiers WHERE card_id=? AND kind='image_source_id' AND value='89631140'",(blue,)).fetchone()
    assert not db.execute("SELECT value FROM identifiers WHERE kind='passcode' AND (length(value)!=8 OR value GLOB '*[^0-9]*')").fetchall()
    assert db.execute("SELECT 1 FROM identifiers WHERE kind='passcode' AND value LIKE '0%' LIMIT 1").fetchone()
    langs={r[0] for r in db.execute('SELECT DISTINCT language FROM names WHERE card_id=?',(blue,))}
    assert set(LANGS)<=langs
    for lang in LANGS:
        assert db.execute('SELECT 1 FROM printings WHERE card_id=? AND language=?',(blue,lang)).fetchone()
    en=parse_card((DATA/'neuron-blue-en.html').read_bytes(),'en',4007)
    pt=parse_card((DATA/'neuron-blue-pt.html').read_bytes(),'pt',4007)
    assert en['name']=='Blue-Eyes White Dragon'
    assert pt['name']=='Dragão Branco de Olhos Azuis',pt['name']
    rarities={r['rarity_id'] for r in en['printings'] if r['set_code']=='RA05-EN085'}
    assert len(rarities)>=2,rarities
    assert any(r['set_code'] is None and r['product_name']=='25TH ANNIVERSARY ULTIMATE KAIBA SET' for r in en['printings'])
    try: parse_card((DATA/'neuron-blue-en.html').read_bytes(),'es',4007)
    except ValueError: pass
    else: raise AssertionError('Wrong language accepted')
    index=parse_index((DATA/'neuron-search-es.html').read_bytes(),'es',1)
    assert len(index['cards'])==100 and index['pages']==138
    assert search(db,'89631139',0)['items'][0]['id']==blue
    assert any(i['id']==blue for i in search(db,'LOB-EN001',0)['items'])
    assert all(p['language']=='pt' for p in detail(db,blue,'pt',0)['printings'])
    # A product-level edition list must not manufacture per-card edition evidence.
    assert not db.execute("SELECT 1 FROM printings WHERE source LIKE 'ygojson%' AND edition IS NOT NULL AND image_url IS NULL LIMIT 1").fetchone()
    db.close()
    result={'status':'passed','checks':['SQLite integrity and foreign keys','passcode vs art IDs','leading zeros','five languages','same set code multiple rarities','localized title without English subtitle','language mismatch rejection','index pagination','passcode and set-code lookup','language filter','edition provenance']}
    (DATA/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
if __name__=='__main__': main()
