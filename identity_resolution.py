"""One immutable identity map per process; live registry remains the data source."""
import json,os,sqlite3
from contextlib import closing
from pathlib import Path
from types import MappingProxyType

ROOT=Path(__file__).resolve().parent

class IdentityMap:
    def __init__(self,aliases=None,version='raw',error=None,disputed=()):
        aliases=dict(aliases or {})
        if any(a==b or b in aliases for a,b in aliases.items()):raise ValueError('Identity map contains a cycle or chain')
        self.aliases=MappingProxyType(aliases);self.version=version;self.error=error
        self.disputed=frozenset(disputed)

    def allows(self,uid,kind,value):return (uid,kind,value) not in self.disputed

    def canonical(self,uid):return self.aliases.get(uid,uid)

    def merge(self,matches):
        grouped={}
        for match in matches:
            source=match['card_id'];uid=self.canonical(source)
            item=grouped.setdefault(uid,{**match,'card_id':uid,'source_card_ids':[]})
            for original in match.get('source_card_ids',[source]):
                if original not in item['source_card_ids']:item['source_card_ids'].append(original)
            for field in ('names','printings'):
                if field in match:
                    item.setdefault(field,[])
                    item[field]=list(item[field])
                    for value in match[field]:
                        if value not in item[field]:item[field].append(value)
        return list(grouped.values())

    def info(self):return {'version':self.version,'aliases':len(self.aliases),'disputed_identifiers':len(self.disputed),'error':self.error,'data_source':'live_registry'}

    @classmethod
    def load(cls):
        if os.environ.get('YUGIOH_IDENTITY_MODE')=='raw':return cls()
        try:
            pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
            path=(ROOT/pointer['database']).resolve()
            if not path.is_relative_to(ROOT/'data/curated'):raise ValueError('Invalid release path')
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                aliases=dict(db.execute("SELECT source_card_id,canonical_card_id FROM identity_map WHERE decision='accepted_alias'"))
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='identifier_decisions' AND type='table'").fetchone()
                disputed=list(db.execute("SELECT card_id,kind,value FROM identifier_decisions WHERE status='disputed'")) if exists else []
                for target in set(aliases.values()):
                    if db.execute('SELECT canonical_card_id FROM identity_map WHERE source_card_id=?',(target,)).fetchone()!=(target,):raise ValueError('Invalid alias target')
            return cls(aliases,pointer['version'],disputed=disputed)
        except (OSError,ValueError,KeyError,sqlite3.Error) as exc:return cls(error=str(exc))

# Pin the map across OCR, appearance and geometry for the process lifetime.
# Publishing another snapshot requires an explicit viewer restart; never mix
# a newly loaded name map with old temporal votes or artwork caches.
IDENTITIES=IdentityMap.load()
canonical=IDENTITIES.canonical

def normalize_detection(detection):
    result=dict(detection)
    if result.get('card_id'):
        result.setdefault('source_card_id',result['card_id']);result['card_id']=canonical(result['card_id'])
    if 'top5' in result:result['top5']=[normalize_detection(x) for x in result['top5']]
    return result
