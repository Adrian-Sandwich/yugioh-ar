"""Let TripoSR run without torchmcubes: PyMCubes (CPU marching cubes) when the CUDA build is missing.

torchmcubes compiles a CUDA extension. On this PC (30/09/2026) it could not be built: the full CUDA
toolkits are 11.8 and 12.1, too old for the Visual Studio 2022 C++ library (14.44 needs CUDA >= 12.4),
and the 12.8 folder holds no nvcc. PyMCubes ships wheels. Marching cubes runs once per model on a
256^3 grid, so the CPU costs a second or two, not the minutes of a failed build.

    downloads/gen3d/triposr/.venv/Scripts/python.exe -m pip install PyMCubes
    python research/gen3d_workers/patch_triposr_mcubes.py      # idempotent

Patches downloads/gen3d/triposr/tsr/models/isosurface.py (a clone, not versioned): torchmcubes is
still used when it imports.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[2] / 'downloads/gen3d/triposr/tsr/models/isosurface.py'
MARK = '# patched: PyMCubes fallback'

IMPORT_OLD = 'from torchmcubes import marching_cubes\n'
IMPORT_NEW = f'''{MARK} (research/gen3d_workers/patch_triposr_mcubes.py)
try:
    from torchmcubes import marching_cubes
except ImportError:
    marching_cubes = None
'''

FORWARD_OLD = '''        level = -level.view(self.resolution, self.resolution, self.resolution)
        try:'''
FORWARD_NEW = '''        level = -level.view(self.resolution, self.resolution, self.resolution)
        if self.mc_func is None:
            # PyMCubes returns vertices in grid index order (i, j, k), which is what the swap
            # below produces from torchmcubes' (k, j, i). Faces are turned outward if needed.
            import mcubes
            verts, faces = mcubes.marching_cubes(level.detach().cpu().numpy().astype(np.float32), 0.0)
            faces = faces.astype(np.int64)
            if len(faces):
                a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
                if np.einsum('ij,ij->i', a, np.cross(b, c)).sum() < 0: faces = faces[:, [0, 2, 1]]
            v_pos = torch.from_numpy(verts.astype(np.float32)) / (self.resolution - 1.0)
            return v_pos.to(level.device), torch.from_numpy(faces).to(level.device)
        try:'''


def main():
    text = TARGET.read_text(encoding='utf-8')
    if MARK in text:
        print('ya parchado:', TARGET); return
    for old in (IMPORT_OLD, FORWARD_OLD):
        if text.count(old) != 1: raise SystemExit(f'TripoSR cambió; revisa a mano {TARGET}')
    text = text.replace(IMPORT_OLD, IMPORT_NEW).replace(FORWARD_OLD, FORWARD_NEW)
    TARGET.write_text(text, encoding='utf-8')
    print('parchado:', TARGET)


if __name__ == '__main__':
    main()
