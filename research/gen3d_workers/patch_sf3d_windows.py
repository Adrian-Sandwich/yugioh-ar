"""Let Stable Fast 3D's texture_baker compile on Windows with CUDA 12.8 and VS 2022 (MSVC 14.44).

Its CUDA file includes <torch/extension.h>, which pulls torch/csrc/dynamo/compiled_autograd.h, and
nvcc with this MSVC stops there with "error C2872: 'std': ambiguous symbol" (30/09/2026). The kernel
only needs tensors and the operator registry: smaller headers and ATen factories are enough.

    python research/gen3d_workers/patch_sf3d_windows.py      # idempotent
    then, in a VS x64 prompt with CUDA 12.8: pip install wheel ninja; pip install --no-build-isolation ./texture_baker/ ./uv_unwrapper/

Patches downloads/gen3d/sf3d/texture_baker/texture_baker/csrc/baker_kernel.cu (a clone, not versioned).
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[2] / 'downloads/gen3d/sf3d/texture_baker/texture_baker/csrc/baker_kernel.cu'
MARK = '// patched: no torch/extension.h'
SWAPS = [('#include <torch/extension.h>\n',
          f'{MARK} (research/gen3d_workers/patch_sf3d_windows.py)\n#include <torch/types.h>\n#include <torch/library.h>\n'),
         ('torch::empty(', 'at::empty('), ('torch::TensorOptions()', 'at::TensorOptions()')]


def main():
    text = TARGET.read_text(encoding='utf-8')
    if MARK in text:
        print('ya parchado:', TARGET); return
    if SWAPS[0][0] not in text: raise SystemExit(f'SF3D cambió; revisa a mano {TARGET}')
    for old, new in SWAPS: text = text.replace(old, new)
    TARGET.write_text(text, encoding='utf-8')
    print('parchado:', TARGET)


if __name__ == '__main__':
    main()
