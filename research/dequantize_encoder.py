"""Float version of the DRAW2 Small encoder for GPU execution providers.

`vit_yugiscan_int8.onnx` is a dynamic-quantized graph (DynamicQuantizeLinear +
MatMulInteger/ConvInteger). CUDA and TensorRT fall back to CPU for most of it,
and no fp32 export of this compact model is published (the HuggingFace
`vit_fp32.onnx` is the main ViT with 13,820 labels, not interchangeable).

Each `XInteger -> Cast -> Mul(scale)` chain is replaced by a float MatMul/Conv
whose weights are the dequantized int8 weights, (w_q - zero_point) * scale.
Weights are therefore exactly the int8 ones; only activations stop being
quantized, so scores drift slightly and acceptance thresholds must be re-checked
with research/calibrate_acceptance.py before this model is used in the viewer.

  .venv-eval/Scripts/python.exe research/dequantize_encoder.py
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / 'data/models/vit_small_features.onnx'
TARGET = {'fp32': ROOT / 'data/models/vit_small_features_fp32.onnx',
          'fp16': ROOT / 'data/models/vit_small_features_fp16.onnx'}


def dequantize(model):
    graph = model.graph
    init = {i.name: i for i in graph.initializer}
    producer = {o: n for n in graph.node for o in n.output}
    consumers = {}
    for n in graph.node:
        for i in n.input: consumers.setdefault(i, []).append(n)
    remove, add, new_init = set(), [], []
    for node in [n for n in graph.node if n.op_type in ('MatMulInteger', 'ConvInteger')]:
        a_q, w_q, _, w_zp = node.input
        quantizer = producer[a_q]
        assert quantizer.op_type == 'DynamicQuantizeLinear', node.name
        (cast,) = consumers[node.output[0]]
        (scale_mul,) = consumers[cast.output[0]]
        assert cast.op_type == 'Cast' and scale_mul.op_type == 'Mul', node.name
        scale_name = next(i for i in scale_mul.input if i != cast.output[0])
        scales = producer[scale_name]
        w_scale = next(i for i in scales.input if i in init)
        weight = (numpy_helper.to_array(init[w_q]).astype(np.float32)
                  - numpy_helper.to_array(init[w_zp]).astype(np.float32)) * numpy_helper.to_array(init[w_scale]).astype(np.float32)
        name = w_q.removesuffix('_quantized') + '_dequantized'
        new_init.append(numpy_helper.from_array(weight.astype(np.float32), name))
        op = 'MatMul' if node.op_type == 'MatMulInteger' else 'Conv'
        attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
        add.append(helper.make_node(op, [quantizer.input[0], name], [scale_mul.output[0]], name=node.name + '_float', **attrs))
        remove.update(id(n) for n in (node, cast, scale_mul))
    kept = [n for n in graph.node if id(n) not in remove] + add
    # Drop quantizers and scale products nobody reads any more.
    outputs = {o.name for o in graph.output}
    while True:
        used = {i for n in kept for i in n.input} | outputs
        dead = [n for n in kept if not any(o in used for o in n.output)]
        if not dead: break
        kept = [n for n in kept if n not in dead]
    used = {i for n in kept for i in n.input}
    graph.ClearField('node')
    graph.node.extend(topological(kept, {i.name for i in graph.input} | set(init) | {i.name for i in new_init}))
    initializers = [i for i in list(graph.initializer) + new_init if i.name in used]
    graph.ClearField('initializer')
    graph.initializer.extend(initializers)
    return model


def topological(nodes, available):
    available = set(available) | {''}
    ordered, pending = [], list(nodes)
    while pending:
        ready = [n for n in pending if all(i in available for i in n.input)]
        assert ready, 'graph has a cycle or a missing input'
        for n in ready:
            ordered.append(n); available.update(n.output)
        pending = [n for n in pending if n not in ready]
    return ordered


def main():
    import vision_onnx
    vision_onnx.with_features()  # make sure SOURCE matches the current int8 download
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    model = dequantize(onnx.load(SOURCE))
    onnx.checker.check_model(model)
    onnx.save(model, TARGET['fp32'])
    from onnxruntime.transformers.float16 import convert_float_to_float16
    half = convert_float_to_float16(onnx.load(TARGET['fp32']), keep_io_types=True)
    onnx.save(half, TARGET['fp16'])
    for precision, path in TARGET.items():
        path.with_suffix('.json').write_text(json.dumps({
            'source': SOURCE.relative_to(ROOT).as_posix(), 'source_sha256': digest, 'precision': precision,
            'method': 'int8 weights dequantized: (w_q - zero_point) * scale; activations in float',
            'io': 'float32', 'thresholds_calibrated': False}, indent=2))
        print(precision, path.relative_to(ROOT).as_posix(), round(path.stat().st_size / 2**20, 1), 'MB')


if __name__ == '__main__':
    main()
