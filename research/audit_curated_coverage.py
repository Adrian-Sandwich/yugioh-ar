"""Audit canonical identities after import repairs; absence is not a release claim."""
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGS = ('en', 'es', 'de', 'fr', 'pt')


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def main():
    pointer = json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    out = ROOT/'research/database-audit'/('coverage-'+pointer['version'])
    out.mkdir(exist_ok=True)
    with closing(sqlite3.connect((ROOT/pointer['database']).as_uri()+'?mode=ro', uri=True)) as db:
        cards = db.execute('SELECT id,card_type FROM resolved_cards ORDER BY id').fetchall()
        neuron = defaultdict(set)
        for uid,cid in db.execute('SELECT m.canonical_card_id,c.neuron_cid FROM cards c JOIN identity_map m ON c.id=m.source_card_id WHERE c.neuron_cid IS NOT NULL'):
            neuron[uid].add(cid)
        names = defaultdict(dict)
        for uid, lang, name in db.execute('''SELECT canonical_card_id,language,min(name)
                FROM resolved_names WHERE trim(name)!='' GROUP BY canonical_card_id,language'''):
            names[uid][lang] = name
        prints = {(uid,lang):n for uid,lang,n in db.execute('''SELECT canonical_card_id,language,count(*)
                FROM resolved_printings GROUP BY canonical_card_id,language''')}
        arts = dict(db.execute('SELECT canonical_card_id,count(*) FROM resolved_artworks GROUP BY canonical_card_id'))
        serials = defaultdict(set)
        for uid, code in db.execute("SELECT canonical_card_id,value FROM resolved_identifiers WHERE kind='passcode'"):
            serials[uid].add(code)
        visual = defaultdict(lambda: defaultdict(int))
        for uid, status, n in db.execute('''SELECT canonical_card_id,status,count(*) FROM resolved_visual_references
                WHERE kind IN ('card','art') GROUP BY canonical_card_id,status'''):
            visual[uid][status] = n
        gaps = []
        for row in db.execute('''SELECT source,language,count(*),
                sum(set_code IS NULL OR trim(set_code)=''),
                sum(rarity IS NULL OR trim(rarity)=''),
                sum(edition IS NULL OR trim(edition)=''),
                sum(image_url IS NULL OR trim(image_url)=''),
                sum(product_id IS NULL OR trim(product_id)='')
                FROM printings GROUP BY source,language ORDER BY source,language'''):
            gaps.append(dict(zip(('source','language','observations','missing_set_code','missing_rarity',
                                  'missing_edition','missing_image_url','missing_product_id'), row)))
    rows=[]; actionable=[]
    for uid, kind in cards:
        row={'canonical_card_id':uid,'card_type':kind,'name_en':names[uid].get('en',''),
             'passcodes':'|'.join(sorted(serials[uid])),'artwork_records':arts.get(uid,0),
             'linked_card_or_art_refs':visual[uid].get('linked',0),
             'proposed_card_or_art_refs':visual[uid].get('proposed',0)}
        for lang in LANGS:
            row['has_name_'+lang]=int(bool(names[uid].get(lang)))
            row['printing_observations_'+lang]=prints.get((uid,lang),0)
            if not row['has_name_'+lang] and row['printing_observations_'+lang]:
                actionable.append({'canonical_card_id':uid,'name_en':row['name_en'],'card_type':kind,'language':lang,
                                   'neuron_cids':'|'.join(str(c) for c in sorted(neuron[uid])),
                                   'printing_observations':row['printing_observations_'+lang],
                                   'reason':'Printing language declared but localized name absent; check source.'})
        rows.append(row)
    coverage={lang:{'with_name':sum(r['has_name_'+lang] for r in rows),
                    'without_name':sum(not r['has_name_'+lang] for r in rows),
                    'with_printings':sum(r['printing_observations_'+lang]>0 for r in rows),
                    'printing_but_no_name':sum(not r['has_name_'+lang] and r['printing_observations_'+lang]>0 for r in rows)}
              for lang in LANGS}
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'version':pointer['version'],
             'canonical_cards':len(cards),'coverage':coverage,
             'without_passcode':sum(not r['passcodes'] for r in rows),
             'without_artwork_records':sum(not r['artwork_records'] for r in rows),
             'without_linked_card_or_art_refs':sum(not r['linked_card_or_art_refs'] for r in rows),
             'missing_names_with_printings_by_type':dict(Counter(r['card_type'] for r in actionable)),
             'printing_metadata_gaps':gaps,
             'limitations':'Missing data does not prove an edition/language exists. Linked is source status, not visual ground truth. Printing counts are source observations.'}
    write_csv(out/'cards.csv',rows,list(rows[0]))
    write_csv(out/'names-missing-with-printings.csv',actionable,
              ['canonical_card_id','name_en','card_type','language','neuron_cids','printing_observations','reason'])
    evidence=[]
    with closing(sqlite3.connect((ROOT/pointer['database']).as_uri()+'?mode=ro',uri=True)) as db:
        for row in actionable:
            observations=[dict(zip(('printing_id','source','set_code','record_key','image_url'),r)) for r in db.execute('''
                SELECT id,source,set_code,record_key,image_url FROM resolved_printings
                WHERE canonical_card_id=? AND language=? ORDER BY id''',(row['canonical_card_id'],row['language']))]
            caches=[{'cid':cid,'path':f'data/registry/neuron/card-{row["language"]}-{cid}.json',
                     'exists':(ROOT/f'data/registry/neuron/card-{row["language"]}-{cid}.json').exists()}
                    for cid in sorted(neuron[row['canonical_card_id']])]
            evidence.append({**row,'observations':observations,'cached_details':caches})
    (out/'names-gap-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(out/'printing-metadata-gaps.csv',gaps,list(gaps[0]))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Cobertura después de la descarga','',f"Versión: `{pointer['version']}`; {len(cards):,} identidades canónicas.",'',
           '| Idioma | Con nombre | Sin nombre | Con impresiones | Impresiones sin nombre |',
           '|---|---:|---:|---:|---:|']
    for lang,c in coverage.items():
        lines.append(f"| {lang} | {c['with_name']} | {c['without_name']} | {c['with_printings']} | {c['printing_but_no_name']} |")
    lines+=['','Primera prioridad: `names-missing-with-printings.csv` reúne casos donde una fuente declara una impresión en el idioma pero falta el nombre.',
            'Revisar esa evidencia antes de buscar traducciones o completar campos.',
            'El detalle por impresión, CID y presencia de caché está en `names-gap-evidence.json`. Los conteos siguientes son pares carta–idioma:',
            json.dumps(summary['missing_names_with_printings_by_type'],ensure_ascii=False),
            '',f"Sin passcode: {summary['without_passcode']}; sin registros de arte: {summary['without_artwork_records']}; sin referencias de carta/arte con estado linked: {summary['without_linked_card_or_art_refs']}.",
            '', 'Los huecos por rareza, edición, producto y URL están agrupados por fuente e idioma en `printing-metadata-gaps.csv`.',
            'No se infieren idiomas de nombres ni rarezas de ilustraciones. Las impresiones son observaciones, no unidades físicas distintas.',
            'Un nombre ausente no demuestra que exista una edición en ese idioma. Un passcode ausente puede ser legítimo.',
            'No se modifica ninguna base ni archivo de imagen.']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='printing_metadata_gaps'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
