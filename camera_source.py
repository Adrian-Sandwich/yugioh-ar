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


def frame_end(buffer,start):
    """Index just past the EOI of the JPEG starting at `start`, or -1 if incomplete.

    Walks the marker segments so an EXIF thumbnail (a whole JPEG inside APP1,
    with its own EOI) does not cut the frame short; only after SOS is the next
    FFD9 the real end, because entropy-coded data stuffs every FF with 00.
    """
    i=start+2;n=len(buffer)
    while True:
        if i+4>n:return -1
        if buffer[i]!=0xFF:return -1  # not a marker: corrupt stream, resync
        marker=buffer[i+1]
        if marker==0xD8 or 0xD0<=marker<=0xD7 or marker==0x01 or marker==0xFF:
            i+=1 if marker==0xFF else 2;continue
        if marker==0xD9:return i+2
        if marker==0xDA:
            end=buffer.find(EOI,i+2)
            return -1 if end<0 else end+2
        length=(buffer[i+2]<<8)|buffer[i+3]
        i+=2+length


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
            # read1: whatever has arrived. read(n) blocks until n bytes, so the tail
            # of each frame waited for the next frame's bytes (up to one frame late).
            chunk=response.read1(65536)
            if not chunk:raise OSError('MJPEG stream closed')
            buffer+=chunk
            while True:
                start=buffer.find(SOI)
                if start<0:
                    del buffer[:-1];break
                end=frame_end(buffer,start)
                if end<0:
                    if len(buffer)-start>self.max_frame or (len(buffer)>start+4 and buffer[start+2]!=0xFF):del buffer[:start+2]
                    else:del buffer[:start]
                    break
                frame=bytes(buffer[start:end]);del buffer[:end]
                captured=time.time()
                with self.lock:self.record=(frame,captured);self.frames+=1
                if self.on_frame:
                    try:self.on_frame(frame,captured)
                    except Exception:pass
