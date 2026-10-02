"""Recognizer in a child process: a hung or crashed ONNX forward cannot freeze the viewer.

The parent talks to the child over a pipe with the same `analyze_jpeg` contract
as vision_onnx.LiveRecognizer. A call that exceeds `timeout` kills the child,
starts a fresh one and raises TimeoutError; the camera loop keeps serving
frames meanwhile. Reference metadata is fetched once at start so the viewer
can report counts and names without a round trip.
"""
import multiprocessing as mp
import os
import threading
import time
import traceback
from contracts import ANALYZE_CONTEXT


def _serve(conn,mode):
    try:
        from vision_onnx import LiveRecognizer
        recognizer=LiveRecognizer(mode)
        conn.send(('ready',{'references':recognizer.references,'cards':recognizer.cards,'pid':os.getpid()}))
    except Exception:
        conn.send(('failed',traceback.format_exc()));return
    while True:
        try:message=conn.recv()
        except (EOFError,OSError):return
        if message is None:return
        _,payload=message
        try:
            # Test hook only: a deliberate stall to exercise the watchdog.
            if payload.get('_test_delay') and os.environ.get('YUGIOH_INFERENCE_TEST')=='1':time.sleep(payload['_test_delay'])
            context={k:payload[k] for k in ANALYZE_CONTEXT if k in payload}
            conn.send(('ok',recognizer.analyze_jpeg(payload['data'],**context)))
        except Exception:
            conn.send(('error',traceback.format_exc()))


class RemoteRecognizer:
    def __init__(self,mode='embedding',timeout=25.,start_timeout=180.):
        self.mode=mode;self.timeout=timeout;self.start_timeout=start_timeout
        self.lock=threading.Lock();self.restarts=0;self.timeouts=0;self.process=None;self.conn=None
        self.references=[];self.cards={};self.child_pid=None
        self._start()

    def _start(self):
        context=mp.get_context('spawn')
        self.conn,child=context.Pipe()
        self.process=context.Process(target=_serve,args=(child,self.mode),daemon=True,name='inference-host')
        self.process.start();child.close()
        if not self.conn.poll(self.start_timeout):
            self._kill();raise RuntimeError('El proceso de inferencia no arrancó a tiempo')
        kind,payload=self.conn.recv()
        if kind!='ready':
            self._kill();raise RuntimeError(f'El proceso de inferencia falló al cargar:\n{payload}')
        self.references=payload['references'];self.cards=payload['cards'];self.child_pid=payload['pid']

    def _kill(self):
        if self.process is not None and self.process.is_alive():
            self.process.kill();self.process.join(5)
        if self.conn is not None:
            try:self.conn.close()
            except OSError:pass

    def restart(self):
        self._kill();self.restarts+=1;self._start()

    def analyze_jpeg(self,data,_test_delay=None,**context):
        """`context`: the keyword arguments of contracts.ANALYZE_CONTEXT, passed through to the child."""
        unknown=set(context)-set(ANALYZE_CONTEXT)
        if unknown:raise TypeError(f'analyze_jpeg: argumentos desconocidos {sorted(unknown)} (ver contracts.ANALYZE_CONTEXT)')
        with self.lock:
            if self.process is None or not self.process.is_alive():self.restart()
            payload={'data':data,**{k:(list(v) if k in ('reuse','verified') else v) for k,v in context.items()}}
            if _test_delay:payload['_test_delay']=_test_delay
            try:self.conn.send(('analyze',payload))
            except (OSError,EOFError,BrokenPipeError):
                self.restart();raise OSError('El proceso de inferencia se había cerrado; reiniciado')
            if not self.conn.poll(self.timeout):
                self.timeouts+=1;self.restart()
                raise TimeoutError(f'La inferencia superó {self.timeout:.0f} s; proceso reiniciado')
            try:kind,payload=self.conn.recv()
            except (EOFError,OSError):
                self.restart();raise OSError('El proceso de inferencia murió durante el análisis; reiniciado')
            if kind=='ok':return payload
            raise RuntimeError(f'Fallo en el proceso de inferencia:\n{payload}')

    def status(self):
        return {'isolated':True,'alive':bool(self.process and self.process.is_alive()),'pid':self.child_pid,'restarts':self.restarts,'timeouts':self.timeouts,'timeout_s':self.timeout}

    def close(self):
        with self.lock:
            try:
                if self.conn is not None and self.process is not None and self.process.is_alive():self.conn.send(None)
            except (OSError,EOFError,BrokenPipeError):pass
            if self.process is not None:
                self.process.join(3)
            self._kill()
