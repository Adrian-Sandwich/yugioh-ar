"""Second votes that accept a candidate the recognizer rejected: the illustration verified by SIFT
(promote_by_art) or the printed title read by OCR (promote_by_name). Evidence comes from the OCR
worker (passcode_ocr.PasscodeWorker.verified); the score itself is never changed."""
import time

from identity_resolution import canonical
from util import quad_iou

ART_PROMOTION_MAX_AGE_S = 4.
ART_PROMOTION_MIN_IOU = .5
# A title read on a card stays valid this long while the card stays where it was read (IoU).
NAME_MEMORY_S = 20.


def promote_by_art(candidates,verified,now=None):
    """Accept a rejected candidate whose top-1 identity was verified on the illustration.

    `verified` items come from the asynchronous art verifier: corners, card_id,
    inliers and captured_at. Only the same identity, on an overlapping card,
    within ART_PROMOTION_MAX_AGE_S, counts. The score itself is untouched.
    """
    now=time.time() if now is None else now
    promoted=0
    for candidate in candidates:
        if candidate.get('accepted') or not candidate.get('card_id') or candidate.get('rejected_as'): continue
        for item in verified:
            if item.get('evidence')=='name': continue   # title evidence: promote_by_name
            if canonical(item.get('card_id'))!=canonical(candidate['card_id']): continue
            if not 0<=now-item.get('captured_at',0)<=ART_PROMOTION_MAX_AGE_S: continue
            if quad_iou(candidate['corners'],item['corners'])<ART_PROMOTION_MIN_IOU: continue
            candidate.update(accepted=True,acceptance='art_verified',art_inliers=item.get('inliers'),art_artwork_id=item.get('artwork_id'))
            promoted+=1;break
    return promoted


def promote_by_name(candidates,verified,now=None,max_age=ART_PROMOTION_MAX_AGE_S):
    """Accept a rejected candidate when the title OCR names one of its own top-5 identities.

    Two independent weak votes: the card is among the recognizer's candidates, and its printed
    name, read on the same card (overlapping corners, recent frame), resembles that candidate
    more than any other name in the registry (name_ocr.pick_by_name). For printings whose
    illustration no longer looks like the reference: Ghost, Starlight, glare. The chosen
    identity moves to the front of top5 so sprite and name follow it.
    """
    now=time.time() if now is None else now
    promoted=0
    for candidate in candidates:
        if candidate.get('accepted') or not candidate.get('top5') or candidate.get('rejected_as'): continue
        for item in verified:
            if item.get('evidence')!='name': continue
            if not 0<=now-item.get('captured_at',0)<=max_age: continue
            if quad_iou(candidate['corners'],item['corners'])<ART_PROMOTION_MIN_IOU: continue
            chosen=next((t for t in candidate['top5'] if canonical(t.get('card_id'))==canonical(item['card_id'])),None)
            if chosen is None:
                # A title that won over the whole registry (name_ocr.pick_global) stands alone: the art
                # gave no vote for it, so its score is 0 and the identity comes from the name only.
                if item.get('scope')!='global': continue
                chosen={'card_id':item['card_id'],'score':0.,'ref_id':None,'artwork_id':None}
            candidate.update(accepted=True,acceptance='name_ocr',card_id=chosen['card_id'],score=chosen.get('score',candidate.get('score')),
                             top5=[chosen]+[t for t in candidate['top5'] if t is not chosen],name_similarity=item.get('similarity'),name_text=item.get('text'),
                             name_scope=item.get('scope','candidates'))
            promoted+=1;break
    return promoted
