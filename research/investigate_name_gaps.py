"""Investigate the pinned name gaps without inventing translations or editing the DB."""
import hashlib,json,re,sqlite3,subprocess,sys,time
from collections import Counter
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scrape_neuron import parse_card


def fetch(url,path):
    if not path.exists():
        pending=path.with_suffix('.part')
        result=subprocess.run(['curl.exe','-L','--fail','--silent','--show-error','--max-time','30',url,'-o',str(pending)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr.strip())
        pending.replace(path)
        time.sleep(.6)
    return path.read_bytes()


def localized_field(text,lang):
    matches=re.findall(r'^\|\s*'+re.escape(lang)+r'_name\s*=([^\n]*)',text,re.M)
    if len(matches)!=1:return {'status':'field_missing_or_ambiguous','raw_values':matches}
    value=matches[0].strip()
    if not value:return {'status':'source_field_empty','raw_values':matches}
    if any(c in value for c in '{}[]<>|'):
        return {'status':'markup_needs_review','raw_values':matches}
    return {'status':'candidate_localized_name','name':value,'raw_values':matches}


def main():
    pointer=json.loads((ROOT/'data/curated/latest.json').read_text(encoding='utf-8'))
    base=ROOT/'research/database-audit'
    gaps=json.loads((base/('coverage-'+pointer['version'])/'names-gap-evidence.json').read_text(encoding='utf-8'))
    out=base/('name-investigation-'+pointer['version']);out.mkdir(exist_ok=True)
    with closing(sqlite3.connect((ROOT/pointer['database']).as_uri()+'?mode=ro',uri=True)) as db:
        facts={uid:json.loads(raw) for uid,raw in db.execute('SELECT card_id,facts_json FROM card_facts')}
    ids=sorted({int(p['id']) for g in gaps for p in facts.get(g['canonical_card_id'],{}).get('externalIDs',{}).get('yugipedia',[])})
    pages={};sources=[]
    for start in range(0,len(ids),20):
        batch=ids[start:start+20]
        url='https://yugipedia.com/api.php?'+urlencode({'action':'query','pageids':'|'.join(map(str,batch)),
            'prop':'revisions','rvprop':'ids|timestamp|content','format':'json'})
        path=out/f'yugipedia-{start//20+1}.json'
        body=fetch(url,path);data=json.loads(body)
        if 'error' in data:raise ValueError(data['error'])
        source={'url':url,'artifact':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(body).hexdigest()}
        sources.append(source)
        for key,page in data.get('query',{}).get('pages',{}).items():pages[key]=(page,source)
        print(f'Yugipedia: {min(start+20,len(ids))}/{len(ids)} pages requested',flush=True)
    cases=[]
    for gap in gaps:
        checks=[]
        for external in facts.get(gap['canonical_card_id'],{}).get('externalIDs',{}).get('yugipedia',[]):
            page,source=pages.get(str(external['id']),({},{}))
            revisions=page.get('revisions',[])
            check={'page_id':external['id'],'title':page.get('title'),'source':source}
            if revisions:
                revision=revisions[0]
                check.update(localized_field(revision.get('*',''),gap['language']))
                check['revision_id']=revision.get('revid');check['revision_timestamp']=revision.get('timestamp')
            else:check['status']='page_or_revision_missing'
            checks.append(check)
        official=[]
        for cache in gap['cached_details']:
            cid=cache['cid'];lang=gap['language']
            if cid<=0:
                official.append({'cid':cid,'status':'nonpositive_identifier_needs_review',
                                 'reason':'Do not treat a nonpositive source dbID as a validated Neuron CID.'})
                continue
            url=f'https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid={cid}&request_locale={lang}'
            path=out/f'neuron-{lang}-{cid}.html'
            body=fetch(url,path)
            record={'url':url,'artifact':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(body).hexdigest()}
            try:
                record['parsed']=parse_card(body,lang,cid);record['status']='candidate_official_name'
            except ValueError as exc:record.update(status='detail_not_recovered',reason=str(exc))
            official.append(record)
            print(f'Neuron {lang}/{cid}: {record["status"]}',flush=True)
        names={c['name'] for c in checks if c['status']=='candidate_localized_name'}
        names.update(c['parsed']['name'] for c in official if c['status']=='candidate_official_name' and c['parsed'].get('name'))
        status='candidate_needs_review' if names else 'unresolved_source_empty_or_missing'
        if len(names)>1:status='conflicting_candidates'
        cases.append({**gap,'status':status,'wiki_checks':checks,'official_checks':official})
    summary={'version':pointer['version'],'cases':len(cases),'pages_requested':len(ids),
             'status_counts':dict(Counter(c['status'] for c in cases)),
             'wiki_field_status':dict(Counter(w['status'] for c in cases for w in c['wiki_checks'])),
             'official_check_status':dict(Counter(w['status'] for c in cases for w in c['official_checks'])),
             'names_imported':0,'scope':'Source observations; no automatic translations or DB mutations.'}
    (out/'results.json').write_text(json.dumps({'summary':summary,'sources':sources,'cases':cases},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
