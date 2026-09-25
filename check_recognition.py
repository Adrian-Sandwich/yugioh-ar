"""Evaluate one reference on two independent captures and controlled negatives."""

import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import cv2
import numpy as np

from recognition import Recognizer
from camera_viewer import Server, Handler

ROOT = Path(__file__).resolve().parent


def main():
    recognizer = Recognizer()
    output = ROOT / "research/recognition"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for filename in ["carta-2026-09-25T04-15-11-032Z.jpg", "carta-2026-09-25T04-13-54-278Z.jpg"]:
        image = cv2.imread(str(ROOT / "data/captures" / filename))
        result = recognizer.detect(image)
        results.append({"sample": filename, "expected": True, **result})
        annotated = image.copy()
        for detection in result["detections"]:
            corners = np.int32(detection["corners"])
            cv2.polylines(annotated, [corners], True, (90, 255, 100), 4)
            cv2.putText(annotated, detection["name"], tuple(corners[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (90, 255, 100), 2)
        cv2.imwrite(str(output / filename), annotated)
    # The same capture with the card removed tests background leakage.
    entry = recognizer.references[0][0]
    background = cv2.imread(str(ROOT / "data/references" / entry["source"]))
    cv2.fillConvexPoly(background, np.int32([[435, 240], [940, 235], [995, 985], [443, 1015]]), (30, 30, 30))
    for name, image in [("same-background-card-masked", background), ("blank", np.zeros((720, 1280, 3), np.uint8))]:
        results.append({"sample": name, "expected": False, **recognizer.detect(image)})
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    assert all(bool(item["detections"]) == item["expected"] for item in results), "Recognition check failed"
    # Exercise the actual HTTP camera -> viewer -> recognition path with a
    # reserved capture. This is explicitly a simulated camera, not a live test.
    sample = (ROOT / "data/captures/carta-2026-09-25T04-13-54-278Z.jpg").read_bytes()

    class Camera(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(sample)))
            self.end_headers()
            self.wfile.write(sample)

        def log_message(self, *args):
            pass

    camera = ThreadingHTTPServer(("127.0.0.1", 0), Camera)
    viewer = Server(("127.0.0.1", 0), Handler)
    viewer.camera = f"http://127.0.0.1:{camera.server_port}"
    viewer.recognizer = recognizer
    viewer.recognition_lock = threading.Lock()
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (camera, viewer)]
    for thread in threads:
        thread.start()
    try:
        base = f"http://127.0.0.1:{viewer.server_port}"
        with urlopen(base + "/analyze", timeout=15) as response:
            result = json.load(response)
        assert result["detections"][0]["id"] == "blue-eyes-user-art-01"
        assert result["image"].startswith("data:image/jpeg;base64,")
        with urlopen(base + "/config") as response:
            assert json.load(response)["recognition"] is True
        with urlopen(base) as response:
            assert b"<canvas" in response.read()
        print("HTTP integration OK (simulated camera, held-out capture)")
    finally:
        for server in (viewer, camera):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
