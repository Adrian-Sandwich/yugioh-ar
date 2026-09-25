"""Read-only environment inventory for the next computer."""
import argparse,importlib.metadata,json,platform,shutil,sqlite3,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--torch',action='store_true');a=p.parse_args()
    versions={}
    for name in ('ultralytics','torch','torchvision','onnxruntime','opencv-python','rapidocr'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    paths=['data/registry/registry.sqlite','data/catalog/catalog.sqlite','data/pilot/catalog.json','data/pilot/embeddings.npy',
        'downloads/reference-assets/draw2/onnx/ygo_yolo.onnx','data/models/vit_small_features.onnx',
        'downloads/reference-assets/yolo11-pose/yolo11n-pose.pt','downloads/reference-assets/yolo11-pose/yolo11s-pose.pt']
    report={'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),'sqlite':sqlite3.sqlite_version,
            'packages_current_environment':versions,'free_disk_gb':round(shutil.disk_usage(ROOT).free/1e9,1),
            'required_assets':{name:(ROOT/name).exists() for name in paths}}
    if a.torch:
        import torch
        report['torch_runtime']={'version':torch.__version__,'cuda_available':torch.cuda.is_available(),
            'cuda_version':torch.version.cuda,'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
