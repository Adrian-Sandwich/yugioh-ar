"""Small reproducible domain-transfer probe; not a statistical accuracy benchmark.
Run from project root: .venv-eval/Scripts/python.exe research/digit-references/evaluate_yolo.py
"""
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from passcode_ocr import REGIONS, NumberReader, region

OUT = Path(__file__).resolve().parent
MODELS = ROOT / 'repos/yolov8-digits-detection/models'
QA = ROOT / 'research/qa/passcode'


def main():
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    sessions = {name: ort.InferenceSession(str(MODELS / (name + '.onnx')),
                options, providers=['CPUExecutionProvider'])
                for name in ('preprocessing', 'yolo', 'nms', 'postprocessing')}

    def run(name, inputs):
        session = sessions[name]
        return dict(zip([o.name for o in session.get_outputs()], session.run(None, inputs)))

    _, _, height, width = sessions['yolo'].get_inputs()[0].shape
    dims = {'input_h': np.array([height], np.int32), 'input_w': np.array([width], np.int32)}

    def detect(image):
        start = time.perf_counter()
        pre = run('preprocessing', dict(image=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
                  fill_value=np.array([114], np.uint8), **dims))
        yolo = run('yolo', {'images': pre['preprocessed_img'][None].astype(np.float32)})
        selected = run('nms', dict(output0=yolo['output0'],
                       max_output_boxes_per_class=np.array([100], np.int32),
                       iou_threshold=np.array([.7], np.float32),
                       score_threshold=np.array([.25], np.float32)))
        boxes = run('postprocessing', dict(boxes_xywh=selected['selected_boxes_xywh'],
                    padding_tlbr=pre['padding_tlbr'], **dims))['boxes_xywhn']
        found = [{'digit': int(c), 'score': round(float(s), 4), 'xywhn': b.tolist()}
                 for b, c, s in zip(boxes.reshape(-1, 4),
                     selected['selected_class_ids'].reshape(-1), selected['selected_class_scores'].reshape(-1))]
        found.sort(key=lambda x: x['xywhn'][0])
        return {'detections': found, 'x_order_raw': ''.join(str(x['digit']) for x in found),
                'ms': round((time.perf_counter()-start)*1000, 1)}

    rectified = cv2.imread(str(QA / 'real-rectified.png'))
    cases = [('real-tight', region(rectified, REGIONS['tight']), '89631139'),
             ('real-wide', cv2.imread(str(QA / 'real-passcode.png')), '89631139'),
             ('live-blurry-unlabelled', cv2.imread(str(QA / 'live-blue-crop.png')), None),
             ('blank', np.full((40, 240, 3), 255, np.uint8), ''),
             ('upstream-annotated-demo', cv2.imread(str(ROOT / 'repos/yolov8-digits-detection/img/image_prediction.png')), None)]
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 32)
    printed = Image.new('RGB', (190, 48), 'white')
    ImageDraw.Draw(printed).text((5, 2), '89631139', font=font, fill='black')
    for h in (12, 20, 48):
        sample = cv2.resize(np.array(printed), (round(190*h/48), h), interpolation=cv2.INTER_AREA)
        cases.append((f'printed-line-height-{h}', sample, '89631139'))
    rows = []
    for name, image, truth in cases:
        if image is None:
            raise FileNotFoundError(name)
        cv2.imwrite(str(OUT / (name + '.png')), image)
        row = {'case': name, 'shape': list(image.shape), 'expected': truth, **detect(image)}
        row['exact_raw_match'] = row['x_order_raw'] == truth if truth is not None else None
        rows.append(row)
    reader = NumberReader()
    start = time.perf_counter()
    best, ambiguous, observations = reader.read(rectified)
    baseline = {'case': 'real-full-rectified', 'best': best, 'ambiguous': ambiguous,
                'observations': observations, 'ms': round((time.perf_counter()-start)*1000, 1)}
    report = {'note': 'Exploratory probe only. Raw x-order can include duplicate or off-line detections. '
                       'Upstream demo is already annotated and only a pipeline sanity check. '
                       'Live blurred crop has no independently transcribed ground truth.',
              'model_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in MODELS.glob('*.onnx')},
              'yolo': rows, 'rapidocr_baseline': baseline}
    (OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'yolo': [{k:v for k,v in row.items() if k != 'detections'} for row in rows],
                      'rapidocr': baseline['best']}, indent=2))


if __name__ == '__main__':
    main()
