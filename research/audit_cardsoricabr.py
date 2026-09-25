"""Verify downloaded originals and report image dimensions and exact duplicates."""
import collections
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads' / 'cardsoricabr'


def main():
    state = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    dimensions = collections.Counter()
    hashes = collections.defaultdict(list)
    errors = []
    images = []
    total = 0
    for item in state['files'].values():
        path = BASE / item['path']
        try:
            if item['status'] != 'ok':
                raise ValueError('Download not completed')
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != item['sha256'] or len(raw) != item['bytes']:
                raise ValueError('Hash or size mismatch')
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise ValueError('Image could not be decoded')
            height, width = image.shape[:2]
            dimensions[f'{width}x{height}'] += 1
            hashes[digest].append(item['id'])
            images.append({'id': item['id'], 'width': width, 'height': height})
            total += len(raw)
        except Exception as exc:
            errors.append({'id': item['id'], 'error': str(exc)})
    report = {
        'discovery_complete': state.get('discovery_complete', False),
        'folders': len(state['folders']), 'expected_files': len(state['files']),
        'verified_images': len(images), 'total_bytes': total,
        'dimensions': dict(dimensions.most_common()), 'unique_sha256': len(hashes),
        'duplicate_groups': [ids for ids in hashes.values() if len(ids) > 1],
        'errors': errors, 'images': images,
        'note': 'Exact hashes only: visually similar images, identity, language, art and rarity remain unaudited.',
    }
    (BASE / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('images', 'duplicate_groups', 'dimensions')}, ensure_ascii=True))
    print('Most common dimensions:', dimensions.most_common(12))
    print('Exact duplicate groups:', len(report['duplicate_groups']))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
