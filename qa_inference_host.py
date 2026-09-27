"""Inference in a child process: real analysis through the pipe, hang detected and host restarted."""
import json,os,time
from pathlib import Path
from inference_host import RemoteRecognizer

ROOT=Path(__file__).resolve().parent
SCENE=ROOT/'data/captures/carta-2026-09-25T04-13-54-278Z.jpg'  # one card: keeps the round trip well under the timeout on a loaded CPU

def main():
    os.environ['YUGIOH_INFERENCE_TEST']='1'
    started=time.perf_counter();host=RemoteRecognizer('embedding',timeout=15.);startup=time.perf_counter()-started
    try:
        assert host.references and host.cards and host.status()['alive'] and host.status()['pid']!=os.getpid()
        data=SCENE.read_bytes()
        result=host.analyze_jpeg(data)
        assert result['detections'] and result['width']>0 and 'candidates' in result,'real analysis must cross the pipe intact'
        names={d['name'] for d in result['detections']}
        # Context arguments travel too: a fresh matching track is reused without encoding.
        first=result['candidates'][0]
        track=[{'corners':first['corners'],'card_id':'reused','score':.9,'margin':.4,'rotation':0,'track_id':3,'top5':[{'card_id':'reused','score':.9}]}]
        reused=host.analyze_jpeg(data,reuse=track)
        assert reused['reused_cards']==1
        pid=host.status()['pid']
        try:host.analyze_jpeg(data,_test_delay=20);raise AssertionError('a stalled forward must time out')
        except TimeoutError:pass
        assert host.status()['restarts']==1 and host.status()['timeouts']==1 and host.status()['pid']!=pid and host.status()['alive'],'host must restart after a timeout'
        again=host.analyze_jpeg(data);assert {d['name'] for d in again['detections']}==names,'restarted host must give the same identities'
        report={'status':'passed','startup_s':round(startup,1),'detections':len(result['detections']),'names':sorted(names),
                'checks':['child process serves analyses','reuse/verified context crosses the pipe','timeout kills and restarts the child','same result after restart'],
                'note':'Startup time observed once; the child loads the ONNX models and the pilot index.'}
    finally:
        host.close()
    assert not host.status()['alive']
    (ROOT/'research/qa/inference-host.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
