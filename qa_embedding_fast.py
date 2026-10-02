"""Verify retrieval-only postprocessing on real model inputs, without timing claims."""
import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from vision_onnx import Encoder, ROOT


from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    encoder=Encoder()
    vectors=np.load(ROOT/'data/pilot/embeddings.npy')
    inputs=sorted((ROOT/'research/glare-benchmark/inputs').glob('*.png'))
    assert len(inputs)==8
    checked=[]
    for path in inputs:
        image=cv2.imread(str(path))
        assert image is not None
        predictions,original=encoder.predict(image)
        assert len(predictions)==5
        # This guards the optimization itself, not just its numeric equivalence.
        with patch('vision_onnx.np.exp',side_effect=AssertionError('Unused classifier softmax executed')):
            unused,optimized=encoder.predict(image,classify=False)
        assert unused==[]
        np.testing.assert_array_equal(original,optimized)
        np.testing.assert_array_equal(vectors@original,vectors@optimized)
        checked.append(path.name)
        print(path.name,'identical features and retrieval scores',flush=True)
    result={'status':'passed','samples':checked,'checks':[
        'classifier still returns five predictions','retrieval skips classifier softmax',
        'bit-identical normalized features','bit-identical pilot cosine scores'],
        'timing':'Not benchmarked; ONNX forward remains unchanged'}
    (QA_OUT/'embedding-fast.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
