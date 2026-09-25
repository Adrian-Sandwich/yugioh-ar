"""Reference-image matching with SIFT and geometric verification, CPU only.

Detects at most one instance per reference. Scores are geometric diagnostics,
not calibrated probabilities. No rule engine or temporal tracking yet.
"""

import json
import time
from pathlib import Path

import cv2
import numpy as np


class Recognizer:
    def __init__(self, catalog=None):
        cv2.setNumThreads(2)
        self.sift = cv2.SIFT_create(nfeatures=3000)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.references = []
        catalog = Path(catalog or Path(__file__).parent / "data/references/catalog.json")
        for entry in json.loads(catalog.read_text(encoding="utf-8")):
            image = cv2.imread(str(catalog.parent / entry["source"]))
            if image is None:
                raise ValueError(f"Missing reference: {entry['source']}")
            width, height = 420, 610
            ih, iw = image.shape[:2]
            quad = np.float32(entry.get("corners", [[0,0],[iw-1,0],[iw-1,ih-1],[0,ih-1]]))
            rectangle = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
            transform = cv2.getPerspectiveTransform(quad, rectangle)
            reference = cv2.warpPerspective(image, transform, (width, height))
            gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
            mask = np.zeros_like(gray)
            # Exclude card borders and the repeated text frame; use artwork only.
            mask[105:435, 35:385] = 255
            points, descriptors = self.sift.detectAndCompute(gray, mask)
            if descriptors is None or len(points) < 14:
                raise ValueError(f"Not enough reference features: {entry['name']}")
            self.references.append((entry, rectangle, points, descriptors))

    def detect(self, frame):
        started = time.perf_counter()
        height, width = frame.shape[:2]
        scale = min(1.0, 1280 / width)
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        points, descriptors = self.sift.detectAndCompute(gray, None)
        detections = []
        if descriptors is not None and len(points) >= 2:
            for entry, rectangle, ref_points, ref_descriptors in self.references:
                pairs = self.matcher.knnMatch(ref_descriptors, descriptors, k=2)
                matches = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance]
                # Enforce unique destination features before fitting the plane.
                unique = {}
                for match in sorted(matches, key=lambda item: item.distance):
                    unique.setdefault(match.trainIdx, match)
                matches = list(unique.values())
                if len(matches) < 14:
                    continue
                src = np.float32([ref_points[m.queryIdx].pt for m in matches])
                dst = np.float32([points[m.trainIdx].pt for m in matches])
                matrix, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
                if matrix is None or inlier_mask is None:
                    continue
                inliers = inlier_mask.ravel().astype(bool)
                count = int(inliers.sum())
                ratio = count / len(matches)
                if count < 12 or ratio < 0.55:
                    continue
                coverage = cv2.contourArea(cv2.convexHull(src[inliers])) / (420 * 610)
                if coverage < 0.12:
                    continue
                corners = cv2.perspectiveTransform(rectangle.reshape(-1, 1, 2), matrix).reshape(4, 2) / scale
                if not np.isfinite(corners).all() or not cv2.isContourConvex(corners.astype(np.float32)):
                    continue
                area = cv2.contourArea(corners.astype(np.float32))
                if not 0.003 * width * height < area < 0.85 * width * height:
                    continue
                if (corners[:, 0] < 0).any() or (corners[:, 0] >= width).any() or (corners[:, 1] < 0).any() or (corners[:, 1] >= height).any():
                    continue
                detections.append({"id": entry["id"], "name": entry["name"],
                                   "corners": corners.round(1).tolist(), "inliers": count,
                                   "matches": len(matches), "inlier_ratio": round(ratio, 3),
                                   "reference_coverage": round(coverage, 3)})
        return {"detections": detections, "processing_ms": round((time.perf_counter() - started) * 1000, 1),
                "width": width, "height": height}

    def analyze_jpeg(self, data):
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Invalid JPEG")
        return self.detect(frame)


