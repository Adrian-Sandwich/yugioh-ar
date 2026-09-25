"""Read-only coverage snapshot; does not alter or restart the active crawler."""
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/registry-coverage'
LANGS = ('en', 'es', 'de', 'fr', 'pt')


def main():
    db = sqlite3.connect((ROOT / 'data/registry/registry.sqlite').as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    cards = db.execute('SELECT id,card_type,neuron_cid FROM cards').fetchall()
    names = db.execute('SELECT DISTINCT card_id,language,name FROM names').fetchall()
    codes = db.execute("SELECT DISTINCT card_id,value FROM identifiers WHERE kind='passcode'").fetchall()
    prints = db.execute('SELECT card_id,language,count(*),count(DISTINCT nullif(set_code,\'\')) FROM printings GROUP BY card_id,language').fetchall()
    arts = dict(db.execute('SELECT card_id,count(*) FROM artworks GROUP BY card_id'))
    issues = dict(db.execute('SELECT kind,count(*) FROM issues GROUP BY kind'))
    db.rollback()
    db.close()

    title = defaultdict(lambda: defaultdict(set))
    for cid, lang, name in names:
        title[cid][lang].add(name)
    serials = defaultdict(set)
    owners = defaultdict(set)
    for cid, value in codes:
        serials[cid].add(value)
        owners[value].add(cid)
    printing = {(cid, lang): (count, sets) for cid, lang, count, sets in prints}
    pilot = json.loads((ROOT / 'data/pilot/catalog.json').read_text(encoding='utf-8'))
    pilot_ids = {r['card_id'] for r in pilot}
    rows = []
    for cid, kind, neuron in cards:
        row = {'card_id': cid, 'pilot': int(cid in pilot_ids), 'card_type': kind,
               'neuron_cid': neuron, 'passcodes': '|'.join(sorted(serials[cid])),
               'artwork_records': arts.get(cid, 0)}
        for lang in LANGS:
            row['names_' + lang] = ' | '.join(sorted(title[cid][lang]))
            row['printing_observations_' + lang], row['distinct_set_codes_' + lang] = printing.get((cid, lang), (0, 0))
        row['missing_name_languages'] = '|'.join(l for l in LANGS if not title[cid][l])
        row['missing_printing_languages'] = '|'.join(l for l in LANGS if not printing.get((cid, l), (0, 0))[0])
        row['review_reasons'] = '|'.join(x for x, needed in (
            ('missing_passcode', not serials[cid]), ('missing_name', bool(row['missing_name_languages'])),
            ('missing_printing', bool(row['missing_printing_languages'])), ('missing_art', not arts.get(cid, 0)),
            ('shared_passcode', any(len(owners[v]) > 1 for v in serials[cid]))) if needed)
        rows.append(row)
    rows.sort(key=lambda r: (-r['pilot'], r['names_es'] or r['names_en'], r['card_id']))
    OUT.mkdir(exist_ok=True)
    for filename, selected in [('cards.csv', rows), ('pilot.csv', [r for r in rows if r['pilot']]),
                               ('review.csv', [r for r in rows if r['review_reasons']])]:
        with (OUT / filename).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(selected)
    coverage = {l: {'cards_with_name': sum(bool(r['names_' + l]) for r in rows),
                    'cards_with_printings': sum(r['printing_observations_' + l] > 0 for r in rows),
                    'cards_with_name_without_printings': sum(bool(r['names_' + l]) and not r['printing_observations_' + l] for r in rows)} for l in LANGS}
    summary = {'generated_at': datetime.now(timezone.utc).isoformat(), 'cards': len(rows),
               'pilot_cards': sum(r['pilot'] for r in rows), 'coverage': coverage,
               'cards_without_passcode': sum(not r['passcodes'] for r in rows),
               'shared_passcodes': {v: sorted(ids) for v, ids in owners.items() if len(ids) > 1},
               'invalid_passcodes': sorted(v for v in owners if len(v) != 8 or not v.isascii() or not v.isdecimal()),
               'issues_by_kind': issues,
               'review_counts': dict(Counter(x for r in rows for x in r['review_reasons'].split('|') if x))}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Cobertura del registro durante la descarga', '', 'Instantánea UTC: ' + summary['generated_at'], '',
             f"{len(rows)} registros de carta; {summary['pilot_cards']} identidades del piloto.", '',
             '| Idioma | Con nombre | Con observaciones de impresión | Nombre sin impresiones |',
             '|---|---:|---:|---:|']
    for lang, c in coverage.items():
        lines.append(f"| {lang} | {c['cards_with_name']} | {c['cards_with_printings']} | {c['cards_with_name_without_printings']} |")
    lines += ['', f"Sin passcode: {summary['cards_without_passcode']}. Passcodes compartidos entre registros: {len(summary['shared_passcodes'])}. Passcodes con formato inválido: {len(summary['invalid_passcodes'])}.", '',
              '## Cómo usar los archivos', '',
              '- `pilot.csv`: las identidades del piloto y sus nombres, seriales, artes y cobertura de sets por idioma.',
              '- `cards.csv`: todas las identidades; `review.csv`: registros con algún dato pendiente de revisión.',
              '- `summary.json`: conteos, seriales compartidos e incidencias del importador.', '',
              'Importar seriales como texto para conservar ceros iniciales. Los nombres alternativos se mantienen juntos, sin elegir una variante canónica.', '',
              'La ausencia de traducción o impresión no demuestra que exista una edición en ese idioma. Un passcode ausente puede ser legítimo; los compartidos requieren revisión y no se fusionan automáticamente. Los conteos de impresiones son observaciones de fuentes, no unidades físicas únicas. Los registros de arte no prueban rareza ni cobertura visual completa.', '',
              'El crawler sigue incorporando fichas. Este informe lee una transacción coherente y cierra la conexión antes de escribir CSV; no modifica la base. Repetir al terminar la descarga:', '',
              '```powershell', '.\\.venv-eval\\Scripts\\python.exe research/audit_registry_coverage.py', '```', '',
              'Prioridad: revisar primero `pilot.csv`, después seriales compartidos e incidencias, y finalmente los huecos por idioma cuando termine Neuron. No completar traducciones, artes ni rarezas por inferencia.']
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
