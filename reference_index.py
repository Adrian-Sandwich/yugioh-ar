"""The reference index: one embedding per reference image of the current scope (pilot or full),
plus photographs of the owner's cards (enroll_reference.py). Built incrementally (build_index)."""
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np

import settings
from onnx_models import ENCODER_VARIANT, Encoder

PILOT = settings.PILOT
SCOPE = settings.SCOPE
REFS = settings.REFS


def index_paths(variant=None):
    """Index files of the current scope for an encoder variant; int8 keeps the historical names."""
    variant=variant or ENCODER_VARIANT
    stem='embeddings' if variant=='int8' else f'embeddings-{variant}'
    return REFS/f'{stem}.npy',REFS/f'{stem}.json'


def reference_entries(catalog_path=REFS/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    """Scope references plus photographs of the owner's physical cards (enroll_reference.py)."""
    entries=json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    enrolled=json.loads(Path(enrolled_path).read_text(encoding='utf-8')) if Path(enrolled_path).exists() else []
    for entry in enrolled:
        # Enrolled sources are relative to the pilot folder, whatever the scope.
        entry.setdefault('enrolled',True);entry['base']=str(Path(enrolled_path).parent)
    return entries+enrolled


def references_digest(catalog_path=REFS/'catalog.json',enrolled_path=PILOT/'enrolled.json'):
    digest=hashlib.sha256(Path(catalog_path).read_bytes())
    if Path(enrolled_path).exists(): digest.update(Path(enrolled_path).read_bytes())
    return digest.hexdigest()


def previous_index(catalog_path,encoder):
    """ref_id -> (row, vector) of the index on disk, when it was made by this same encoder."""
    vectors_path,metadata_path=index_paths(encoder.variant)
    folder=Path(catalog_path).parent;vectors_path,metadata_path=folder/vectors_path.name,folder/metadata_path.name
    try:
        metadata=json.loads(metadata_path.read_text());vectors=np.load(vectors_path)
        if metadata.get('model_sha256')!=hashlib.sha256(encoder.model_path.read_bytes()).hexdigest() or len(vectors)!=len(metadata['rows']): return {}
        return {row['ref_id']:(row,vectors[i]) for i,row in enumerate(metadata['rows'])}
    except (OSError,ValueError,KeyError): return {}


def build_index(catalog_path=REFS/'catalog.json',encoder=None):
    """Encode every reference; one whose file is unchanged since the index on disk keeps its vector.

    Incremental on 28/09/2026: enrolling one photo re-encoded all 14,782 references of the full scope
    (~3 min) inside an analysis, past the recognizer child's 25 s timeout, which then restarted in a
    loop. Unchanged means same source, size and mtime (a 2 s stat), or failing that the same SHA-256.
    """
    entries=reference_entries(catalog_path)
    encoder=encoder or Encoder();previous=previous_index(catalog_path,encoder)
    vectors=[None]*len(entries);rows=[None]*len(entries);todo=[];reused=0
    for n,entry in enumerate(entries):
        path=(Path(entry.get('base') or Path(catalog_path).parent)/entry['source']).resolve()
        st=path.stat();stamp=[st.st_size,st.st_mtime_ns]
        row={'ref_id':entry['id'],'card_id':entry['card_id'],'artwork_id':entry.get('artwork_id'),
             'enrolled':bool(entry.get('enrolled')),'source':entry['source'],'stamp':stamp}
        old,vector=previous.get(entry['id'],(None,None))
        if old is not None and old.get('source') in (None,entry['source']):
            same=old.get('stamp')==stamp
            if not same:
                raw=path.read_bytes();row['image_sha256']=hashlib.sha256(raw).hexdigest();same=old.get('image_sha256')==row['image_sha256']
            if same:
                row.setdefault('image_sha256',old.get('image_sha256'));rows[n]=row;vectors[n]=vector;reused+=1;continue
        rows[n]=row;todo.append((n,path))
    # Float encoders batch 32 references per run (lote/imagen drift 0.0001); int8
    # keeps one run per reference so the historical index reproduces exactly.
    step=1 if encoder.variant=='int8' else 32
    for start in range(0,len(todo),step):
        chunk=todo[start:start+step];images=[];data=[]
        for _,path in chunk:
            data.append(path.read_bytes());images.append(cv2.imdecode(np.frombuffer(data[-1],np.uint8),cv2.IMREAD_COLOR))
        for (n,_),raw,(_,z) in zip(chunk,data,encoder.predict_batch(images,classify=False)):
            vectors[n]=z;rows[n]['image_sha256']=hashlib.sha256(raw).hexdigest()
        done=start+len(chunk)
        if done%(10 if len(todo)<1000 else 1024)<len(chunk) or done==len(todo): print('INDEX',done,'/',len(todo),'new;',reused,'reused',flush=True)
    out=Path(catalog_path).parent
    vectors_path,metadata_path=index_paths(encoder.variant)
    # Atomic replace: two viewers may rebuild after the same pilot change, and a
    # reader must never load half a file. Vectors first, metadata (the digest) last.
    suffix=f'.{os.getpid()}.tmp'
    with open(out/(vectors_path.name+suffix),'wb') as f: np.save(f,np.stack(vectors))
    os.replace(out/(vectors_path.name+suffix),out/vectors_path.name)
    (out/(metadata_path.name+suffix)).write_text(json.dumps({'rows':rows,'encoder_variant':encoder.variant,
        'model_sha256':hashlib.sha256(encoder.model_path.read_bytes()).hexdigest(),
        'catalog_sha256':references_digest(catalog_path),
        'dimension':len(vectors[0]),'normalization':'L2','retrieval':'exact cosine','scope':f'{SCOPE} plus enrolled photos; thresholds not calibrated'},indent=2))
    os.replace(out/(metadata_path.name+suffix),out/metadata_path.name)
    print('INDEX DONE',len(rows),flush=True)
