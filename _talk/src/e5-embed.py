"""Local E5 inference. No remote calls, auto-downloads, or generated memory text."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'runtime/embedding-python'))
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


def local(value):
    target = (ROOT / value).resolve()
    target.relative_to(ROOT)
    return target


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    request = read_json(local(sys.argv[1]))
    target = local(sys.argv[2])
    model_dir = ROOT / 'models/multilingual-e5-small-onnx'
    profile = read_json(model_dir / 'profile.json')
    for item in profile['files']:
        if digest(model_dir / item['local']) != item['sha256']:
            raise ValueError('Model/tokenizer provenance mismatch')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model_dir / 'model_quantized.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=1, pad_token='<pad>')
    texts = request['texts']
    if request['kind'] not in ('query', 'passage'):
        raise ValueError('E5 prefix must be explicit')
    vectors = []
    counts = []
    started = time.monotonic()
    for offset in range(0, len(texts), 16):
        encoded = tokenizer.encode_batch([request['kind'] + ': ' + text for text in texts[offset:offset+16]])
        values = {
            'input_ids': np.array([e.ids for e in encoded], dtype=np.int64),
            'attention_mask': np.array([e.attention_mask for e in encoded], dtype=np.int64),
            'token_type_ids': np.array([e.type_ids for e in encoded], dtype=np.int64),
        }
        hidden = session.run(None, {i.name: values[i.name] for i in session.get_inputs()})[0]
        mask = values['attention_mask'][..., None]
        pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)
        pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
        vectors.extend(pooled.astype(np.float32).tolist())
        counts.extend(values['attention_mask'].sum(axis=1).tolist())
        if len(texts) > 16 and (offset // 16) % 16 == 0:
            print(json.dumps({'embedded': min(offset + 16, len(texts)), 'total': len(texts)}), flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {'kind': request['kind'], 'request_sha256': digest(local(sys.argv[1])), 'model_profile_sha256': digest(model_dir / 'profile.json'), 'dimensions': 384, 'vectors': vectors, 'token_counts': counts, 'seconds': time.monotonic() - started, 'provider': session.get_providers()}
    temp = target.with_suffix(target.suffix + '.partial')
    temp.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    temp.replace(target)
    print(json.dumps({'complete': len(texts), 'seconds': payload['seconds']}), flush=True)


if __name__ == '__main__':
    main()
