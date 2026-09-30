"""Hunyuan3D-2mini worker for research/gen3d_bench.py (runs inside downloads/gen3d/hunyuan's venv).

    python hunyuan_mini.py --output-dir OUT [--texture] IMG...   # OUT/<i>/mesh.glb, like SF3D/TripoSR

Shape: hunyuan3d-dit-v2-mini-turbo + FlashVDM (5 steps). Texture (optional): Hunyuan3D-Paint
turbo with CPU offload, since shape + texture need ~16 GB per the upstream README and the 4070
has 12. The shape pipeline is freed before the texture one loads.
"""
import argparse, gc, os

import torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('images', nargs='+')
ap.add_argument('--output-dir', required=True)
ap.add_argument('--texture', action='store_true')
ap.add_argument('--steps', type=int, default=5)
ap.add_argument('--octree', type=int, default=256)
a = ap.parse_args()

from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

shape = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    'tencent/Hunyuan3D-2mini', subfolder='hunyuan3d-dit-v2-mini-turbo', use_safetensors=False, device='cuda')
shape.enable_flashvdm(topk_mode='merge')

images, meshes = [], []
for path in a.images:
    img = Image.open(path).convert('RGBA')  # the bench feeds cut-outs that already carry alpha
    images.append(img)
    meshes.append(shape(image=img, num_inference_steps=a.steps, octree_resolution=a.octree,
                        num_chunks=20000, generator=torch.manual_seed(12345), output_type='trimesh')[0])
del shape; gc.collect(); torch.cuda.empty_cache()

if a.texture:
    from hy3dgen.texgen import Hunyuan3DPaintPipeline
    paint = Hunyuan3DPaintPipeline.from_pretrained('tencent/Hunyuan3D-2')  # turbo subfolder by default
    paint.enable_model_cpu_offload()
    meshes = [paint(m, image=img) for m, img in zip(meshes, images)]

for i, m in enumerate(meshes):
    os.makedirs(os.path.join(a.output_dir, str(i)), exist_ok=True)
    m.export(os.path.join(a.output_dir, str(i), 'mesh.glb'))
