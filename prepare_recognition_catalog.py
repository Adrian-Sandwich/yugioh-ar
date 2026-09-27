"""Portable, versioned inputs for the next embedding build; preserves every ref."""
import hashlib,json,sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parent


def classify(ref, identity, inspection=None):
    inspection=inspection or {}
    domain={'ygoprodeck':'artwork_provider','tdoane':'game_asset','cardsoricabr':'third_party_collection'}.get(ref['source'],'unknown')
    kind=identity.get('card_type')
    formats=identity.get('declared_formats',[])
    family=('skill' if kind=='skill' else 'token' if kind=='token' else
            'standard_card' if kind in ('monster','spell','trap') and set(formats)&{'tcg','ocg'} else 'unknown')
    reasons=[]
    if ref['source']!='ygoprodeck' or ref['kind']!='art':reasons.append('not_artwork_provider_crop')
    if ref['status']!='linked':reasons.append('identity_link_unreviewed')
    if not identity:reasons.append('identity_unresolved')
    if family!='standard_card':reasons.append('outside_standard_card_scope')
    if identity.get('declared_illegal'):reasons.append('source_declares_illegal')
    if inspection.get('image_format') in ('rush_duel','custom_game_layout','nonstandard_layout'):
        reasons.append('nonstandard_image_layout')
    return {'origin_domain':domain,'identity_family':family,
            'image_format':inspection.get('image_format','unreviewed'),
            'inspection':inspection or None,'hold_reasons':reasons}


