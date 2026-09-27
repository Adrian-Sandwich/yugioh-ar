"""Prevent false artwork assignments and preserve separate image references."""
import sqlite3
from printing_art_links import build_links,visual_triage


def main():
    with sqlite3.connect(':memory:') as db:
        db.executescript('''
            CREATE TABLE printings(id TEXT PRIMARY KEY,card_id TEXT,image_url TEXT,source TEXT);
            CREATE TABLE artworks(id TEXT PRIMARY KEY,card_id TEXT,card_url TEXT,source TEXT);
            CREATE TABLE identity_map(source_card_id TEXT PRIMARY KEY,canonical_card_id TEXT);
            CREATE VIEW resolved_printings AS SELECT m.canonical_card_id,p.* FROM printings p JOIN identity_map m ON p.card_id=m.source_card_id;
            CREATE VIEW resolved_artworks AS SELECT m.canonical_card_id,a.* FROM artworks a JOIN identity_map m ON a.card_id=m.source_card_id;
            CREATE TABLE visual_references(ref_id TEXT,source TEXT,path TEXT,card_id TEXT,status TEXT,reason TEXT,candidates_json TEXT);
        ''')
        db.executemany('INSERT INTO identity_map VALUES (?,?)',[('a','a'),('alias','a'),('b','b')])
        db.executemany('INSERT INTO printings VALUES (?,?,?,?)',[
            ('exact','alias','https://image/1','source'),('ambiguous','a','https://image/2','source'),
            ('wrong-card','b','https://image/1','source'),('null','a',None,'source'),
            ('empty','a','','source'),('other-art','a','https://image/3','source'),
            ('whitespace','a',' ','source'),('different-url','a','https://image/1?size=1','source')])
        db.executemany('INSERT INTO artworks VALUES (?,?,?,?)',[
            ('art1','a','https://image/1','source'),('art2','a','https://image/2','source'),
            ('art3','a','https://image/2','source'),('empty','a','','source'),('space','a',' ','source')])
        before=list(db.execute('SELECT * FROM printings'))
        summary=build_links(db)
        assert summary['links_by_status']=={'ambiguous_url':2,'source_declared':1},summary
        assert summary['printing_observations_without_link']==6
        assert db.execute('SELECT printing_id,artwork_id FROM source_declared_printing_art').fetchall()==[('exact','art1')]
        assert list(db.execute('SELECT * FROM printings'))==before
        proposals=[('copy1','a','["alias"]'),('copy2','a','["alias"]'),
                   ('ambiguous',None,'["a","b"]'),('bad',None,'broken'),
                   ('unknown',None,'["missing"]'),('none',None,'[]')]
        db.executemany('INSERT INTO visual_references VALUES (?,\'test\',\'same-image.jpg\',?,\'proposed\',\'test\',?)',proposals)
        rows={r['ref_id']:r for r in visual_triage(db)}
        assert len(rows)==6
        assert rows['copy1']['canonical_candidates']==['a']==rows['copy2']['canonical_candidates']
        assert rows['copy1']['triage']=='unique_candidate_needs_verification'
        assert rows['ambiguous']['triage']=='multiple_candidates'
        assert rows['bad']['triage']=='invalid_candidates'
        assert rows['unknown']['triage']=='unknown_identity'
        assert rows['none']['triage']=='no_candidate'
    print('PASS: aliases, ambiguity, wrong identity, absent/blank/different URLs, raw preservation, duplicate refs and malformed candidates')


if __name__=='__main__':main()
