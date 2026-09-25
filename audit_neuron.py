"""Measure complete index coverage and verify cached snapshots."""
import hashlib,json
from registry import DATA,LANGS,now
from scrape_neuron import save
def main():
    cache=DATA/'neuron'; report={'audited_at':now(),'languages':{}}
    for lang in LANGS:
        pages=[json.loads(p.read_text(encoding='utf-8')) for p in cache.glob(f'index-{lang}-*.json')]
        first=next(p for p in pages if p['page']==1)
        expected=first['pages']; actual={p['page'] for p in pages}
        missing=sorted(set(range(1,expected+1))-actual)
        rows=[c for p in pages for c in p['cards']]
        cids={c['cid'] for c in rows}
        mismatches=[]
        for p in pages:
            path=cache/f"index-{lang}-{p['page']}.html"
            if hashlib.sha256(path.read_bytes()).hexdigest()!=p['html_sha256']: mismatches.append(p['page'])
        report['languages'][lang]={'expected_pages':expected,'cached_pages':len(pages),'missing_pages':missing,'html_hash_mismatches':mismatches,'rows':len(rows),'unique_cids':len(cids),'duplicate_cid_rows':len(rows)-len(cids),'complete_index':not missing and not mismatches and len(rows)==len(cids)}
    report['complete_five_language_index']=all(x['complete_index'] for x in report['languages'].values())
    report['expected_card_language_histories']=sum(x['unique_cids'] for x in report['languages'].values())
    report['cached_histories']=len(list(cache.glob('card-*.json')))
    report['scope']='Complete relative to public Neuron search index snapshot; not a claim of all worldwide physical releases or all printing histories.'
    save(cache/'index-coverage.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
