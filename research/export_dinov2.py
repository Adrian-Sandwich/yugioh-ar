"""Export DINOv2 (Meta, Apache-2.0) as a retrieval-only encoder variant.

A general-purpose self-supervised encoder, never trained on cards, as a
baseline against DRAW2 Small before any contrastive fine-tuning (queue,
experiment 8). The ONNX has one output: the CLS embedding. vision_onnx reads the
manifest next to it for the input normalization, so the same pipeline, index
builder and research/calibrate_acceptance.py evaluate it unchanged:

  .venv-gpu/Scripts/python.exe research/export_dinov2.py --size s
  set YUGIOH_ONNX_DEVICE=cuda & set YUGIOH_ENCODER=dinov2_vits14
  .venv-gpu/Scripts/python.exe vision_onnx.py            # pilot index
  .venv-gpu/Scripts/python.exe research/calibrate_acceptance.py --same-scans research/qa/calibration/acceptance-records.json --output research/qa/calibration-dinov2_vits14

Weights come from torch.hub (facebookresearch/dinov2); they are not committed.
"""
import argparse
import json
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]


class Embedding(torch.nn.Module):
    def __init__(self, model):
        super().__init__(); self.model = model

    def forward(self, pixel_values):
        return self.model(pixel_values)  # CLS token after the final norm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', choices=('s', 'b'), default='s')
    args = parser.parse_args()
    name = f'dinov2_vit{args.size}14'
    model = Embedding(torch.hub.load('facebookresearch/dinov2', name)).eval()
    target = ROOT / f'data/models/{name}.onnx'
    target.parent.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        # 224 = 16 patches of 14 px, the size vision_onnx.tensor() produces.
        torch.onnx.export(model, torch.randn(1, 3, 224, 224), str(target), input_names=['pixel_values'], output_names=['embedding'],
                          dynamic_axes={'pixel_values': {0: 'batch'}, 'embedding': {0: 'batch'}}, opset_version=17, dynamo=False)
    dimension = int(model(torch.randn(1, 3, 224, 224)).shape[1])
    target.with_suffix('.json').write_text(json.dumps({
        'source': f'torch.hub facebookresearch/dinov2 {name}', 'license': 'Apache-2.0', 'dimension': dimension,
        'preprocessing': 'imagenet', 'outputs': ['embedding'], 'trained_for_retrieval': 'self-supervised, not on cards',
        'thresholds_calibrated': False}, indent=2))
    print(name, target.relative_to(ROOT).as_posix(), round(target.stat().st_size / 2**20, 1), 'MB', dimension)


if __name__ == '__main__':
    main()
