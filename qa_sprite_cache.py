"""Compare cached AR rendering against pixel baselines captured before optimization."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from ar_overlay import SpriteOverlay

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent
BASELINE=ROOT/'research/qa/sprite-cache-before.npz'


def fixture():
    rng=np.random.default_rng(274)
    frame=rng.integers(0,256,(180,260,3),dtype=np.uint8)
    sprite=rng.integers(0,256,(67,53,4),dtype=np.uint8)
    sprite[10:25,10:25]=[0,0,0,255]
    sprite[:8,:,3]=0
    quad=[[30,10],[140,28],[150,160],[15,140]]
    second=[[105,30],[230,15],[245,170],[115,165]]
    return frame,sprite,quad,second


def render_cases():
    frame,sprite,quad,second=fixture()
    renderer=SpriteOverlay()
    renderer.cache['sample']=sprite
    cases={}
    def detection(corners,stable=True):
        return {'sprite_ref':'sample','stable':stable,'corners':corners}
    for transparent in (False,True):
        for name,items in [('empty',[]),('unstable',[detection(quad,False)]),
            ('single',[detection(quad)]),('overlap',[detection(quad),detection(second)])]:
            cases[f'{name}_{transparent}']=renderer.render(frame,items,transparent)
    return cases


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--record-baseline',action='store_true')
    args=parser.parse_args()
    actual=render_cases()
    if args.record_baseline:
        if BASELINE.exists():
            raise RuntimeError('Refusing to overwrite pre-change baseline')
        np.savez_compressed(BASELINE,**actual)
        print('Saved pre-change pixel baseline',BASELINE)
        return
    with np.load(BASELINE) as before:
        assert set(before.files)==set(actual)
        for name,pixels in actual.items():
            np.testing.assert_array_equal(before[name],pixels,err_msg=name)
    frame,sprite,quad,second=fixture()
    renderer=SpriteOverlay(prepared_limit=2)
    renderer.cache['sample']=sprite
    items=[{'sprite_ref':'sample','stable':True,'corners':q} for q in (quad,second)]
    with patch('ar_overlay.np.concatenate',wraps=np.concatenate) as composed:
        renderer.render(frame,items[:1],True)
        shape=composed.call_args.args[0][0].shape
        assert shape[0]*shape[1]<frame.shape[0]*frame.shape[1],'Composition still uses the full frame'
    renderer.clear_cache();renderer.cache['sample']=sprite
    with patch('ar_overlay.cv2.resize',wraps=cv2.resize) as resized:
        renderer.render(frame,items,True)
        renderer.render(frame,items,True)
        assert resized.call_count==1,'Same sprite prepared repeatedly'
        replacement=sprite.copy();replacement[:]=[0,250,0,128]
        renderer.cache['sample']=replacement
        changed=renderer.render(frame,items,True)
        assert resized.call_count==2,'Replacing a sprite did not invalidate its canvas'
        assert not np.array_equal(changed,actual['overlap_True'])
        for ref in ('two','three'):
            renderer.cache[ref]=sprite
            renderer.render(frame,[{**items[0],'sprite_ref':ref}],True)
        assert len(renderer.prepared)==2 and 'sample' not in renderer.prepared
        renderer.render(frame,items,True)
        assert resized.call_count==5,'Evicted sprite was not prepared again'
        renderer.clear_cache('sample')
        assert 'sample' not in renderer.cache and 'sample' not in renderer.prepared
        renderer.clear_cache()
        assert not renderer.cache and not renderer.prepared
    result={'status':'passed','pixel_identical_cases':list(actual),
        'checks':['overlapping transparent sprites','opaque black pixels','no detections and unstable detections',
                  'one resize for repeated sprite','replacement invalidates canvas','bounded LRU eviction','explicit invalidation','composition limited to occupied region'],
        'timing':'Not benchmarked; warp unchanged, identical alpha arithmetic on bounded regions'}
    (QA_OUT/'sprite-cache.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
