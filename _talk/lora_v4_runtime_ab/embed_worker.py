"""Persistent CPU E5, using exactly the existing profile and pooling."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'runtime/embedding-python'))
os.environ['TOKENIZERS_PARALLELISM']='false'
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

def main():
    directory=ROOT/'models/multilingual-e5-small-onnx'
    profile=json.loads((directory/'profile.json').read_text('utf8'))
    for f in profile['files']:
        assert hashlib.sha256((directory/f['local']).read_bytes()).hexdigest()==f['sha256']
    opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(directory/'model_quantized.onnx'),sess_options=opts,
                                providers=['CPUExecutionProvider'])
    tok=Tokenizer.from_file(str(directory/'tokenizer.json'))
    tok.enable_truncation(max_length=512);tok.enable_padding(pad_id=1,pad_token='<pad>')
    print(json.dumps({'ready':True,'pid':os.getpid(),'profile_sha256':hashlib.sha256((directory/'profile.json').read_bytes()).hexdigest()}),flush=True)
    for line in sys.stdin:
        req=json.loads(line)
        if req.get('stop'):break
        assert req['kind'] in ['query','passage']
        vectors=[]
        for offset in range(0,len(req['texts']),16):
            enc=tok.encode_batch([req['kind']+': '+s for s in req['texts'][offset:offset+16]])
            values={'input_ids':np.array([e.ids for e in enc],dtype=np.int64),
                    'attention_mask':np.array([e.attention_mask for e in enc],dtype=np.int64),
                    'token_type_ids':np.array([e.type_ids for e in enc],dtype=np.int64)}
            hidden=session.run(None,{i.name:values[i.name] for i in session.get_inputs()})[0]
            mask=values['attention_mask'][...,None]
            pooled=(hidden*mask).sum(axis=1)/mask.sum(axis=1)
            pooled/=np.linalg.norm(pooled,axis=1,keepdims=True).clip(min=1e-12)
            vectors.extend(pooled.astype(np.float32).tolist())
        print(json.dumps({'vectors':vectors}),flush=True)

if __name__=='__main__':main()
