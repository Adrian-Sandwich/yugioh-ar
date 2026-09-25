"""Run original external architectures with strict, weights-only checkpoint loading."""
import argparse,hashlib,importlib.util,json,sys,time
from pathlib import Path
import cv2,numpy as np,torch
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',choices=['docshrnet','mimo-shdocs'],required=True)
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--warmup',type=int,default=0)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--padding',choices=['reflect','upstream'],default='reflect',help='MIMO: pilot used reflect; upstream uses black padding, including 8 pixels on divisible sides')
    args=parser.parse_args()
    if args.threads<1 or args.warmup<0 or args.repeats<1:parser.error('Invalid timing options')
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    if args.device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA requested but unavailable; no silent CPU fallback')
    device=torch.device(args.device)
    if args.model=='docshrnet':
        spec=importlib.util.spec_from_file_location('external_docshrnet',ROOT/'repos/DocSHRNet/model/docshrnet.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        model=module.DocSHRNet(img_channel=3,width=32);path=ROOT/'downloads/glare-models/docshrnet.pth';key='model_state_dict'
    else:
        sys.path.insert(0,str(ROOT/'repos/SHDocs/model'))
        from models.MIMOUNet import build_net
        model=build_net('MIMO-UNetPlus');path=ROOT/'downloads/glare-models/mimo-shdocs.pkl';key='model'
    checkpoint=torch.load(path,map_location='cpu',weights_only=True)
    model.load_state_dict({k.removeprefix('module.'):v for k,v in checkpoint[key].items()},strict=True)
    del checkpoint
    model.to(device).eval();dest=OUT/'outputs'/args.model;dest.mkdir(parents=True,exist_ok=True)
    report={'model':args.model,'torch':torch.__version__,'device':str(device),'threads':args.threads,
            'warmup_per_shape':args.warmup,'repeats':args.repeats,'mimo_padding':args.padding,
            'timing_scope':'Forward pass only; transfers and PNG serialization excluded; CUDA synchronized',
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':[]}
    for row in json.loads((OUT/'samples.json').read_text())['samples']:
        image=cv2.imread(str(OUT/row['file']));h,w=image.shape[:2]
        x=torch.from_numpy(np.ascontiguousarray(image[:,:,::-1].transpose(2,0,1))).float()[None]/255
        if args.model=='mimo-shdocs':
            if args.padding=='reflect':x=torch.nn.functional.pad(x,(0,(-w)%8,0,(-h)%8),mode='reflect')
            else:x=torch.nn.functional.pad(x,(0,8-w%8,0,8-h%8))
        x=x.to(device)
        with torch.inference_mode():
            for _ in range(args.warmup):model(x)
            durations=[]
            for _ in range(args.repeats):
                if device.type=='cuda':torch.cuda.synchronize()
                start=time.perf_counter();y=model(x)
                if device.type=='cuda':torch.cuda.synchronize()
                durations.append((time.perf_counter()-start)*1000)
            if isinstance(y,(tuple,list)):y=y[-1]
            result=(y[0,:,:h,:w].clamp(0,1).permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)[:,:,::-1]
        ms=round(float(np.median(durations)),1)
        assert result.shape==image.shape and np.isfinite(result).all()
        cv2.imwrite(str(dest/f'{row["sample"]}.png'),result)
        report['rows'].append({'sample':row['sample'],'ms':ms,'all_ms':durations,'shape':list(result.shape)})
        (dest/'run.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(args.model,row['sample'],ms,'ms',flush=True)

if __name__=='__main__':main()
