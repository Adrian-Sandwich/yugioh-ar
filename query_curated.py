"""Query the published snapshot through canonical identities, preserving members."""
import argparse,json,sqlite3
from contextlib import closing
from pathlib import Path
from ygo_source import ROOT

def search(term):
    pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    path=(ROOT/pointer['database']).resolve()
    if not path.is_relative_to(ROOT/'data/curated'):raise ValueError('Invalid release path')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        matches=db.execute('''WITH matched AS (
            SELECT card_id FROM names WHERE name LIKE ?
            UNION SELECT card_id FROM resolved_identifiers WHERE value=?
            UNION SELECT card_id FROM printings WHERE set_code=?
            UNION SELECT id FROM cards WHERE id=?)
            SELECT DISTINCT m.canonical_card_id FROM matched x JOIN identity_map m ON m.source_card_id=x.card_id
            ORDER BY m.canonical_card_id LIMIT 50''',('%'+term+'%',term,term,term)).fetchall()
        out=[]
        for (uid,) in matches:
            members=[r[0] for r in db.execute('SELECT source_card_id FROM identity_map WHERE canonical_card_id=? ORDER BY source_card_id',(uid,))]
            names={}
            for lang,name in db.execute('SELECT DISTINCT language,name FROM resolved_names WHERE canonical_card_id=? ORDER BY language,name',(uid,)):names.setdefault(lang,[]).append(name)
            codes=[r[0] for r in db.execute("SELECT DISTINCT value FROM resolved_identifiers WHERE canonical_card_id=? AND kind='passcode' ORDER BY value",(uid,))]
            out.append({'canonical_id':uid,'source_ids':members,'names':names,'passcodes':codes,
                'artworks':db.execute('SELECT count(*) FROM resolved_artworks WHERE canonical_card_id=?',(uid,)).fetchone()[0],
                'printing_observations':db.execute('SELECT count(*) FROM resolved_printings WHERE canonical_card_id=?',(uid,)).fetchone()[0],
                'source_declared_art_links':db.execute("SELECT count(*) FROM printing_art_links WHERE canonical_card_id=? AND status='source_declared'",(uid,)).fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='printing_art_links'").fetchone() else None,
                'visual_references':db.execute('SELECT count(*) FROM resolved_visual_references WHERE canonical_card_id=?',(uid,)).fetchone()[0]})
    return {'version':pointer['version'],'items':out,'limit':50,'scope':'Snapshot, not the live crawler database. Aliases are reversible; every source identity is preserved.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('query');a=p.parse_args()
    print(json.dumps(search(a.query),ensure_ascii=False,indent=2))
