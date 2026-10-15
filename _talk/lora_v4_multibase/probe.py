"""Small-file download and CPU/meta architecture audit; no pretrained weight load."""
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
from atomic_state import write

ROOT = Path(__file__).resolve().parent
TALK = ROOT.parent
MODELS = [
    ('gemma4_26b_a4b', 'google/gemma-4-26B-A4B'),
    ('llmjp41_32b_a3b', 'llm-jp/llm-jp-4.1-32b-a3b-thinking'),
    ('xing40_29b_a4b', 'XingChen-AGI/Xing4.0-29B-A4B'),
]

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)

def main():
    from huggingface_hub import HfApi, hf_hub_download
    import torch
    import transformers
    import peft
    import bitsandbytes
    from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForMultimodalLM, BitsAndBytesConfig
    from transformers.integrations.bitsandbytes import replace_with_bnb_linear
    from accelerate import init_empty_weights

    environment = {
        'python': sys.executable, 'pid': os.getpid(),
        'packages': {m.__name__: m.__version__ for m in [torch, transformers, peft, bitsandbytes]},
        'package_files': {m.__name__: {'path': m.__file__, 'sha256': sha(m.__file__)} for m in [torch, transformers, peft, bitsandbytes]},
        'hip': torch.version.hip, 'gpu': torch.cuda.get_device_name(0),
        'gpu_total_bytes': torch.cuda.get_device_properties(0).total_memory,
        'gpu_free_bytes': torch.cuda.mem_get_info()[0],
        'pretrained_weights_loaded': False,
    }
    write(ROOT / 'audit/environment.json', environment)
    emit(environment)
    source_paths = [
        TALK / 'lora_v4_planner_talk/common.py',
        TALK / 'lora_v4_planner_talk/train.py',
        TALK / 'lora_v4_planner_talk/build_dataset.py',
        TALK / 'lora_v4_planner_talk/data/pilot_20261006c/manifest.json',
        TALK / 'memory_talk_lora_abc_v2/data/approved_candidates.jsonl',
        TALK / 'memory_talk_lora_abc_v2/scripts/prepare_memory_talk_abc_v2.py',
        TALK / 'memory_talk_lora_abc_v2/scripts/train_memory_talk_abc_v2_retry_20261004b.py',
        TALK / 'lora_v4_runtime_bc/runs/bc_consistency_10m_20261008/protocol.json',
    ]
    source_paths += sorted((TALK / 'lora_v4_planner_talk/data/pilot_20261006c').glob('*.jsonl'))
    write(ROOT / 'audit/reference_hashes.json', {str(p): sha(p) for p in source_paths})
    api = HfApi()
    results = []
    for key, repo in MODELS:
        out = ROOT / 'models' / key
        out.mkdir(parents=True, exist_ok=True)
        result = {'key': key, 'repo': repo, 'status': 'metadata', 'remote_code_executed': False}
        try:
            info = api.model_info(repo, files_metadata=True)
            result.update(revision=info.sha, gated=info.gated,
                weight_bytes=sum(s.size or 0 for s in info.siblings if s.rfilename.endswith('.safetensors')))
            write(out / 'repository.json', {**result, 'files': [{'name': s.rfilename, 'size': s.size} for s in info.siblings]})
            names = [s.rfilename for s in info.siblings if s.rfilename in {
                'config.json', 'generation_config.json', 'tokenizer.json', 'tokenizer_config.json',
                'tokenizer.model', 'spiece.model', 'vocab.json', 'merges.txt',
                'special_tokens_map.json', 'model.safetensors.index.json', 'README.md'
            } or s.rfilename.endswith('.py')]
            for name in names:
                emit({'event': 'small_file', 'model': key, 'file': name})
                hf_hub_download(repo, name, revision=info.sha, local_dir=out)
            result['small_file_hashes'] = {name: sha(out / name) for name in names}
            raw = json.loads((out / 'config.json').read_text(encoding='utf8'))
            result.update(model_type=raw['model_type'], architectures=raw.get('architectures'), auto_map=raw.get('auto_map'))
            if key == 'xing40_29b_a4b':
                result.update(status='remote_code_review_required',
                    reason='Custom architecture source saved; not executed before root review.')
            else:
                cfg = AutoConfig.from_pretrained(out, local_files_only=True, trust_remote_code=False)
                loader = AutoModelForMultimodalLM if key.startswith('gemma') else AutoModelForCausalLM
                with init_empty_weights(include_buffers=True):
                    model = loader.from_config(cfg, torch_dtype=torch.bfloat16, attn_implementation='sdpa')
                    model.tie_weights()
                original = {n: {'numel': p.numel(), 'shape': list(p.shape)} for n, p in model.named_parameters()}
                attention = [n for n, m in model.named_modules() if '.self_attn.' in n and n.rsplit('.', 1)[-1] in {'q_proj', 'k_proj', 'v_proj', 'o_proj'}]
                fused = [n for n in original if '.experts.' in n and not n.endswith('.weight')]
                quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                    bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
                # The reference excludes tied embedding/lm_head from bnb conversion.
                replace_with_bnb_linear(model, modules_to_not_convert=['lm_head'], quantization_config=quant)
                params = list(model.named_parameters())
                quantized = [(n, p) for n, p in params if isinstance(p, bitsandbytes.nn.Params4bit)]
                unquantized = [(n, p) for n, p in params if not isinstance(p, bitsandbytes.nn.Params4bit)]
                qn = sum(p.numel() for _, p in quantized)
                un = sum(p.numel() for _, p in unquantized)
                # prepare_model_for_kbit_training casts non-Params4bit BF16/FP16 to FP32.
                frozen_lower = qn * .5 + un * 4
                result.update(status='capacity_blocked' if frozen_lower > environment['gpu_total_bytes'] else 'meta_capacity_requires_training_peak_check',
                    parameter_count=sum(p['numel'] for p in original.values()),
                    bnb_quantized_parameter_count=qn, bnb_unquantized_parameter_count=un,
                    unquantized_expert_parameters=sum(original[n]['numel'] for n in fused),
                    fused_expert_parameter_names=fused, attention_module_names=attention,
                    frozen_weight_lower_bound_bytes=frozen_lower,
                    frozen_weight_lower_bound_GiB=round(frozen_lower / 2**30, 3),
                    quantization_scope='current reference bnb Linear replacement; no custom expert conversion',
                    lower_bound_excludes='quantization metadata, LoRA, optimizer, gradients, activations, load peak',
                    shape_inventory=original)
                del model
        except Exception as exc:
            result.update(status='probe_failed', error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        write(out / 'admission.json', result)
        results.append({k: v for k, v in result.items() if k not in {'shape_inventory', 'small_file_hashes', 'attention_module_names', 'fused_expert_parameter_names'}})
        emit(results[-1])
        write(ROOT / 'audit/model_admission.json', {'models': results, 'pretrained_weights_loaded': False})
    write(ROOT / 'state.json', {'status': 'preflight_review', 'training_started': False, 'models': results,
        'updated': time.strftime('%Y-%m-%dT%H:%M:%S%z')})

if __name__ == '__main__':
    main()
