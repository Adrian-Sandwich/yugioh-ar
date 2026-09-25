"""Fetch selected public weights/configs, pinned to Hugging Face revisions."""
import concurrent.futures
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "research/references-20260924"
OUT = ROOT / "downloads/reference-assets"
SELECTION = {
    "hf-draw.json": ("models", ["README.md", "yolo_ygo.pt"]),
    "hf-draw2.json": ("models", ["README.md", "draw_config.json", "config.json", "cardnames.json", "onnx/ygo_yolo.onnx", "onnx/vit_yugiscan_int8.onnx", "onnx/card_labels_yugiscan.json", "onnx/cardnames_onnx.json"]),
    "hf-retro-dataset.json": ("datasets", ["README.md", "club_yugioh_dataset.zip"]),
}


def download(job):
    repo, kind, revision, entry, folder = job
    name = entry["rfilename"]
    prefix = "datasets/" if kind == "datasets" else ""
    url = f"https://huggingface.co/{prefix}{repo}/resolve/{revision}/{name}"
    target = OUT / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"repo": repo, "revision": revision, "url": url, "file": str(target.relative_to(ROOT)), "expected_bytes": entry["size"]}
    partial = target.with_suffix(target.suffix + ".partial")
    try:
        digest = hashlib.sha256()
        count = 0
        started = time.monotonic()
        with urllib.request.urlopen(url, timeout=30) as response, partial.open("wb") as file:
            while chunk := response.read(1024 * 1024):
                file.write(chunk)
                digest.update(chunk)
                count += len(chunk)
                if time.monotonic() - started > 240:
                    raise TimeoutError("Download exceeded four minutes")
        if count != entry["size"]:
            raise ValueError(f"Expected {entry['size']} bytes, got {count}")
        expected_hash = entry.get("lfs", {}).get("sha256")
        if expected_hash and digest.hexdigest() != expected_hash:
            raise ValueError("SHA256 mismatch")
        partial.replace(target)
        record.update(status="downloaded", bytes=count, sha256=digest.hexdigest(), upstream_sha256_verified=bool(expected_hash))
    except Exception as exc:
        record.update(status="failed", error=str(exc))
    print(folder + "/" + name, record["status"], record.get("bytes", record.get("error")), flush=True)
    return record


if __name__ == "__main__":
    jobs = []
    for metadata, (kind, selected) in SELECTION.items():
        info = json.loads((META / metadata).read_text())
        for entry in info["siblings"]:
            if entry["rfilename"] in selected:
                jobs.append((info["id"], kind, info["sha"], entry, metadata.removeprefix("hf-").removesuffix(".json")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(download, jobs))
    (META / "assets.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
