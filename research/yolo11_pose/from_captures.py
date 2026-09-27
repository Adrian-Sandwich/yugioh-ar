"""Bridge: capture-page annotations (annotations.jsonl) -> reviewed scenes for YOLO11 import.

The capture page (http://127.0.0.1:8768/capture, capture_dataset.py) stores one
record per card with corners TL,TR,BR,BL, session and split. The detector
importer (import_annotations.py) needs one `<image>.pose.json` per scene with
ALL cards marked, because an unmarked card becomes a false negative in
training. The capture page has no "I marked every card" checkbox, so the
sessions certified as exhaustive are declared here explicitly. Split names
differ ('validation' vs 'val'); this maps them.

    .venv-eval/Scripts/python.exe research/yolo11_pose/from_captures.py data/pilot/captures data/pose/from-captures-v1 --exhaustive-sessions pixel_madera_20260927_1 pixel_madera_20260927_2
    .venv-pose/Scripts/python.exe research/yolo11_pose/import_annotations.py data/pose/from-captures-v1 data/pose/real-v1
"""
import argparse, json, shutil
from pathlib import Path

SPLITS = {'train': 'train', 'validation': 'val', 'val': 'val', 'test': 'test'}


def convert(captures, output, exhaustive_sessions):
    captures = Path(captures); output = Path(output)
    rows = [json.loads(l) for l in (captures / 'annotations.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    certified = set(exhaustive_sessions)
    scenes = {}
    skipped = {'session_not_certified': 0, 'unknown_split': 0}
    for r in rows:
        if r['session'] not in certified:
            skipped['session_not_certified'] += 1; continue
        if r.get('split') not in SPLITS:
            skipped['unknown_split'] += 1; continue
        scene = scenes.setdefault(r['image_sha256'], {'image': r['image'], 'image_sha256': r['image_sha256'], 'width': r['width'], 'height': r['height'],
                                                     'session': r['session'], 'split': SPLITS[r['split']], 'corner_order': ['TL', 'TR', 'BR', 'BL'],
                                                     'reviewed': True, 'exhaustive': True, 'objects': [],
                                                     'source': 'capture page (capture_dataset.py); exhaustive declared by the operator at conversion'})
        if scene['session'] != r['session'] or scene['split'] != SPLITS[r['split']]:
            raise ValueError(f"La imagen {r['image']} aparece en dos sesiones o particiones")
        scene['objects'].append({'corners': r['corners'], 'visibility': [2, 2, 2, 2], 'card_id': r.get('card_id'), 'physical_copy': r.get('physical_copy'),
                                 'condition': r.get('condition'), 'annotation_id': r['id']})
    if output.exists() and any(output.iterdir()):
        raise ValueError('La carpeta de salida debe ser nueva o estar vacía')
    output.mkdir(parents=True, exist_ok=True)
    for scene in scenes.values():
        shutil.copyfile(captures / scene['image'], output / scene['image'])
        (output / (Path(scene['image']).stem + '.pose.json')).write_text(json.dumps(scene, ensure_ascii=False, indent=1), encoding='utf-8')
    splits = {}
    for s in scenes.values():
        splits[s['split']] = splits.get(s['split'], 0) + 1
    return {'scenes': len(scenes), 'cards': sum(len(s['objects']) for s in scenes.values()), 'by_split': splits, 'skipped': skipped,
            'note': 'Negatives (photos without cards) cannot come from the capture page; add them with the pose annotator.'}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('captures', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--exhaustive-sessions', nargs='+', required=True, help='sessions in which EVERY card of every photo was annotated')
    a = p.parse_args()
    print(json.dumps(convert(a.captures, a.output, a.exhaustive_sessions), ensure_ascii=False))


if __name__ == '__main__':
    main()
