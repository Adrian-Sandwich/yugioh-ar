"""Evidence-backed printing/art links. Never infer an artwork from identity alone."""
import json


def build_links(db):
    """Build derived tables in a new release; caller owns the transaction.

    A unique, literal, nonempty URL on the same canonical identity supports a
    source-declared association, not independent verification of a physical card.
    Multiple artwork IDs remain ambiguous even if their images are identical.
    """
    db.executescript('''
        CREATE TABLE printing_art_links(
            printing_id TEXT NOT NULL REFERENCES printings(id),
            artwork_id TEXT NOT NULL REFERENCES artworks(id),
            canonical_card_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('source_declared','ambiguous_url')),
            method TEXT NOT NULL,
            image_url TEXT NOT NULL,
            printing_source TEXT NOT NULL,
            artwork_source TEXT NOT NULL,
            PRIMARY KEY(printing_id,artwork_id));
        CREATE INDEX printing_art_links_card ON printing_art_links(canonical_card_id,status);
        CREATE TEMP TABLE exact_art_matches AS
            SELECT p.id AS printing_id,a.id AS artwork_id,p.canonical_card_id,
                   p.image_url,p.source AS printing_source,a.source AS artwork_source
            FROM resolved_printings p JOIN resolved_artworks a
              ON p.canonical_card_id=a.canonical_card_id AND p.image_url=a.card_url
            WHERE p.image_url IS NOT NULL AND trim(p.image_url)!='';
        INSERT INTO printing_art_links
            SELECT e.printing_id,e.artwork_id,e.canonical_card_id,
                   CASE WHEN n.total=1 THEN 'source_declared' ELSE 'ambiguous_url' END,
                   'exact_card_url',e.image_url,e.printing_source,e.artwork_source
            FROM exact_art_matches e JOIN
              (SELECT printing_id,count(*) AS total FROM exact_art_matches GROUP BY printing_id) n
              ON e.printing_id=n.printing_id;
        DROP TABLE exact_art_matches;
        CREATE VIEW source_declared_printing_art AS
            SELECT * FROM printing_art_links WHERE status='source_declared';
    ''')
    counts=dict(db.execute('SELECT status,count(*) FROM printing_art_links GROUP BY status'))
    return {'links_by_status':counts,
            'printing_observations_with_link':db.execute('SELECT count(DISTINCT printing_id) FROM printing_art_links').fetchone()[0],
            'printing_observations_without_link':db.execute('SELECT count(*) FROM printings p WHERE NOT EXISTS (SELECT 1 FROM printing_art_links l WHERE l.printing_id=p.id)').fetchone()[0],
            'identities_with_link':db.execute('SELECT count(DISTINCT canonical_card_id) FROM printing_art_links').fetchone()[0],
            'independently_verified':0}


def visual_triage(db):
    """Inventory proposals, preserving every ref and the original candidate JSON.

    This queue is diagnostic only: a unique candidate is not a verified identity.
    Canonicalization combines candidate identities, never image references.
    """
    mapping=dict(db.execute('SELECT source_card_id,canonical_card_id FROM identity_map'))
    rows=[]
    for ref_id,source,path,card_id,status,reason,raw in db.execute('''
        SELECT ref_id,source,path,card_id,status,reason,candidates_json
        FROM visual_references WHERE status IN ('proposed','unresolved') ORDER BY ref_id'''):
        invalid=False
        try:
            candidates=json.loads(raw or '[]')
            if not isinstance(candidates,list) or any(not isinstance(c,str) for c in candidates):
                raise ValueError('Expected identity list')
        except (ValueError,TypeError):
            candidates=[];invalid=True
        ids=set(candidates)
        if card_id:ids.add(card_id)
        unknown=sorted(ids-mapping.keys())
        canonical=sorted({mapping[c] for c in ids if c in mapping})
        state=('invalid_candidates' if invalid else 'unknown_identity' if unknown else
               'no_candidate' if not canonical else 'multiple_candidates' if len(canonical)>1 else
               'unique_candidate_needs_verification')
        rows.append({'ref_id':ref_id,'source':source,'path':path,'original_status':status,
                     'original_card_id':card_id,'original_reason':reason,'original_candidates_json':raw,
                     'triage':state,'canonical_candidates':canonical,'unknown_ids':unknown})
    return rows


def export_evidence(db,directory):
    import csv
    from collections import Counter
    cursor=db.execute('SELECT * FROM printing_art_links ORDER BY printing_id,artwork_id')
    with (directory/'printing-art-links.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow([c[0] for c in cursor.description]);writer.writerows(cursor)
    rows=visual_triage(db)
    with (directory/'visual-review-queue.jsonl').open('w',encoding='utf-8') as stream:
        for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    summary={'references_pending':len(rows),'by_triage':dict(Counter(r['triage'] for r in rows)),
             'by_source':dict(Counter(r['source'] for r in rows)),
             'policy':'Diagnostic proposals only. No approvals, image edits or deduplication.'}
    (directory/'visual-review-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary
