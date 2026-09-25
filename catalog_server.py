"""Local review gallery. Run after build_catalog.py; never exposes arbitrary paths."""
import argparse
import io
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import cv2
import numpy as np

from catalog import ROOT, DATA, DB, EFFECTIVE, connect, normalized, asset_path, init_reviews, review_reference, card_detail, export_pilot


class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,ctype='application/json; charset=utf-8'):
        if isinstance(body,(dict,list)):
            body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            route=urlsplit(self.path)
            q={k:v[0] for k,v in parse_qs(route.query).items()}
            if route.path=='/':
                return self.reply(200,(ROOT/'web/catalog.html').read_bytes(),'text/html; charset=utf-8')
            if route.path=='/capture':
                return self.reply(200,(ROOT/'web/capture.html').read_bytes(),'text/html; charset=utf-8')
            if route.path=='/api/summary':
                result=json.loads((DATA/'summary.json').read_text(encoding='utf-8'))
                result['token']=self.server.token
                result['pilot']=json.loads((ROOT/'data/pilot/selection.json').read_text(encoding='utf-8'))
                with connect() as conn:
                    result['reviews']=dict(conn.execute('SELECT action,count(*) FROM review.decisions GROUP BY action'))
                return self.reply(200,result)
            with connect() as conn:
                if route.path=='/api/cards':
                    page=max(0,int(q.get('page',0)))
                    term=normalized(q.get('q',''))
                    where='WHERE search LIKE ?'
                    args=['%'+term+'%']
                    total=conn.execute('SELECT count(*) FROM cards '+where,args).fetchone()[0]
                    rows=[dict(r) for r in conn.execute('SELECT id,name_en,name_es,category FROM cards '+where+' ORDER BY name_en LIMIT 30 OFFSET ?',args+[page*30])]
                    for row in rows:
                        refs=conn.execute('SELECT ref_id,effective_status FROM ('+EFFECTIVE+") WHERE effective_card_id=? AND kind='card' AND effective_status!='rejected' ORDER BY CASE effective_status WHEN 'approved' THEN 0 WHEN 'linked' THEN 1 ELSE 2 END LIMIT 1",(row['id'],)).fetchone()
                        row['cover']=refs['ref_id'] if refs else None
                    return self.reply(200,{'items':rows,'total':total,'page':page})
                if route.path=='/api/card':
                    return self.reply(200,card_detail(conn,q['id']))
                if route.path=='/api/pending':
                    page=max(0,int(q.get('page',0)))
                    where=" WHERE effective_status IN ('proposed','unresolved') AND kind='card'"
                    total=conn.execute('SELECT count(*) FROM ('+EFFECTIVE+')'+where).fetchone()[0]
                    rows=[dict(r) for r in conn.execute('SELECT * FROM ('+EFFECTIVE+')'+where+' ORDER BY source,name LIMIT 24 OFFSET ?',(page*24,))]
                    return self.reply(200,{'items':rows,'total':total,'page':page})
                if route.path=='/asset':
                    ref=conn.execute('SELECT * FROM refs WHERE ref_id=?',(q.get('id',''),)).fetchone()
                    if not ref:
                        return self.reply(404,{'error':'Imagen inexistente'})
                    path=asset_path(ref)
                    if q.get('thumb')=='1':
                        image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
                        h,w=image.shape[:2]
                        image=cv2.resize(image,(max(1,int(w*min(1,240/h))),min(h,240)))
                        return self.reply(200,cv2.imencode('.jpg',image)[1].tobytes(),'image/jpeg')
                    return self.reply(200,path.read_bytes(),'image/png' if path.suffix.lower()=='.png' else 'image/jpeg')
            self.reply(404,{'error':'Ruta inexistente'})
        except (ValueError,KeyError,TypeError) as exc:
            self.reply(400,{'error':str(exc)})
        except (BrokenPipeError,ConnectionResetError):
            pass

    def do_POST(self):
        # JSON + secret header protects localhost writes against cross-origin forms.
        if self.headers.get('X-Review-Token')!=self.server.token:
            return self.reply(403,{'error':'Recarga la galería para guardar cambios'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            limit=17*1024*1024 if self.path=='/api/capture' else 65536
            if not 0<length<=limit:
                raise ValueError('Solicitud demasiado grande o vacía')
            payload=json.loads(self.rfile.read(length))
            with self.server.write_lock:
                if self.path=='/api/review':
                    review_reference(payload)
                    return self.reply(200,{'saved':True})
                if self.path=='/api/pilot':
                    return self.reply(200,export_pilot(payload.get('ids')))
                if self.path=='/api/capture':
                    from capture_dataset import save_capture
                    return self.reply(200,save_capture(payload))
            self.reply(404,{'error':'Ruta inexistente'})
        except (ValueError,TypeError,KeyError) as exc:
            self.reply(400,{'error':str(exc)})

    def log_message(self,*args):
        pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8768)
    args=parser.parse_args()
    if not DB.exists():
        parser.error('Primero ejecuta build_catalog.py')
    init_reviews()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    server.token=secrets.token_urlsafe(32)
    server.write_lock=threading.Lock()
    print(f'Galería: http://127.0.0.1:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
