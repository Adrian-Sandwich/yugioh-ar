"""Read individual YGOJSON records; the downloaded aggregates failed CRC checks."""
import json
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'downloads/reference-assets/ygojson-individual-20260925.zip'
def records(kind):
    with zipfile.ZipFile(ARCHIVE) as z:
        for uid in json.loads(z.read(kind+'.json')):
            yield json.loads(z.read(f'{kind}/{uid}.json'))
