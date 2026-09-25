"""Meaningful checks for catalog links, review isolation, tracking and HTTP writes."""
import base64
import json
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import catalog
import capture_dataset
from ar_overlay import Tracker,SpriteOverlay
from catalog_server import Handler
from http.server import ThreadingHTTPServer


def main():
    catalog.init_reviews()
    with catalog.connect() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        blue=conn.execute("SELECT id FROM cards WHERE name_en='Blue-Eyes White Dragon'").fetchone()[0]
        rows=list(conn.execute("SELECT card_id,artwork_id,status FROM refs WHERE ref_id IN ('tdoane:card:89631139.jpg','tdoane:card:89631140.jpg')"))
        assert len(rows)==2 and all(r['card_id']==blue and r['status']=='linked' for r in rows)
        assert rows[0]['artwork_id']!=rows[1]['artwork_id']
        proposed=conn.execute("SELECT ref_id,card_id FROM refs WHERE source='cardsoricabr' AND status='proposed' AND card_id=? LIMIT 1",(blue,)).fetchone()
        assert proposed
        before=conn.execute('SELECT count(*) FROM review.decisions').fetchone()[0]
    pilot=json.loads((catalog.ROOT/'data/pilot/catalog.json').read_text(encoding='utf-8'))
    with catalog.connect() as conn:
        for entry in pilot:
            row=conn.execute('SELECT effective_status FROM ('+catalog.EFFECTIVE+') WHERE ref_id=?',(entry['id'],)).fetchone()
            assert row[0] in ('linked','approved')
    # Inside .runtime (ignored everywhere); a locked SQLite file must not abort the run
    # nor leave tmp* folders in the project root.
    (catalog.ROOT/'.runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=catalog.ROOT/'.runtime',ignore_cleanup_errors=True) as tmp:
        review_db=Path(tmp)/'reviews.sqlite'
        with patch.object(catalog,'REVIEWS',review_db),patch.object(capture_dataset,'DATASET',Path(tmp)/'captures'):
            catalog.init_reviews()
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            server.token='test-token';server.write_lock=threading.Lock()
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(route,body,token='test-token'):
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Review-Token':token})
                with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
            try:
                try:
                    post('/api/review',{'ref_id':proposed['ref_id'],'action':'approve','card_id':blue},'wrong-token')
                    raise AssertionError('CSRF guard did not reject write')
                except urllib.error.HTTPError as exc: assert exc.code==403
                post('/api/review',{'ref_id':proposed['ref_id'],'action':'approve','card_id':blue,'language':'en','artwork_id':'test-art'})
                with catalog.connect() as conn:
                    row=conn.execute('SELECT * FROM ('+catalog.EFFECTIVE+') WHERE ref_id=?',(proposed['ref_id'],)).fetchone()
                    assert row['effective_status']=='approved' and row['printed_language']=='en'
                post('/api/review',{'ref_id':proposed['ref_id'],'action':'reset'})
                with catalog.connect() as conn: assert conn.execute('SELECT count(*) FROM review.decisions').fetchone()[0]==0
                png=cv2.imencode('.png',np.zeros((200,200,3),np.uint8))[1].tobytes()
                payload={'image':base64.b64encode(png).decode(),'session':'test_session','split':'train','card_id':blue,
                         'corners':[[10,10],[180,10],[180,180],[10,180]],'language':'en'}
                assert post('/api/capture',payload)['saved']
                try:
                    post('/api/capture',{**payload,'split':'test'})
                    raise AssertionError('Session leaked across splits')
                except urllib.error.HTTPError as exc: assert exc.code==400
                for invalid in ([],[[0,0],[100,100],[0,100],[100,0]]):
                    try:
                        post('/api/capture',{**payload,'corners':invalid})
                        raise AssertionError('Invalid quadrilateral accepted')
                    except urllib.error.HTTPError as exc: assert exc.code==400
            finally:
                server.shutdown();server.server_close();thread.join()
    with catalog.connect() as conn: assert conn.execute('SELECT count(*) FROM review.decisions').fetchone()[0]==before
    tracker=Tracker()
    def detection(x):return {'id':'ref','card_id':blue,'corners':[[x,0],[x+40,0],[x+40,60],[x,60]]}
    first=tracker.update([detection(0),detection(150)],now=0)
    assert len({d['track_id'] for d in first})==2 and all(not d['stable'] for d in first)
    second=tracker.update([detection(2),detection(152)],now=.1)
    assert [d['track_id'] for d in first]==[d['track_id'] for d in second] and all(d['stable'] for d in second)
    assert tracker.update([detection(3),detection(153)],now=4.5)[0]['stable'], 'Slower SIFT cycles must retain confirmation'
    tracker.update([],now=.2)
    assert not tracker.update([detection(2)],now=.3)[0]['stable']
    frame=np.zeros((720,1280,3),np.uint8)
    detection={'sprite_ref':'tdoane:sprite:89631139.png','corners':[[100,100],[400,120],[420,600],[90,580]],'stable':True}
    assert np.count_nonzero(SpriteOverlay().render(frame,[detection]))>0
    print('PASS: IDs/arts, pilot eligibility, review API/CSRF/reset, capture geometry/session separation, duplicate tracking and sprite projection')


if __name__=='__main__': main()
