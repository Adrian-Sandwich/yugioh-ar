"""Download the requested public reference pages and selected research assets."""
import concurrent.futures
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "research/references-20260924"
JOBS = {
    "medium-draw.html": "https://medium.com/@hich.tala.phd/how-i-trained-a-model-to-detect-and-recognise-a-wide-range-of-yu-gi-oh-cards-6ea71da007fd",
    "towardsdatascience.html": "https://towardsdatascience.com/i-made-an-ai-to-recognize-over-10-000-yugioh-cards-26fc6aed1588/",
    "reddit-draw.html": "https://www.reddit.com/r/yugioh/comments/1avcvae/i_trained_a_deep_learning_model_to_detect_yugioh/",
    "roboflow.html": "https://universe.roboflow.com/unikl-ai/yu-gi-oh-card-detection",
    "roboflow-download.html": "https://universe.roboflow.com/unikl-ai/yu-gi-oh-card-detection/dataset/1/download/yolov8",
    "hf-draw.json": "https://huggingface.co/api/models/HichTala/draw?blobs=true",
    "hf-draw2.json": "https://huggingface.co/api/models/HichTala/draw2?blobs=true",
    "hf-retro-dataset.json": "https://huggingface.co/api/datasets/HichTala/tw-2008-ygo-dataset?blobs=true",
}


def fetch(job):
    name, url = job
    target = DEST / name
    result = {"file": str(target.relative_to(ROOT)), "url": url}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; reference-review/1.0)"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            result.update(status=response.status, final_url=response.url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        target.write_bytes(data)
    except Exception as exc:
        result["error"] = str(exc)
    print(name, result.get("status", result.get("error")), result.get("bytes", ""), flush=True)
    return result


if __name__ == "__main__":
    DEST.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch, JOBS.items()))
    (DEST / "downloads.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
