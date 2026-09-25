"""Resumable public Neuron crawl: multilingual index, then card printing histories."""
import argparse, concurrent.futures, hashlib, json, re, threading, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from registry import DATA, LANGS, now
BASE='https://www.db.yugioh-card.com'
CACHE=DATA/'neuron'
LOCK=threading.Lock()
NEXT=0.0
LANG_LABEL={'en':'English','es':'Español','de':'Deutsch','fr':'Français','pt':'Portugues'}

def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def fetch(url,path):
    global NEXT
    if path.exists(): return path.read_bytes(),path.stat().st_mtime
    for attempt in range(3):
        with LOCK:
            delay=max(0,NEXT-time.monotonic())
            NEXT=max(time.monotonic(),NEXT)+0.55
        time.sleep(delay)
        try:
            req=Request(url,headers={'User-Agent':'YugiohLocalResearch/1.0 (cached personal card registry)'})
            with urlopen(req,timeout=35) as response: body=response.read()
            if len(body)<1000: raise ValueError('Empty response')
            tmp=path.with_suffix('.tmp'); tmp.write_bytes(body); tmp.replace(path)
            return body,path.stat().st_mtime
        except HTTPError as e:
            if e.code not in (429,500,502,503,504) or attempt==2: raise
            time.sleep(min(60,max(5*2**attempt,int(e.headers.get('Retry-After','0')) if e.headers.get('Retry-After','').isdigit() else 0)))
        except (TimeoutError,OSError):
            if attempt==2: raise
            time.sleep(3*(attempt+1))

def soup(body,lang):
    s=BeautifulSoup(body,'html.parser')
    active=s.select_one('#language a.current')
    if not active or f"('{lang}')" not in active.get('href',''):
        raise ValueError('Language mismatch or blocked page; not imported')
    return s

def parse_index(body,lang,page):
    s=soup(body,lang)
    cur=s.select_one('.page_num .nowpage')
    if cur and int(cur.get_text(strip=True))!=page: raise ValueError('Pagination mismatch')
    pages=[int(x) for x in re.findall(r'ChangePage\((\d+)\)',str(s.select_one('.page_num')))]
    rows=[]
    for r in s.select('#card_list .t_row'):
        cid=r.select_one('input.cid'); name=r.select_one('.card_name'); desc=r.select_one('.box_card_text')
        if cid and name:
            rows.append({'cid':int(cid['value']),'name':name.get_text(' ',strip=True),
                'description':desc.get_text(' ',strip=True) if desc else None})
    if not rows: raise ValueError('No cards found')
    return {'cards':rows,'pages':max([page,*pages]),'page':page}

def parse_card(body,lang,cid):
    s=soup(body,lang); name=s.select_one('#cardname h1')
    if not name: raise ValueError('Card detail missing/unavailable in this language')
    # Localized h1 includes an English subtitle; it is not part of the printed name.
    for subtitle in name.select('span'): subtitle.decompose()
    rows=[]
    for r in s.select('#update_list .t_row'):
        code=r.select_one('.card_number'); pack=r.select_one('.pack_name'); rarity=r.select_one('.lr_icon span'); link=r.select_one('input.link_value'); date=r.select_one('.time'); icon=r.select_one('.lr_icon')
        if not code: continue
        rows.append({'set_code':code.get_text(strip=True) or None,'product_name':pack.get_text(' ',strip=True) if pack else None,
            'rarity':rarity.get_text(' ',strip=True) if rarity else None,
            'rarity_id':next((v for v in (icon.get('class',[]) if icon else []) if v.startswith('rid_')),None),
            'release_date':date.get_text(strip=True) if date else None,
            'product_url':urljoin(BASE,link['value']) if link else None})
    return {'cid':cid,'name':name.get_text(' ',strip=True),'printings':rows}

