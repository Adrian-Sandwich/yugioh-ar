"""Validate domain boundaries, artifact integrity and preservation of every ref."""
import hashlib,json,sqlite3
from contextlib import closing
from prepare_recognition_catalog import ROOT,classify


def main():
    ref={'source':'ygoprodeck','kind':'art','status':'linked'}
    card={'card_type':'monster','declared_formats':['tcg']}
    assert not classify(ref,card)['hold_reasons']
    assert 'outside_standard_card_scope' in classify(ref,{'card_type':'token'})['hold_reasons']
    assert classify(ref,{'card_type':'skill'})['identity_family']=='skill'
    assert 'not_artwork_provider_crop' in classify({**ref,'source':'tdoane'},card)['hold_reasons']
    assert 'not_artwork_provider_crop' in classify({**ref,'kind':'sprite'},card)['hold_reasons']
    assert 'identity_link_unreviewed' in classify({**ref,'status':'proposed'},card)['hold_reasons']
    assert 'nonstandard_image_layout' in classify(ref,card,{'image_format':'rush_duel'})['hold_reasons']
    assert 'outside_standard_card_scope' in classify(ref,{'card_type':'monster'})['hold_reasons']
    assert 'source_declares_illegal' in classify(ref,{**card,'declared_illegal':True})['hold_reasons']
    pointer=json.loads((ROOT/'data/recognition-catalog/latest.json').read_text(encoding='utf-8'))
    directory=ROOT/pointer['directory'];summary=pointer['summary']
    for name,digest in summary['artifacts'].items():assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest,name
    assets=[json.loads(line) for line in (directory/'assets.jsonl').read_text(encoding='utf-8').splitlines()]
    inputs=[json.loads(line) for line in (directory/'embedding-inputs.jsonl').read_text(encoding='utf-8').splitlines()]
    with closing(sqlite3.connect((ROOT/f'data/curated/{summary["registry_version"]}/registry.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        original={rid:(path,digest) for rid,path,digest in db.execute('SELECT ref_id,path,sha256 FROM visual_references')}
        owners=dict(db.execute('SELECT id,canonical_card_id FROM resolved_artworks'))
    assert len(assets)==len(original)==summary['references_preserved']
    assert {a['ref_id']:(a['path'],a['sha256']) for a in assets}==original
    eligible={a['ref_id']:a for a in assets if a['usage']=='embedding_input'}
    assert len(inputs)==len(eligible)==summary['embedding_inputs']
    for a in inputs:
        assert a==eligible[a['ref_id']]
        assert owners[a['artwork_id']]==a['card_id']==a['split_group']
        assert a['asset_validation']=='sha256_and_image_verified'
        assert not a['hold_reasons']
    report={'references_preserved':len(assets),'embedding_inputs':len(inputs),'artifact_hashes':'ok',
            'identity_and_domain_boundaries':'ok','source_paths_and_hashes_preserved':True,
            'note':'Asset hashes were checked by the builder; this QA checks the published manifests.'}
    (directory/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
