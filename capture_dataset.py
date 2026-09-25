"""Save user-labelled real captures without mixing session splits."""
import base64
import hashlib
import json
import re
import uuid

import cv2
import numpy as np
from catalog import ROOT,LANGS,connect

DATASET=ROOT/'data/pilot/captures'


def save_capture(payload):
    session=payload.get('session','')
    split=payload.get('split')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',session):
        raise ValueError('La sesión debe usar letras, números, guiones o guiones bajos')
    if split not in ('train','validation','test'):
        raise ValueError('Partición inválida')
    language=payload.get('language') or None
    if language not in (*LANGS,None):
        raise ValueError('Idioma inválido')
    card_id=payload.get('card_id') or None
    if card_id:
        with connect() as conn:
            if not conn.execute('SELECT 1 FROM cards WHERE id=?',(card_id,)).fetchone():
                raise ValueError('Identidad inexistente')
    data=base64.b64decode(payload['image'].split(',',1)[-1],validate=True)
    if len(data)>12*1024*1024: raise ValueError('Imagen demasiado grande')
    suffix='.jpg' if data.startswith(b'\xff\xd8') else '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else None
    if not suffix: raise ValueError('Usa JPEG o PNG')
    image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise ValueError('Imagen ilegible')
    h,w=image.shape[:2]
    if h*w>32000000: raise ValueError('Imagen demasiado grande')
    corners=np.float32(payload.get('corners',[]))
    if corners.shape!=(4,2) or not np.isfinite(corners).all() or not cv2.isContourConvex(corners) or cv2.contourArea(corners)<100:
        raise ValueError('Marca cuatro esquinas consecutivas de una carta visible')
    if (corners<0).any() or (corners[:,0]>=w).any() or (corners[:,1]>=h).any():
        raise ValueError('Esquinas fuera de la imagen')
    DATASET.mkdir(parents=True,exist_ok=True)
    manifest=DATASET/'annotations.jsonl'
    rows=[json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines()] if manifest.exists() else []
    sha=hashlib.sha256(data).hexdigest()
    if any(r['session']==session and r['split']!=split for r in rows):
        raise ValueError('Esta sesión ya pertenece a otra partición; no mezcles fotogramas de una sesión')
    if any(r['image_sha256']==sha and r['split']!=split for r in rows):
        raise ValueError('La misma imagen ya está en otra partición')
    sample_id=uuid.uuid4().hex
    path=DATASET/(sha+suffix)
    if not path.exists(): path.write_bytes(data)
    record={'id':sample_id,'image':path.name,'image_sha256':sha,'width':w,'height':h,'session':session,'split':split,
            'card_id':card_id,'printed_language':language,'corners':corners.tolist(),
            'physical_copy':str(payload.get('physical_copy',''))[:100],
            'artwork':str(payload.get('artwork',''))[:150], 'finish':str(payload.get('finish',''))[:150],
            'condition':str(payload.get('condition','normal'))[:200],
            'label_source':'human annotation; not automatically verified'}
    with manifest.open('a',encoding='utf-8') as out: out.write(json.dumps(record,ensure_ascii=False)+'\n')
    return {'saved':True,'sample_id':sample_id,'image':path.name,'annotations':len(rows)+1}
