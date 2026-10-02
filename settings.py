"""Paths and environment settings shared by the lab, in one place.

Modules keep their historical names (vision_onnx.REFS, name_ocr.DB, ...) as aliases of these, so
tests that patch a module constant keep working. Environment variables are read once, at import:

    YUGIOH_SCOPE             pilot (default) | full: which reference catalogue the recognizer loads
    YUGIOH_ONNX_DEVICE       cpu (default) | cuda
    YUGIOH_ENCODER           int8 | fp16 | ...: default int8 on CPU, fp16 on CUDA
    YUGIOH_ONNX_THREADS      intra-op threads per ONNX session (default 4)
    YUGIOH_GEOMETRY_THREADS  card_geometry worker threads (default 4)
    YUGIOH_CARD_BACKS        folder of card-back references (default data/card-backs)
    YUGIOH_CARD_CATEGORIES   effect categories JSON from ygo-deckforge
    YUGIOH_IDENTITY_MODE     raw: skip the curated identity release (tests)
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'

REGISTRY_DIR = DATA / 'registry'
REGISTRY_DB = REGISTRY_DIR / 'registry.sqlite'
CATALOG_DIR = DATA / 'catalog'
CATALOG_DB = CATALOG_DIR / 'catalog.sqlite'
PILOT = DATA / 'pilot'
FULL = DATA / 'full'
AUTO_SPRITES = DATA / 'auto-sprites'

SCOPE = os.environ.get('YUGIOH_SCOPE', 'pilot').lower()
if SCOPE not in ('pilot', 'full'): raise ValueError(f'YUGIOH_SCOPE={SCOPE!r}: use pilot or full')
REFS = PILOT if SCOPE == 'pilot' else FULL

ONNX_DEVICE = os.environ.get('YUGIOH_ONNX_DEVICE', 'cpu').lower()
ENCODER_VARIANT = os.environ.get('YUGIOH_ENCODER') or ('int8' if ONNX_DEVICE == 'cpu' else 'fp16')
ONNX_THREADS = int(os.environ.get('YUGIOH_ONNX_THREADS') or 4)
GEOMETRY_THREADS = int(os.environ.get('YUGIOH_GEOMETRY_THREADS') or 4)

CARD_BACKS = Path(os.environ.get('YUGIOH_CARD_BACKS') or DATA / 'card-backs')
CARD_CATEGORIES = Path(os.environ.get('YUGIOH_CARD_CATEGORIES') or ROOT.parents[1] / 'ygo-deckforge/artifacts/categories/card-categories.json')
