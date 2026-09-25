"""Read-only multilingual registry browser at localhost:8769."""
import argparse, json, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from registry import ROOT, DATA, DB, LANGS

def connection():
    db=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return db

def search(db,term,page,mode='all'):
    queries={
        'all':('SELECT card_id FROM names WHERE name LIKE ? UNION SELECT card_id FROM identifiers WHERE value=? UNION SELECT card_id FROM printings WHERE set_code=? UNION SELECT id FROM cards WHERE id=?',('%'+term+'%',term,term,term)),
        'name':('SELECT DISTINCT card_id FROM names WHERE name LIKE ?',('%'+term+'%',)),
        'passcode':("SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?",(term,)),
        'set':('SELECT DISTINCT card_id FROM printings WHERE set_code=?',(term,)),
        'cid':('SELECT id AS card_id FROM cards WHERE neuron_cid=?',(term,)),
    }
    if mode not in queries:raise ValueError('Tipo de búsqueda inválido')
    match,args=queries[mode]
    # A savepoint gives count/page/names a single read snapshot while Neuron
    # writes. It is also safe inside callers' existing transactions.
    db.execute('SAVEPOINT registry_search')
    try:
        rows=db.execute('''WITH matched AS MATERIALIZED ('''+match+'''),
            totals AS (SELECT count(*) AS n FROM matched),
            selected AS (SELECT card_id FROM matched ORDER BY card_id LIMIT 30 OFFSET ?)
            SELECT selected.card_id,totals.n FROM totals LEFT JOIN selected ON 1=1 ORDER BY selected.card_id''',(*args,max(0,page)*30)).fetchall()
        total=rows[0][1];ids=[r[0] for r in rows if r[0] is not None]
        items={uid:{'id':uid,'names':{},'passcodes':[]} for uid in ids}
        if ids:
            slots=','.join('?' for _ in ids)
            for r in db.execute('SELECT card_id,language,name FROM names WHERE card_id IN ('+slots+
                    ") ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 WHEN source LIKE 'ygojson%' THEN 1 ELSE 2 END,language,rowid",ids):
                if r['language'] in LANGS:items[r['card_id']]['names'].setdefault(r['language'],r['name'])
            for r in db.execute("SELECT DISTINCT card_id,value FROM identifiers WHERE kind='passcode' AND card_id IN ("+slots+') ORDER BY card_id,value',ids):
                items[r['card_id']]['passcodes'].append(r['value'])
        return {'items':list(items.values()),'total':total,'page':page}
    finally:db.execute('RELEASE registry_search')

def detail(db,uid,lang,page):
    row=db.execute('SELECT * FROM cards WHERE id=?',(uid,)).fetchone()
    if not row: raise KeyError('Carta inexistente')
    result=dict(row)
    result['names']=[dict(r) for r in db.execute('SELECT DISTINCT language,name FROM names WHERE card_id=? AND language IN (?,?,?,?,?) ORDER BY language,name',(uid,*LANGS))]
    result['identifiers']=[dict(r) for r in db.execute('SELECT DISTINCT kind,value FROM identifiers WHERE card_id=? ORDER BY kind,value',(uid,))]
    where='p.card_id=?'; args=[uid]
    if lang: where+=' AND p.language=?'; args.append(lang)
    result['total']=db.execute('SELECT count(*) FROM printings p WHERE '+where,args).fetchone()[0]
    result['printings']=[dict(r) for r in db.execute('''SELECT p.*,s.url AS source_url FROM printings p JOIN sources s ON s.id=p.source WHERE '''+where+' ORDER BY p.release_date DESC,p.set_code,p.rarity LIMIT 100 OFFSET ?',args+[page*100])]
    result['page']=page
    return result

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,value,ctype='application/json; charset=utf-8'):
        body=json.dumps(value,ensure_ascii=False).encode() if not isinstance(value,bytes) else value
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        db=None
        try:
            route=urlsplit(self.path); q={k:v[0] for k,v in parse_qs(route.query).items()}
            if route.path=='/': return self.reply(200,(ROOT/'web/registry.html').read_bytes(),'text/html; charset=utf-8')
            if route.path=='/api/summary': return self.reply(200,json.loads((DATA/'summary.json').read_text(encoding='utf-8')))
            if route.path=='/api/progress':
                path=DATA/'neuron/progress.json'
                return self.reply(200,json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})
            db=connection(); page=max(0,int(q.get('page','0')))
            if route.path=='/api/search': return self.reply(200,search(db,q.get('q','')[:250],page,q.get('mode','all')))
            if route.path=='/api/card': return self.reply(200,detail(db,q.get('id',''),q.get('lang',''),page))
            self.reply(404,{'error':'Ruta inexistente'})
        except (ValueError,KeyError) as e: self.reply(400,{'error':str(e)})
        except (BrokenPipeError,ConnectionResetError): pass
        finally:
            if db: db.close()
    def log_message(self,*args): pass
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--port',type=int,default=8769); a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler); server.daemon_threads=True
    print(f'Registro: http://127.0.0.1:{a.port}',flush=True)
    try: server.serve_forever()
    finally: server.server_close()
