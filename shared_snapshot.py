"""One phone request at a time, short reuse window, original capture timestamp."""
import threading,time


class SharedSnapshots:
    def __init__(self,ttl=.15,error_backoff=.5):
        self.lock=threading.Lock();self.ttl=ttl;self.error_backoff=error_backoff
        self.key=None;self.record=None;self.finished=0.;self.error=None

    def get(self,key,fetch):
        if not self.lock.acquire(timeout=9):raise TimeoutError('Camera request still pending')
        try:
            age=time.monotonic()-self.finished
            if key==self.key:
                if self.error and age<self.error_backoff:raise OSError(self.error)
                if self.record is not None and age<self.ttl:return self.record
            self.key=key;self.record=None;self.error=None
            captured=time.time()
            try:data=fetch()
            except Exception as exc:
                self.error=str(exc);self.finished=time.monotonic();raise
            self.record=(data,captured);self.finished=time.monotonic()
            return self.record
        finally:self.lock.release()
