"""Additive catalog sync preserves two equal images and separate references."""
import hashlib,json,shutil,sqlite3,uuid
from pathlib import Path
from PIL import Image
from sync_catalog import enrich,ROOT

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    folder=QA_OUT/('catalog-sync-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    assets=folder/'assets';assets.mkdir()
    for filename in ('one.png','two.png'):Image.new('RGB',(32,48),'blue').save(assets/filename)
    digest=hashlib.sha256((assets/'one.png').read_bytes()).hexdigest()
    registry=folder/'registry.sqlite'
    with sqlite3.connect(registry) as db:
        db.executescript("CREATE TABLE cards(id,card_type); INSERT INTO cards VALUES ('card','monster'); CREATE TABLE names(card_id,language,name,description,source); INSERT INTO names VALUES ('card','en','Test Card',NULL,'neuron:test'); CREATE TABLE artworks(id,card_id); INSERT INTO artworks VALUES ('art1','card'),('art2','card');")
    db.close()
    with sqlite3.connect(folder/'catalog.sqlite') as db:
        db.executescript('CREATE TABLE cards(id PRIMARY KEY,name_en,name_es,search,category,texts_json); CREATE TABLE refs(ref_id PRIMARY KEY,source,source_id,kind,path,name,sha256,width,height,card_id,artwork_id,status,reason,candidates_json);')
        items={art:{'card_id':'card','image_source_id':str(n),'path':name,'status':'ok','sha256':digest,'url':'https://example.test/'+name} for n,(art,name) in enumerate((('art1','one.png'),('art2','two.png')))}
        manifest=assets/'manifest.json';manifest.write_text(json.dumps({'items':items}))
        stats=enrich(db,registry,assets,manifest)
        assert stats['added_cards']==1 and stats['added_refs']==2
        assert db.execute('SELECT count(*),count(DISTINCT sha256),count(DISTINCT path) FROM refs').fetchone()==(2,1,2)
        assert enrich(db,registry,assets,manifest)['added_refs']==0
        assert all((assets/n).is_file() for n in ('one.png','two.png'))
        assert all(hashlib.sha256((assets/n).read_bytes()).hexdigest()==digest for n in ('one.png','two.png'))
        items['art1']['sha256']='wrong';manifest.write_text(json.dumps({'items':items}))
        try:enrich(db,registry,assets,manifest)
        except ValueError as exc:assert 'hash mismatch' in str(exc)
        else:raise AssertionError('Modified image accepted')
    db.close();shutil.rmtree(folder)
    print('PASS: two duplicate images retained as two references; idempotence, identity links and hash validation')

if __name__=='__main__':main()
