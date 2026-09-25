"""Labels for this frozen scene only, after visual review of contact-sheet.png."""
import json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
path=OUT/'samples.json';data=json.loads(path.read_text(encoding='utf-8'))
cards={r['name']:r['card_id'] for r in json.loads((ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))}
names=['Dragón de Péndulo de Ojos Anómalos','Número 39: Utopía','Dragón Negro de Ojos Rojos',
       'Mago Oscuro','Dragón de Péndulo de Ojos Anómalos','Juicio Solemne','Dragón Blanco de Ojos Azules']
assert len(data['samples'])==8,'Review scene labels again if detections changed'
with sqlite3.connect((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',uri=True) as db:
    for row,name in zip(data['samples'],names):
        row.update(expected_name=name,expected_card_id=cards[name],
                   expected_passcodes=[v[0] for v in db.execute("SELECT DISTINCT value FROM identifiers WHERE kind='passcode' AND card_id=?",(cards[name],))],
                   label_source='User scene description plus visual crop review; registry codes are expectations, not pixel transcriptions')
path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Labeled seven physical instances, including two separate Odd-Eyes copies.')
