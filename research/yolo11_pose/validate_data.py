"""Validate synthetic labels against their generating geometry and identity splits."""
import hashlib,json
from pathlib import Path
import numpy as np
from prepare import DEFAULT


def main():
    m=json.loads((DEFAULT/'manifest.json').read_text());identities={'train':set(),'val':set()};hashes=set();counts={0:0,1:0,2:0}
    for r in m['records']:
        image=DEFAULT/r['image'];sha=hashlib.sha256(image.read_bytes()).hexdigest()
        assert sha==r['sha256'] and sha not in hashes;hashes.add(sha)
        labels=(DEFAULT/'labels'/r['split']/(image.stem+'.txt')).read_text().splitlines()
        assert len(labels)==len(r['objects'])
        for line,obj in zip(labels,r['objects']):
            values=np.array(list(map(float,line.split())));assert len(values)==17 and values[0]==0 and np.isfinite(values).all()
            k=values[5:].reshape(4,3);assert ((k[:,:2]>=0)&(k[:,:2]<=1)).all()
            assert np.allclose(k,np.array(obj['keypoints']))
            for flag in k[:,2]:counts[int(flag)]+=1
            p=np.float32(obj['corners'])/640
            assert np.allclose(k[k[:,2]>0,:2],p[k[:,2]>0],atol=1e-6)
            identities[r['split']].add(obj['card_id'])
    assert not identities['train']&identities['val'],'Alternate artwork identity leakage'
    result={'status':'passed','images':len(m['records']),'keypoint_visibility_counts':counts,'identity_disjoint':True}
    (DEFAULT/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
