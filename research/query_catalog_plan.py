import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalog import connect,EFFECTIVE
with connect() as c:
    print([tuple(r) for r in c.execute('EXPLAIN QUERY PLAN SELECT c.id,r.ref_id FROM cards c JOIN ('+EFFECTIVE+") r ON c.id=r.effective_card_id WHERE r.kind='card' AND r.effective_status IN ('linked','approved') AND r.width>=200 AND r.height>=290")])