class PilotRecognizer(Recognizer):
    """Several identities/arts and up to three visible copies per reference.

    Reverse matching lets different camera keypoints match the same reference
    feature, followed by separate geometric fits. Conservative geometric gates
    remain necessary; this is a pilot rather than a full-catalog search engine.
    """
    def __init__(self, catalog=None):
        super().__init__(catalog or Path(__file__).parent/'data/pilot/catalog.json')
        # Keep distinctive reference features to bound pilot CPU costs.
        refs=[]
        for entry,rectangle,points,descriptors in self.references:
            indices=sorted(range(len(points)),key=lambda i:-points[i].response)[:900]
            refs.append((entry,rectangle,[points[i] for i in indices],descriptors[indices]))
        self.references=refs

    def detect(self,frame):
        started=time.perf_counter();height,width=frame.shape[:2]
        scale=min(1.0,1280/width)
        small=cv2.resize(frame,None,fx=scale,fy=scale) if scale<1 else frame
        points,descriptors=self.sift.detectAndCompute(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY),None)
        candidates=[]
        if descriptors is not None and len(points)>=14:
            for entry,rectangle,ref_points,ref_descriptors in self.references:
                pairs=self.matcher.knnMatch(descriptors,ref_descriptors,k=2)
                matches=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance<.68*pair[1].distance]
                for instance in range(3):
                    if len(matches)<14: break
                    src=np.float32([ref_points[m.trainIdx].pt for m in matches])
                    dst=np.float32([points[m.queryIdx].pt for m in matches])
                    matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,3.0)
                    if matrix is None or mask is None: break
                    inliers=mask.ravel().astype(bool);count=int(inliers.sum())
                    unique=len({m.trainIdx for m,valid in zip(matches,inliers) if valid})
                    if count<14 or unique<12: break
                    coverage=cv2.contourArea(cv2.convexHull(src[inliers]))/(420*610)
                    corners=cv2.perspectiveTransform(rectangle.reshape(-1,1,2),matrix).reshape(4,2)/scale
                    valid=np.isfinite(corners).all() and cv2.isContourConvex(corners.astype(np.float32))
                    if valid:
                        area=cv2.contourArea(corners.astype(np.float32))
                        valid=.003*width*height<area<.85*width*height and coverage>=.12 and (corners[:,0]>=0).all() and (corners[:,0]<width).all() and (corners[:,1]>=0).all() and (corners[:,1]<height).all()
                    if valid:
                        inside=[cv2.pointPolygonTest((corners*scale).astype(np.float32),tuple(map(float,p)),False)>=0 for p in dst]
                        local_count=sum(inside)
                        ratio=count/max(local_count,1)
                        if ratio>=.55:
                            candidates.append({'id':entry['id'],'card_id':entry.get('card_id',entry['id']),
                                'artwork_id':entry.get('artwork_id'),'sprite_ref':entry.get('sprite_ref'),
                                'name':entry['name'],'corners':corners.round(1).tolist(),'inliers':count,
                                'matches':local_count,'inlier_ratio':round(ratio,3),'reference_coverage':round(coverage,3)})
                        matches=[m for m,contained in zip(matches,inside) if not contained]
                    else:
                        matches=[m for m,valid in zip(matches,inliers) if not valid]
        detections=[]
        def overlap(a,b):
            a,b=np.float32(a['corners']),np.float32(b['corners'])
            intersection=cv2.intersectConvexConvex(a,b)[0]
            return intersection/max(cv2.contourArea(a)+cv2.contourArea(b)-intersection,1)
        ordered=sorted(candidates,key=lambda d:-d['inliers'])
        for candidate in ordered:
            if any(overlap(candidate,other)>.5 for other in detections): continue
            if any(other['card_id']!=candidate['card_id'] and other['inliers']>=candidate['inliers']*.8 and overlap(candidate,other)>.6 for other in ordered): continue
            detections.append(candidate)
        return {'detections':detections,'processing_ms':round((time.perf_counter()-started)*1000,1),
                'width':width,'height':height,'references':len(self.references),'mode':'sift-pilot'}