def main():
    pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    out=ROOT/'data/recognition-catalog'/stamp;out.mkdir(parents=True)
    with closing(sqlite3.connect((ROOT/pointer['database']).as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        mapping=dict(db.execute('SELECT source_card_id,canonical_card_id FROM identity_map'))
        facts={uid:json.loads(raw) for uid,raw in db.execute('SELECT card_id,facts_json FROM card_facts')}
        identities={r['id']:{'card_id':r['id'],'card_type':r['card_type'],'names':{},'passcodes':[],
                            'source_ids':[],'declared_formats':sorted(facts.get(r['id'],{}).get('legality',{})),
                            'declared_illegal':bool(facts.get(r['id'],{}).get('illegal'))}
                    for r in db.execute('SELECT id,card_type FROM resolved_cards')}
        for original,canonical in mapping.items():identities[canonical]['source_ids'].append(original)
        for uid,lang,name in db.execute('SELECT DISTINCT canonical_card_id,language,name FROM resolved_names ORDER BY canonical_card_id,language,name'):
            identities[uid]['names'].setdefault(lang,[]).append(name)
        for uid,code in db.execute("SELECT DISTINCT canonical_card_id,value FROM resolved_identifiers WHERE kind='passcode' ORDER BY canonical_card_id,value"):
            identities[uid]['passcodes'].append(code)
        refs=[dict(r) for r in db.execute('SELECT * FROM visual_references ORDER BY ref_id')]
        artwork_owners={aid:uid for aid,uid in db.execute('SELECT id,canonical_card_id FROM resolved_artworks')}
    # Only these source images were visually inspected for layout. All others
    # remain unreviewed; identity family never silently becomes an image label.
    sample=ROOT/'research/database-audit/visual-sample-20260926-071914-072968/results.json'
    annotations={}
    if sample.exists():
        labels={6:'rush_duel',18:'nonstandard_layout',23:'custom_game_layout'}
        for row in json.loads(sample.read_text(encoding='utf-8'))['items']:
            if row['sample_index'] in labels:
                annotations[row['ref_id']]={'image_format':labels[row['sample_index']],
                    'reviewer':'assistant_visual_inspection','sha256':row['sha256'],
                    'evidence':'research/database-audit/visual-sample-20260926-071914-072968/INSPECCION.md',
                    'evidence_sha256':hashlib.sha256(sample.with_name('INSPECCION.md').read_bytes()).hexdigest()}
    rows=[];inputs=[]
    for number,ref in enumerate(refs,1):
        uid=mapping.get(ref['card_id']);identity=identities.get(uid,{})
        annotation=annotations.get(ref['ref_id'])
        if annotation and annotation['sha256']!=ref['sha256']:raise ValueError('Inspection hash no longer matches catalog')
        row={'ref_id':ref['ref_id'],'source':ref['source'],'kind':ref['kind'],
             'source_card_id':ref['card_id'],'card_id':uid,'artwork_id':ref['artwork_id'],
             'path':ref['path'],'sha256':ref['sha256'],'width':ref['width'],'height':ref['height'],
             'link_status':ref['status'],'original_candidates_json':ref['candidates_json'],
             'printed_language':None,'rarity':None,'edition':None,
             'split_group':uid,'usage':'held_for_review',
             **classify(ref,identity,annotation)}
        if not row['hold_reasons']:
            path=(ROOT/ref['path']).resolve()
            if not path.is_relative_to((ROOT/'downloads').resolve()):raise ValueError('Asset path outside downloads')
            if not path.is_file():row['hold_reasons'].append('file_missing')
            elif ref['artwork_id'] not in artwork_owners:row['hold_reasons'].append('unknown_artwork_id')
            elif artwork_owners[ref['artwork_id']]!=uid:row['hold_reasons'].append('artwork_identity_mismatch')
            else:
                try:
                    actual=hashlib.sha256(path.read_bytes()).hexdigest()
                    if not ref['sha256'] or actual!=ref['sha256']:raise ValueError('hash mismatch')
                    with Image.open(path) as im:
                        if im.size!=(ref['width'],ref['height']):raise ValueError('dimension mismatch')
                        im.verify()
                    row['usage']='embedding_input';row['asset_validation']='sha256_and_image_verified'
                    inputs.append(row)
                except (OSError,ValueError) as exc:
                    row['hold_reasons'].append('asset_validation_failed');row['validation_error']=str(exc)
        rows.append(row)
        if number%10000==0:print(f'Prepared {number}/{len(refs)} refs',flush=True)
    assert len(rows)==len(refs)==len({r['ref_id'] for r in rows})
    assert all(r['card_id'] in identities and r['split_group']==r['card_id'] for r in inputs)
    for name,values in [('assets.jsonl',rows),('embedding-inputs.jsonl',inputs),('identities.jsonl',list(identities.values()))]:
        with (out/name).open('w',encoding='utf-8') as stream:
            for value in values:stream.write(json.dumps(value,ensure_ascii=False)+'\n')
    per_card=Counter(r['card_id'] for r in inputs)
    hashes=Counter(r['sha256'] for r in inputs)
    summary={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'version':stamp,
             'registry_version':pointer['version'],'identities':len(identities),
             'references_preserved':len(rows),'embedding_inputs':len(inputs),'embedding_identities':len(per_card),
             'identities_with_multiple_inputs':sum(n>1 for n in per_card.values()),
             'extra_inputs_with_repeated_hash_preserved':sum(n-1 for n in hashes.values()),
             'held_references':len(rows)-len(inputs),
             'origin_domains':dict(Counter(r['origin_domain'] for r in rows)),
             'identity_families':dict(Counter(r['identity_family'] for r in rows)),
             'image_formats':dict(Counter(r['image_format'] for r in rows)),
             'hold_reasons':dict(Counter(reason for r in rows for reason in r['hold_reasons'])),
             'policy':'Preserve every ref and image. Inputs use source-linked artwork crops, not independent physical ground truth. No vectors, training split or viewer changes.',
             'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    summary['artifacts']={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('assets.jsonl','embedding-inputs.jsonl','identities.jsonl')}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    latest=out.parent/'latest.json';tmp=latest.with_suffix('.tmp')
    tmp.write_text(json.dumps({'directory':out.relative_to(ROOT).as_posix(),'summary':summary},ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(latest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
