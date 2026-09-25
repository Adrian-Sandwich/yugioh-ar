"""YOLO11 n/s baseline with native C2PSA and four semantic card corners."""
import argparse,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'.runtime/ultralytics-pose'))
# Ultralytics falls back to <cwd>/Ultralytics when this directory does not exist yet.
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.runtime/matplotlib-pose'))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--size',choices=['n','s'],default='n')
    p.add_argument('--data',type=Path,default=ROOT/'data/pose/bootstrap-v1/dataset.yaml')
    p.add_argument('--epochs',type=int,default=100);p.add_argument('--imgsz',type=int,default=640)
    p.add_argument('--batch',type=int,default=8);p.add_argument('--device',default='cpu')
    p.add_argument('--smoke',action='store_true',help='1 epoch, 320px, 2/image batch; plumbing only')
    a=p.parse_args()
    import torch,yaml,ultralytics
    from ultralytics import YOLO
    torch.set_num_threads(2)
    data_path=a.data.resolve();data=yaml.safe_load(data_path.read_text(encoding='utf-8'))
    if data.get('kpt_shape')!=[4,3]:raise ValueError('Expected exactly four corners with visibility flags')
    data['path']=str(data_path.parent)
    configs=ROOT/'.runtime/pose-configs';configs.mkdir(parents=True,exist_ok=True)
    resolved=configs/f'{data_path.parent.name}.yaml';resolved.write_text(yaml.safe_dump(data),encoding='utf-8')
    weights=ROOT/'downloads/reference-assets/yolo11-pose'/f'yolo11{a.size}-pose.pt'
    if not weights.exists():raise FileNotFoundError(f'Download official checkpoint first: {weights}')
    model=YOLO(str(weights))
    run_name=f'yolo11{a.size}-'+('smoke' if a.smoke else 'baseline')
    result=model.train(data=str(resolved),epochs=1 if a.smoke else a.epochs,
        imgsz=320 if a.smoke else a.imgsz,batch=2 if a.smoke else a.batch,
        device=a.device,workers=0,seed=1104,deterministic=True,optimizer='AdamW',lr0=.001,
        project=str(ROOT/'research/yolo11_pose/runs'),name=run_name,exist_ok=False,
        pretrained=True,amp=False if a.device=='cpu' else True,plots=True,
        fliplr=0.,flipud=0.,mosaic=0.,mixup=0.,copy_paste=0.,degrees=0.,translate=0.,scale=0.,
        shear=0.,perspective=0.,save=True,val=True)
    run=Path(model.trainer.save_dir)
    metadata={'ultralytics':ultralytics.__version__,'torch':torch.__version__,'device':a.device,
        'dataset':str(data_path),'smoke_only':a.smoke,'keypoint_order':['TL','TR','BR','BL'],
        'attention':'native C2PSA; no extra attention added','deployable':False,
        'reason':'Needs reviewed real-scene validation; synthetic metrics are not deployment evidence.'}
    (run/'experiment.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps({'run':str(run),'smoke_only':a.smoke,'metrics':result.results_dict}))


if __name__=='__main__':main()