def task(kind,lang,number):
    path=CACHE/f'{kind}-{lang}-{number}.json'
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    suffix=f'ope=1&sess=1&rp=100&page={number}' if kind=='index' else f'ope=2&cid={number}'
    url=f'{BASE}/yugiohdb/card_search.action?{suffix}&request_locale={lang}'
    html=CACHE/f'{kind}-{lang}-{number}.html'
    body,stamp=fetch(url,html)
    result=parse_index(body,lang,number) if kind=='index' else parse_card(body,lang,number)
    from datetime import datetime,timezone
    result.update(language=lang,url=url,fetched_at=datetime.fromtimestamp(stamp,timezone.utc).isoformat(),html_sha256=hashlib.sha256(body).hexdigest(),parser_version=1)
    save(path,result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--indices',action='store_true',help='All current index pages in five languages')
    p.add_argument('--details',action='store_true',help='All discovered card/language printing histories')
    p.add_argument('--cids',nargs='*',type=int,default=[])
    p.add_argument('--limit',type=int,default=0,help='Optional detail request cap, 0=all')
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--update-registry',action='store_true',help='Import histories as they arrive; export CSV checkpoints')
    a=p.parse_args(); CACHE.mkdir(parents=True,exist_ok=True)
    progress={'started_at':now(),'completed':0,'errors':[],'expected_index_pages':{},'status':'running','scope':{'indices':a.indices,'details':a.details,'limit':a.limit}}
    live=None
    if a.update_registry:
        from registry import connect,import_neuron,export
        live=connect()
        live.execute('PRAGMA journal_mode=WAL')
        for path in CACHE.glob('card-*.json'):
            if not live.execute('SELECT 1 FROM sources WHERE id=?',('neuron:'+path.stem,)).fetchone(): import_neuron(live,path)
        live.commit()
    def batch(tasks):
        progress['scheduled']=len(tasks); save(CACHE/'progress.json',progress)
        # Bounded batches make graceful stop possible without queued requests continuing.
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4,max(1,a.workers))) as pool:
            for offset in range(0,len(tasks),40):
                if (CACHE/'STOP').exists():
                    progress['stopped']=True; break
                futures={pool.submit(task,*t):t for t in tasks[offset:offset+40]}
                for f in concurrent.futures.as_completed(futures):
                    t=futures[f]
                    try:
                        f.result()
                        if live and t[0]=='card': import_neuron(live,CACHE/f'{t[0]}-{t[1]}-{t[2]}.json')
                        progress['completed']+=1
                    except Exception as e:
                        progress['errors'].append({'task':t,'error':str(e)})
                        if isinstance(e,HTTPError) and e.code in (401,403,429):
                            progress['access_blocked']=True
                    if (progress['completed']+len(progress['errors']))%20==0:
                        if live: live.commit()
                        progress['updated_at']=now(); save(CACHE/'progress.json',progress)
                        print(json.dumps({k:progress[k] for k in ('completed','scheduled')}),flush=True)
                if live:
                    live.commit()
                    if progress['completed'] and progress['completed']%1000==0: export()
                if progress.get('access_blocked'): break
    if a.indices:
        tasks=[]
        for lang in LANGS:
            first=task('index',lang,1)
            progress['expected_index_pages'][lang]=first['pages']
            tasks.extend(('index',lang,n) for n in range(2,first['pages']+1))
        batch(tasks)
    details=set((l,c) for l in LANGS for c in a.cids)
    if a.details:
        for path in CACHE.glob('index-??-[0-9]*.json'):
            data=json.loads(path.read_text(encoding='utf-8'))
            details.update((data['language'],c['cid']) for c in data['cards'])
    if details:
        tasks=[('card',lang,cid) for lang,cid in sorted(details,key=lambda x:(-x[1],x[0])) if not (CACHE/f'card-{lang}-{cid}.json').exists()]
        save(CACHE/'detail-queue.json',{'total_discovered':len(details),'remaining':len(tasks),'tasks':tasks})
        batch(tasks[:a.limit] if a.limit else tasks)
    progress.update(status='access_blocked' if progress.get('access_blocked') else ('stopped' if progress.get('stopped') else ('complete_with_errors' if progress['errors'] else 'complete')),finished_at=now())
    progress['cached_index_pages']=len(list(CACHE.glob('index-??-[0-9]*.json')))
    progress['cached_detail_pages']=len(list(CACHE.glob('card-*.json')))
    save(CACHE/'progress.json',progress)
    if live: live.commit(); live.close(); export()
    print(json.dumps(progress,ensure_ascii=False),flush=True)
if __name__=='__main__': main()
