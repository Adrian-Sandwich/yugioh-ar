"""Card name keys: one normalization for every lookup by name (registry, catalog, OCR).

Two modes, both deliberate: accents folded (search and OCR: "Walkure" finds "Walküre") or kept
(curated registry evidence: two names that differ only by accents stay different). Before
02/10/2026 they were written three times (catalog with NFKD, curated_registry and name_ocr with
NFKC); over the registry's 115,044 names the copies gave identical keys.
"""
import unicodedata


def name_key(text, fold_accents=False):
    text = unicodedata.normalize('NFKC', text).casefold()
    if fold_accents:
        text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return ''.join(c for c in text if c.isalnum())
