"""ONNX sessions and the two DRAW2 Small models: the OBB card detector and the ViT encoder.

Inference budget (this PC, 8 logical cores, measured 26/09/2026): one 224x224 encode costs
~624 ms with 2 threads, ~474 ms with 4, ~873 ms with 8; a batch of four costs ~395 ms per image
with 4 threads. Hence 4 threads by default (YUGIOH_ONNX_THREADS) and batched runs.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

import settings
from util import quad_iou

ROOT = settings.ROOT
MODELS = ROOT / 'downloads/reference-assets/draw2/onnx'


# Execution device: 'cpu' (default) or 'cuda' (needs onnxruntime-gpu, see
# requirements-gpu.txt). The int8 encoder only runs well on CPU; on CUDA the
# default is the float model from research/dequantize_encoder.py, which has its
# own index (embeddings-<variant>.npy) and must be calibrated separately.
DEVICE=settings.ONNX_DEVICE
ENCODER_VARIANT=settings.ENCODER_VARIANT


def providers():
    if DEVICE=='cpu': return ['CPUExecutionProvider']
    if DEVICE!='cuda': raise ValueError(f'YUGIOH_ONNX_DEVICE={DEVICE!r}: use cpu or cuda')
    if hasattr(ort,'preload_dlls'): ort.preload_dlls()  # CUDA/cuDNN from the nvidia-* wheels
    # Heuristic cuDNN search: batch size changes with the number of cards and an
    # exhaustive search per new shape stalls the first frames that see it.
    return [('CUDAExecutionProvider',{'cudnn_conv_algo_search':'HEURISTIC'}),'CPUExecutionProvider']


def session(path,threads=None):
    options=ort.SessionOptions()
    options.intra_op_num_threads=int(threads or settings.ONNX_THREADS)
    options.inter_op_num_threads=1
    result=ort.InferenceSession(str(path),sess_options=options,providers=providers())
    if DEVICE=='cuda' and 'CUDAExecutionProvider' not in result.get_providers():
        print(f'WARNING: CUDA unavailable for {Path(path).name}; running on CPU',flush=True)
    return result


IMAGENET_MEAN=np.float32([.485,.456,.406]);IMAGENET_STD=np.float32([.229,.224,.225])


def tensor(image,size=224,normalization='draw2'):
    rgb=cv2.cvtColor(cv2.resize(image,(size,size)),cv2.COLOR_BGR2RGB).astype(np.float32)
    x=(rgb/255-IMAGENET_MEAN)/IMAGENET_STD if normalization=='imagenet' else rgb/127.5-1
    return np.ascontiguousarray(x.transpose(2,0,1)[None])


def with_features():
    import onnx
    from onnx import helper,TensorProto
    source=MODELS/'vit_yugiscan_int8.onnx'
    target=ROOT/'data/models/vit_small_features.onnx'
    target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    manifest=target.with_suffix('.json')
    if target.exists() and manifest.exists() and json.loads(manifest.read_text())['source_sha256']==digest:
        return target
    model=onnx.load(source)
    # Audited graph: Gather of the final normalized CLS token, before classifier quantization.
    feature='/Gather_output_0'
    assert any(n.op_type=='Gather' and feature in n.output for n in model.graph.node)
    dimension=next(i.dims[0] for i in model.graph.initializer if i.name=='vit.layernorm.weight')
    model.graph.output.append(helper.make_tensor_value_info(feature,TensorProto.FLOAT,['batch',dimension]))
    onnx.checker.check_model(model)
    onnx.save(model,target)
    manifest.write_text(json.dumps({'source_sha256':digest,'feature':feature,'dimension':dimension,
        'preprocessing':'BGR->RGB; resize224 square; x/127.5-1; NCHW; L2 features','trained_for_retrieval':False},indent=2))
    return target


def encoder_path(variant):
    """int8/fp32/fp16: DRAW2 Small; any other name is a retrieval-only model in data/models (e.g. dinov2_vits14)."""
    if variant=='int8': return with_features()
    draw2=variant in ('fp32','fp16')
    path=ROOT/(f'data/models/vit_small_features_{variant}.onnx' if draw2 else f'data/models/{variant}.onnx')
    if not path.exists():
        raise FileNotFoundError(f'{path} missing: run research/{"dequantize_encoder.py" if draw2 else "export_dinov2.py"}')
    return path


class Encoder:
    def __init__(self,variant=None):
        self.variant=variant or ENCODER_VARIANT
        self.model_path=encoder_path(self.variant)
        self.model=session(self.model_path)
        manifest=self.model_path.with_suffix('.json')
        self.normalization=json.loads(manifest.read_text()).get('preprocessing') if manifest.exists() else None
        self.normalization='imagenet' if self.normalization=='imagenet' else 'draw2'
        # Retrieval-only encoders have a single output and no classifier vocabulary.
        self.retrieval_only=len(self.model.get_outputs())==1
        self.labels=json.loads((MODELS/'card_labels_yugiscan.json').read_text(encoding='utf-8'))
        self.mapping=json.loads((ROOT/'research/references-20260924/draw2-small-ygojson-map.json').read_text(encoding='utf-8'))

    def predict(self,image,*,classify=True):
        return self.predict_batch([image],classify=classify)[0]

    def predict_batch(self,images,*,classify=True):
        """One ONNX run for several crops; each result equals `predict` on that crop."""
        if not images: return []
        blob=np.concatenate([tensor(image,normalization=self.normalization) for image in images],axis=0)
        outputs=self.model.run(None,{self.model.get_inputs()[0].name:blob})
        logits,features=(None,outputs[0]) if self.retrieval_only else outputs
        results=[]
        for row in range(len(images)):
            z=features[row].astype(np.float32);z/=max(np.linalg.norm(z),1e-12)
            # Retrieval uses only z. Do not softmax/sort/map the entire classifier
            # vocabulary when the caller will immediately discard that ranking.
            if not classify or logits is None:
                results.append(([],z));continue
            scores=np.exp(logits[row]-np.max(logits[row]));scores/=scores.sum()
            top=np.argsort(scores)[-5:][::-1]
            predictions=[{'index':int(i),'label':self.labels[str(i)],'card_id':self.mapping.get(str(i),{}).get('ygojson_uuid'),
                          'score':float(scores[i])} for i in top]
            results.append((predictions,z))
        return results


class Detector:
    def __init__(self):
        self.model=session(MODELS/'ygo_yolo.onnx')

    def detect(self,image,threshold=.2):
        h,w=image.shape[:2];scale=min(640/w,640/h)
        rw,rh=round(w*scale),round(h*scale);px,py=(640-rw)//2,(640-rh)//2
        padded=np.zeros((640,640,3),np.uint8)
        padded[py:py+rh,px:px+rw]=cv2.resize(image,(rw,rh))
        blob=np.ascontiguousarray(cv2.cvtColor(padded,cv2.COLOR_BGR2RGB).transpose(2,0,1)[None].astype(np.float32)/255)
        rows=self.model.run(None,{self.model.get_inputs()[0].name:blob})[0][0]
        if rows.shape[0]<rows.shape[1]: rows=rows.T
        if rows.shape[1]!=6: raise ValueError('Unexpected detector output shape')
        boxes=[]
        for x,y,bw,bh,score,angle in rows[rows[:,4]>=threshold]:
            x,y=(x-px)/scale,(y-py)/scale;bw,bh=bw/scale,bh/scale
            if bw>bh: bw,bh,angle=bh,bw,angle+np.pi/2
            rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            corners=(np.array([[-bw/2,-bh/2],[bw/2,-bh/2],[bw/2,bh/2],[-bw/2,bh/2]])@rotation.T+[x,y]).astype(np.float32)
            if bw<20 or bh<20 or not np.isfinite(corners).all(): continue
            boxes.append({'corners':corners,'score':float(score)})
        kept=[]
        for candidate in sorted(boxes,key=lambda b:-b['score']):
            if any(quad_iou(candidate['corners'],k['corners'])>.5 for k in kept): continue
            kept.append(candidate)
            if len(kept)>=20: break
        return kept


def crop(image,corners):
    dst=np.float32([[0,0],[223,0],[223,223],[0,223]])
    matrix=cv2.getPerspectiveTransform(np.float32(corners),dst)
    return cv2.warpPerspective(image,matrix,(224,224))


