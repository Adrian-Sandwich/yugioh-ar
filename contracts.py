"""What travels between the lab's parts, defined once.

The recognizer (vision_onnx) produces detections; the viewer (camera_viewer) normalises them,
names them (describe) and hands them to the tracker (live_tracking), the OCR worker
(passcode_ocr), the duel (table_duel) and the browser (/analysis, X-Tracks). These were plain
dicts whose keys lived only in the code that built them; a misspelt key read as None, silently.
The TypedDicts below are documentation and the reference for `missing()`, which the qa checks
use; nothing is validated at run time on the live path.
"""
from typing import Literal, Optional, TypedDict

Quad = list  # four [x, y] corners, card order (top-left, top-right, bottom-right, bottom-left)


class Candidate(TypedDict, total=False):
    """One identity in a detection's top5: best reference per card, by score."""
    card_id: str
    score: float
    ref_id: Optional[str]
    artwork_id: Optional[str]


class Detection(TypedDict, total=False):
    """A card box from vision_onnx.ResearchRecognizer.detect (one per detected box)."""
    # always present
    card_id: Optional[str]            # top identity (canonical after identity_resolution.normalize_detection)
    corners: Quad                     # refined (or tracked) corners, rotated so the card is upright
    detector_corners: Quad            # the detector's own box, same rotation
    score: float                      # embedding/classifier score of card_id
    margin: float                     # score minus the best different identity
    accepted: bool                    # passed the acceptance rule (or a promotion below)
    top5: list                        # list[Candidate]
    rotation: int                     # 0/90/180/270 applied to the crop
    detector_score: float
    geometry_status: str              # contour_refined | snapped | tracked | frame_edge | unresolved ...
    geometry_iou: Optional[float]
    identity_source: Literal['embedding', 'classifier', 'track', 'none']
    # sometimes present
    acceptance: Optional[str]         # score | art_verified | name_ocr | None when not accepted
    reuse_iou: float                  # identity_source == 'track': overlap with the reused track
    track_id: int                     # identity_source == 'track'
    rejected_as: str                  # 'card_back': a strong back score in its zone overrode it
    art_inliers: int; art_artwork_id: str                 # acceptance == 'art_verified'
    name_similarity: float; name_text: str                # acceptance == 'name_ocr'
    name_scope: str                   # 'candidates' (title named one of top5) | 'global' (whole registry, score 0)
    source_card_id: str               # card_id before canonicalisation
    # added by LiveRecognizer.describe (accepted detections only)
    id: str                           # reference id used for the sprite
    name: str
    sprite_ref: Optional[str]         # tdoane:sprite:<file> | auto:<code>.png | None
    experimental: bool
    # added by the viewer
    stable: bool                      # ar_overlay.Tracker: same identity in two consecutive analyses
    sprite_url: str


# Keys every detection carries, whatever path built it.
DETECTION_REQUIRED = ('card_id', 'corners', 'detector_corners', 'score', 'margin', 'accepted', 'top5', 'rotation',
                      'detector_score', 'geometry_status', 'geometry_iou', 'identity_source')


class Track(TypedDict, total=False):
    """A followed card in live_tracking.LiveTracker (identity copied from an accepted detection)."""
    track_id: int                     # unique across restarts (millisecond start); the duel's copy_id
    corners: Quad                     # at video rate, from optical flow between analyses
    verified_at: float                # capture time of the analysis that last confirmed it
    tracked_at: float                 # capture time of the last frame the flow reached
    created_at: float
    frames: int
    inliers: Optional[int]
    stable: bool
    # identity, copied from the detection (IDENTITY_FIELDS)
    card_id: str; name: str; sprite_ref: Optional[str]; score: float; margin: float; rotation: int
    top5: list; ref_id: str; artwork_id: str; id: str; acceptance: Optional[str]; source_card_id: str


# Detection fields a track copies at each confirming analysis (live_tracking.sync).
IDENTITY_FIELDS = ('card_id', 'name', 'sprite_ref', 'score', 'margin', 'rotation', 'top5', 'ref_id', 'artwork_id', 'id',
                   'acceptance', 'source_card_id')
# Track fields sent to the browser (X-Tracks header, /analysis tracks): small and ASCII-safe.
TRACK_FIELDS = ('track_id', 'card_id', 'name', 'sprite_ref', 'corners', 'stable', 'verified_at', 'tracked_at', 'acceptance',
                'inliers', 'frames')

# Context the viewer passes to a recognizer's analyze_jpeg (and inference_host forwards to the
# child process): reuse = fresh stable tracks, verified = OCR/art evidence, regions = duel field
# zones, back_zones = zones to check for card backs. A new one is added here, in camera_viewer
# (producer) and in vision_onnx.analyze_jpeg (consumer); inference_host passes them through.
ANALYZE_CONTEXT = ('reuse', 'verified', 'regions', 'back_zones')


def missing(item, required):
    """Keys of `required` absent from the dict `item` (for qa checks)."""
    return [k for k in required if k not in item]
