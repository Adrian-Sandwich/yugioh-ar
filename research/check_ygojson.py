"""Inspect the downloaded database and cross-reference DRAW2 Small labels."""
import hashlib
import json
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research/references-20260924"
archive = ROOT / "downloads/reference-assets/ygojson-aggregate.zip"
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    cards = json.loads(z.read("cards.json"))
    metadata = json.loads(z.read("meta.json"))
index = defaultdict(dict)
for card in cards:
    ids = list(card.get("passwords", []))
    ids += [image.get("password") for image in card.get("images", [])]
    ids.append(card.get("externalIDs", {}).get("ygoprodeck", {}).get("id"))
    for identifier in ids:
        if identifier is not None and str(identifier).isdigit():
            index[str(int(identifier))][card["id"]] = card
labels = json.loads((ROOT / "downloads/reference-assets/draw2/onnx/card_labels_yugiscan.json").read_text(encoding="utf-8"))
mapped, unmatched, ambiguous = {}, {}, {}
for label_index, label in labels.items():
    key = label.rsplit("-", 1)[-1]
    candidates = index.get(str(int(key)) if key.isdigit() else key, {})
    if len(candidates) == 1:
        card = next(iter(candidates.values()))
        mapped[label_index] = {"label": label, "model_card_id": key, "ygojson_uuid": card["id"],
                               "name_es": card.get("text", {}).get("es", {}).get("name"),
                               "name_en": card.get("text", {}).get("en", {}).get("name")}
    elif candidates:
        ambiguous[label_index] = {"label": label, "candidates": list(candidates)}
    else:
        unmatched[label_index] = label
report = {"archive_url": "https://github.com/iconmaster5326/YGOJSON/releases/download/v1/aggregate.zip",
          "archive_bytes": archive.stat().st_size, "sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(),
          "repo_commit": subprocess.check_output(["git", "-C", str(ROOT / "repos/ygojson"), "rev-parse", "HEAD"], text=True).strip(),
          "dataset_metadata": metadata, "cards": len(cards), "labels": len(labels),
          "matched": len(mapped), "unmatched": unmatched, "ambiguous": ambiguous,
          "matched_with_spanish_name": sum(bool(item["name_es"]) for item in mapped.values())}
(OUT / "ygojson-inspection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "draw2-small-ygojson-map.json").write_text(json.dumps(mapped, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({**{key: report[key] for key in ["cards", "labels", "matched", "matched_with_spanish_name", "archive_bytes", "dataset_metadata"]},
                  "unmatched": len(unmatched), "ambiguous": len(ambiguous)}, ensure_ascii=False, indent=2))
print("Blue-Eyes:", next(value for value in mapped.values() if value["model_card_id"] == "89631139"))
