"""Check the published evidence layer against untouched raw rows and catalog refs."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    path=ROOT/pointer['database']
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('ATTACH DATABASE ? AS raw',((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',))
        db.execute('ATTACH DATABASE ? AS catalog',((ROOT/'data/catalog/catalog.sqlite').as_uri()+'?mode=ro',))
        for table in ('cards','names','identifiers','artworks','products','printings','sources','issues','issue_resolutions'):
            assert not db.execute(f'SELECT * FROM raw.{table} EXCEPT SELECT * FROM main.{table} LIMIT 1').fetchone(),table
            assert db.execute(f'SELECT count(*) FROM raw.{table}').fetchone()==db.execute(f'SELECT count(*) FROM main.{table}').fetchone(),table
        assert not db.execute('SELECT * FROM catalog.refs EXCEPT SELECT * FROM visual_references LIMIT 1').fetchone()
        assert db.execute('SELECT count(*) FROM catalog.refs').fetchone()==db.execute('SELECT count(*) FROM visual_references').fetchone()
        assert not db.execute('PRAGMA main.foreign_key_check').fetchone()
        assert db.execute('PRAGMA main.quick_check').fetchone()[0]=='ok'
        assert not db.execute('''SELECT 1 FROM printing_art_links l
            JOIN resolved_printings p ON p.id=l.printing_id
            JOIN resolved_artworks a ON a.id=l.artwork_id
            WHERE p.canonical_card_id!=a.canonical_card_id OR p.image_url!=a.card_url
               OR l.image_url!=p.image_url OR trim(l.image_url)='' LIMIT 1''').fetchone()
        report={'version':pointer['version'],'raw_rows_preserved':True,'visual_rows_preserved':True,
                'quick_check':'ok','foreign_key_check':'ok','printing_art':pointer['summary']['printing_art'],
                'visual_review':pointer['summary']['visual_review']}
    (path.parent/'evidence-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
