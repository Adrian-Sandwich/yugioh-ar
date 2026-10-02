"""Concurrent phone fetches, timestamp freshness, failure recovery and source change."""
import concurrent.futures,json,threading,time
from pathlib import Path
from shared_snapshot import SharedSnapshots


from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    cache=SharedSnapshots(ttl=.1,error_backoff=.1);calls=0;barrier=threading.Barrier(6)
    def fetch():
        nonlocal calls
        calls+=1;time.sleep(.03);return str(calls).encode()
    def client():barrier.wait();return cache.get('phone',fetch)
    with concurrent.futures.ThreadPoolExecutor(6) as pool:results=list(pool.map(lambda _:client(),range(6)))
    assert calls==1 and len(set(results))==1,'Concurrent clients did not share original data/time'
    first=results[0];time.sleep(.12);second=cache.get('phone',fetch)
    assert calls==2 and second[0]!=first[0] and second[1]>first[1]
    third=cache.get('different-phone',fetch);assert calls==3 and third!=second
    time.sleep(.12)
    def broken():raise OSError('controlled offline')
    for _ in range(2):
        try:cache.get('different-phone',broken)
        except OSError:pass
        else:raise AssertionError('Served stale success after camera failure')
    time.sleep(.12);assert cache.get('different-phone',fetch)[0]==b'4'
    result={'status':'passed','concurrent_clients':6,'phone_requests':1,
            'checks':['original timestamp shared','expiry requests fresh frame','source change invalidates','failure does not serve stale image','recovery']}
    (QA_OUT/'shared-snapshot.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
