"""Small helpers that several lab modules had copied: quadrilateral overlap and atomic writes."""
import os
import time
import uuid
from pathlib import Path

import cv2
import numpy as np


def quad_iou(a, b):
    """Intersection over union of two convex quadrilaterals (four [x, y] corners each)."""
    a = np.float32(a); b = np.float32(b)
    inter = cv2.intersectConvexConvex(a, b)[0]
    union = cv2.contourArea(a) + cv2.contourArea(b) - inter
    return float(inter / union) if union > 0 else 0.


def atomic_write(path, data, encoding='utf-8', tries=20, wait=.05):
    """Write text or bytes so a reader never sees half a file: a temporary sibling, then a rename.

    On Windows the rename fails while another process has the target open (a reader, an antivirus
    scan); it is retried for about a second before giving up.
    """
    # Unique per call: two threads of one process writing the same file must not share a temporary.
    path = Path(path); tmp = path.with_name(f'{path.name}.{uuid.uuid4().hex[:12]}.tmp')
    if isinstance(data, str): tmp.write_text(data, encoding=encoding)
    else: tmp.write_bytes(data)
    for attempt in range(tries):
        try:
            os.replace(tmp, path); return path
        except PermissionError:
            if attempt == tries - 1:
                tmp.unlink(missing_ok=True); raise
            time.sleep(wait)
