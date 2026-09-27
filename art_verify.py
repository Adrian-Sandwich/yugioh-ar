"""Geometric verification of embedding candidates against self-hosted cropped artwork.

The embedding proposes identities; this checks whether the photographed
illustration actually contains the candidate's artwork, with SIFT matches and
a RANSAC homography. It is a second, independent visual method: it never
proposes cards outside the candidate list, never lowers the recognizer's
thresholds, and reports ambiguity when two candidates fit the crop.
"""
import json
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
from identity_resolution import canonical

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'downloads/ygoprodeck-art/manifest.json'
# Illustration window of a rectified card (fractions of width/height); wide
# enough for classic and Pendulum layouts, excluding name and text boxes.
ART_REGION = (.07, .156, .93, .73)
MIN_INLIERS, MIN_RATIO, MIN_COVERAGE, MARGIN = 30, .6, .15, 2.


class ArtVerifier:
    def __init__(self, manifest=MANIFEST, cache_limit=400, features=800):
        self.arts = {}
        self.available = Path(manifest).exists()
        if self.available:
            items = json.loads(Path(manifest).read_text(encoding='utf-8'))['items']
            base = Path(manifest).parent
            for art_id, item in items.items():
                if item.get('status') == 'ok':
                    self.arts.setdefault(canonical(item['card_id']), []).append((art_id, base / item['path']))
        self.sift = cv2.SIFT_create(nfeatures=features)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.cache = OrderedDict(); self.cache_limit = cache_limit

    def reference(self, art_id, path):
        cached = self.cache.get(art_id)
        if cached is not None:
            self.cache.move_to_end(art_id); return cached
        image = cv2.imread(str(path))
        if image is None:
            return None
        image = cv2.resize(image, (350, max(1, round(350 * image.shape[0] / image.shape[1]))))
        points, descriptors = self.sift.detectAndCompute(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), None)
        entry = (np.float32([p.pt for p in points]) if points else np.empty((0, 2), np.float32), descriptors, image.shape[:2])
        self.cache[art_id] = entry
        while len(self.cache) > self.cache_limit:
            self.cache.popitem(last=False)
        return entry

    def match(self, crop_points, crop_descriptors, reference):
        ref_points, ref_descriptors, shape = reference
        if ref_descriptors is None or crop_descriptors is None or len(ref_points) < 8 or len(crop_points) < 8:
            return {'inliers': 0, 'matches': 0, 'ratio': 0., 'coverage': 0.}
        pairs = self.matcher.knnMatch(ref_descriptors, crop_descriptors, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .7 * p[1].distance]
        unique = {}
        for m in sorted(good, key=lambda m: m.distance):
            unique.setdefault(m.trainIdx, m)
        good = list(unique.values())
        if len(good) < 8:
            return {'inliers': 0, 'matches': len(good), 'ratio': 0., 'coverage': 0.}
        src = ref_points[[m.queryIdx for m in good]]; dst = crop_points[[m.trainIdx for m in good]]
        matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if matrix is None or mask is None:
            return {'inliers': 0, 'matches': len(good), 'ratio': 0., 'coverage': 0.}
        inliers = mask.ravel().astype(bool); count = int(inliers.sum())
        coverage = float(cv2.contourArea(cv2.convexHull(src[inliers])) / (shape[0] * shape[1])) if count >= 3 else 0.
        # Rotation of the reference inside the crop: SIFT is rotation invariant,
        # so the homography, not the crop, tells whether the card is upside down.
        angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
        return {'inliers': count, 'matches': len(good), 'ratio': round(count / len(good), 3), 'coverage': round(coverage, 3), 'angle': round(angle, 1)}

    def verify(self, rectified, candidate_ids, limit=3):
        """Best artwork per candidate; orientation from the homography; explicit ambiguity."""
        started = time.perf_counter()
        candidates = [c for c in dict.fromkeys(canonical(c) for c in (candidate_ids or [])) if c][:limit]
        if not candidates:
            return {'status': 'skipped', 'reason': 'no_candidates', 'card_id': None, 'matches': [], 'candidates': []}
        if not self.available:
            return {'status': 'skipped', 'reason': 'references_unavailable', 'card_id': None, 'matches': [], 'candidates': []}
        h, w = rectified.shape[:2]; x0, y0, x1, y1 = ART_REGION
        # One crop: the window still holds most of the illustration when the
        # card is upside down, and the homography angle reports that case.
        crop = rectified[round(y0 * h):round(y1 * h), round(x0 * w):round(x1 * w)]
        keypoints, descriptors = self.sift.detectAndCompute(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None)
        points = np.float32([p.pt for p in keypoints]) if keypoints else np.empty((0, 2), np.float32)
        results = []
        for card_id in candidates:
            best = None
            for art_id, path in self.arts.get(card_id, []):
                reference = self.reference(art_id, path)
                if reference is None:
                    continue
                scored = self.match(points, descriptors, reference)
                if best is None or scored['inliers'] > best['inliers']:
                    best = {**scored, 'card_id': card_id, 'artwork_id': art_id,
                            'orientation': 180 if abs(scored.get('angle', 0.)) > 90 else 0}
            results.append(best or {'card_id': card_id, 'inliers': 0, 'matches': 0, 'ratio': 0., 'coverage': 0., 'artwork_id': None, 'orientation': None, 'reason': 'no_reference_art'})
        results.sort(key=lambda r: -r['inliers'])
        best = results[0]; second = results[1]['inliers'] if len(results) > 1 else 0
        passes = best['inliers'] >= MIN_INLIERS and best['ratio'] >= MIN_RATIO and best['coverage'] >= MIN_COVERAGE
        if passes and best['inliers'] >= MARGIN * max(second, 1):
            status, card_id = 'matched', best['card_id']
        elif passes:
            status, card_id = 'ambiguous', None
        else:
            status, card_id = 'unverified', None
        return {'status': status, 'card_id': card_id, 'orientation': best['orientation'] if status == 'matched' else None,
                'matches': [{'card_id': best['card_id'], 'artwork_id': best['artwork_id'], 'inliers': best['inliers'], 'ratio': best['ratio'], 'coverage': best['coverage']}] if status == 'matched' else [],
                'candidates': [{k: r.get(k) for k in ('card_id', 'artwork_id', 'inliers', 'ratio', 'coverage', 'orientation')} for r in results],
                'processing_ms': round((time.perf_counter() - started) * 1000)}
