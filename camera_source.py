"""MJPEG stream from IP Webcam (`/video`) as the frame source, with polling fallback.

One reader thread keeps the newest complete JPEG and the time it was received.
Consumers call `latest()`; a stale stream (no frame for `stale_s`) raises so the
caller can fall back to single-shot polling. An optional `on_frame` callback
runs in the reader thread for every new frame (the corner tracker). Frames are
never queued: a slow consumer only ever sees the newest one.
"""
import threading,time,urllib.request
from urllib.request import ProxyHandler,Request,build_opener

SOI=b'\xff\xd8';EOI=b'\xff\xd9'


class MjpegSource:
    def __init__(self,base,path='/video',on_frame=None,stale_s=2.,max_frame=16*1024*1024,opener=None):
        self.url=base.rstrip('/')+path;self.on_frame=on_frame;self.stale_s=stale_s;self.max_frame=max_frame
        self.opener=opener or build_opener(ProxyHandler({}))
        self.lock=threading.Lock();self.record=None;self.frames=0;self.error=None;self.connected=False
        self.stop=threading.Event();self.thread=threading.Thread(target=self.run,name='mjpeg',daemon=True);self.thread.start()

    def latest(self):
        with self.lock:
            record=self.record
        if record is None or time.time()-record[1]>self.stale_s:
            raise OSError(self.error or 'MJPEG stream without recent frames')
        return record

    def status(self):
        with self.lock:
            age=None if self.record is None else round(time.time()-self.record[1],3)
            return {'url':self.url,'connected':self.connected,'frames':self.frames,'last_frame_age_s':age,'error':self.error}

    def close(self):
        self.stop.set()

    def run(self):
        backoff=.5
        while not self.stop.is_set():
            try:
                with self.opener.open(Request(self.url,headers={'Cache-Control':'no-cache'}),timeout=8) as response:
                    with self.lock:self.connected=True;self.error=None
                    backoff=.5;self.read_stream(response)
            except Exception as exc:
                with self.lock:self.connected=False;self.error=str(exc)
            if self.stop.is_set():break
            self.stop.wait(backoff);backoff=min(backoff*2,5.)

    def read_stream(self,response):
        buffer=bytearray()
        while not self.stop.is_set():
            chunk=response.read(65536)
            if not chunk:raise OSError('MJPEG stream closed')
            buffer+=chunk
            while True:
                start=buffer.find(SOI)
                if start<0:
                    del buffer[:-1];break
                end=buffer.find(EOI,start+2)
                if end<0:
                    if len(buffer)-start>self.max_frame:del buffer[:start+2]
                    else:del buffer[:start]
                    break
                frame=bytes(buffer[start:end+2]);del buffer[:end+2]
                captured=time.time()
                with self.lock:self.record=(frame,captured);self.frames+=1
                if self.on_frame:
                    try:self.on_frame(frame,captured)
                    except Exception:pass
