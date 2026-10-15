"""Freeze existing materials and retokenize without changing training texts."""
import importlib.util
import json
import math
import shutil
import sys
import traceback
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from probe import ROOT, TALK, MODELS, sha, write, emit

def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line.strip()]

def jsonl(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(x, ensure_ascii=False, separators=(',', ':')) for x in data) + '\n', encoding='utf8')

class NativeSentencePiece:
    """Native model file; equivalent raw encoding, with character offsets."""
    def __init__(self, path):
        import sentencepiece
        self.sp = sentencepiece.SentencePieceProcessor(model_file=str(path))
    def encode(self, text, add_special_tokens=False):
        assert not add_special_tokens
        encoded = self.sp.encode(text, return_type='offset_mapping', return_bytes=False)
        offsets = list(encoded['offsets'])
        # Native protobuf offsets are UTF-8 bytes. This API returns character
        # offsets, but leading byte-fallback pieces can have zero-length spans.
        # Give all pieces of a character its full span, as fast tokenizers do,
        # so offset-based target masking keeps every byte of the first character.
        for i, (a, b) in enumerate(offsets):
            if a == b:
                for c, d in offsets[i + 1:]:
                    if c == a and d > a:
                        offsets[i] = (a, d)
                        break
                    if c > a:
                        break
        return SimpleNamespace(ids=encoded['ids'], offsets=offsets)
    def decode(self, ids, skip_special_tokens=True):
        return self.sp.decode(ids)

def tokenizer(key):
    from tokenizers import Tokenizer
    path = ROOT / 'models' / key
    if (path / 'tokenizer.json').exists():
        return Tokenizer.from_file(str(path / 'tokenizer.json'))
    return NativeSentencePiece(path / 'tokenizer.model')

def freeze():
    expected = json.loads((ROOT / 'audit/reference_hashes.json').read_text(encoding='utf8'))
    assert all(sha(p) == digest for p, digest in expected.items())
    out = ROOT / 'reference'
    out.mkdir(exist_ok=True)
    approved = TALK / 'memory_talk_lora_abc_v2/data/approved_candidates.jsonl'
    data = rows(approved)
    assert len(data) == len({r['sample_id'] for r in data}) == 582
    groups = json.loads((TALK / 'memory_talk_lora_abc_v2/configs/input_manifest.json').read_text(encoding='utf8'))['authoritative_group_split']
    byid = {r['sample_id']: r for r in data}
    counts = Counter()
    donor_count = 0
    for r in data:
        split = groups[r['source']['group_id']]
        assert r['source']['derived_split'] == split
        assert r['input_text'].endswith('\n') and not r['input_text'].endswith('\n\n')
        assert r['context'] and r['target'] and r['memory'] in r['input_text']
        assert sha(r['source']['path']) == r['source']['sha256']
        counts[(split, r['sample_type'])] += 1
        if r['sample_type'] == 'IRREL':
            donor = r['donor']
            did = donor.get('sample_id') or donor.get('donor_sample_id') or donor.get('sample')
            if did not in byid:
                raise ValueError('Unknown donor key: ' + repr(donor))
            source = byid[did]
            assert groups[source['source']['group_id']] == split
            assert source['memory'] == r['memory']
            donor_count += 1
    assert counts == Counter({(s, c): n for s, n in [('train', 106), ('validation', 40), ('test', 48)] for c in ['REL', 'NONE', 'IRREL']})
    shutil.copy2(approved, out / 'approved_candidates.jsonl')
    shutil.copy2(TALK / 'memory_talk_lora_abc_v2/configs/input_manifest.json', out / 'abc_input_manifest.json')
    pilot = TALK / 'lora_v4_planner_talk/data/pilot_20261006c'
    shutil.copytree(pilot, out / 'pilot_20261006c', dirs_exist_ok=True)
    for role in ['planner', 'talk']:
        for split in ['train', 'validation', 'test']:
            original = rows(pilot / f'{role}_{split}.jsonl')
            text_only = [{k: v for k, v in r.items() if k not in {
                'input_ids', 'labels', 'target_start', 'target_token_count', 'context_cut_tokens', 'full_target_token_sha256'}} for r in original]
            jsonl(out / f'{role}_{split}_text.jsonl', text_only)
    write(ROOT / 'audit/source_data_audit.json', {'status': 'pass', 'adopted': 582,
        'split': {'train': 318, 'validation': 120, 'test': 144}, 'donors_checked': donor_count,
        'source_files_and_hashes_checked': True, 'cross_split_donors': 0,
        'raw_text_changed': False, 'reference_hashes': expected})
    return data, groups

def build_abc(key, tok, data, groups):
    windows = {s: [] for s in ['train', 'validation', 'test']}
    boundaries = []
    total = 0
    for r in data:
        prefix = r['input_text']
        boundary = len(prefix)
        full = tok.encode(prefix + r['target'], add_special_tokens=False)
        p = tok.encode(prefix, add_special_tokens=False)
        # Standalone Unigram encoding inserts a dummy initial whitespace token;
        # it must not be injected after an actual prompt. Use the exact joined
        # sequence and its character offsets, as the existing v4 encode does.
        start = len(p.ids)
        if any(a < boundary < b for a, b in full.offsets) or full.ids[:start] != p.ids:
            boundaries.append(r['sample_id'])
            continue
        memory_start = prefix.find(r['memory'])
        context_start = prefix.find(r['context'], memory_start + len(r['memory']))
        assert context_start >= 0
        mstart = next(i for i, (_, b) in enumerate(full.offsets) if b > context_start)
        if any(a < context_start < b for a, b in full.offsets):
            raise ValueError('Static/context token boundary changed: ' + r['sample_id'])
        static = full.ids[:mstart]
        context = full.ids[mstart:start]
        assert len(static) < 1024
        ids = full.ids[start:]
        total += len(ids)
        split = groups[r['source']['group_id']]
        for ordinal, start in enumerate(range(0, len(ids), min(160, 1024 - len(static)))):
            chunk = ids[start:start + min(160, 1024 - len(static))]
            budget = 1024 - len(static) - len(chunk)
            history = (context + ids[:start])[-budget:] if budget else []
            labels = [-100] * (len(static) + len(history)) + chunk
            windows[split].append({'window_id': f"{r['sample_id']}:{ordinal:04d}",
                'sample_id': r['sample_id'], 'source_id': r['source']['source_id'],
                'source_group_id': r['source']['group_id'], 'split': split,
                'input_ids': static + history + chunk, 'labels': labels,
                'target_start': len(static) + len(history), 'target_token_count': len(chunk),
                'input_text': prefix, 'target_text': r['target'],
                'target_start_token': start, 'target_end_token': start + len(chunk),
                'context_cut_tokens': max(0, len(context) + start - budget)})
    if boundaries:
        write(ROOT / 'data' / key / 'abc_boundary_failures.json', {'status': 'failed',
            'reason': 'Exact reference separate prefix/target tokenization is not additive with this tokenizer.',
            'sample_ids': boundaries, 'count': len(boundaries), 'rows_skipped_for_training': False})
        raise ValueError(f'{len(boundaries)} ABC tokenizer boundary failures; no samples may be silently omitted')
    assert sum(r['target_token_count'] for part in windows.values() for r in part) == total
    for split, part in windows.items():
        part.sort(key=lambda x: (x['source_id'], x['sample_id'], x['window_id']))
        jsonl(ROOT / 'data' / key / f'v3_{split}.jsonl', part)
    return {'windows': {s: len(v) for s, v in windows.items()}, 'target_tokens': total,
        'target_missing': 0, 'target_overlap': 0, 'updates': math.ceil(len(windows['train']) / 8)}

def build_pilot(key, tok):
    sys.path.insert(0, str(TALK / 'lora_v4_planner_talk'))
    from build_dataset import encode
    source = ROOT / 'reference/pilot_20261006c'
    example = {r['id']: r for r in rows(source / 'examples.jsonl')}
    result = {}
    for role in ['planner', 'talk']:
        result[role] = {}
        for split in ['train', 'validation', 'test']:
            output = []
            for old in rows(source / f'{role}_{split}.jsonl'):
                identity = old['window_id'].removesuffix('-PLAN')
                if old.get('mode') == 'PLAN-':
                    identity = identity.replace('-FALLBACK', '-REL')
                recent = example[identity]['planner_input']['recent']
                rec = encode(tok, old['prompt'], old['target'], recent)
                meta = {k: v for k, v in old.items() if k not in rec}
                output.append({**meta, **rec})
            assert len({r['window_id'] for r in output}) == len(output)
            jsonl(ROOT / 'data' / key / f'{role}_{split}.jsonl', output)
            result[role][split] = len(output)
        result[role]['updates'] = math.ceil(result[role]['train'] / 8) * (5 if role == 'planner' else 3)
    return result

def main():
    prior = ROOT / 'audit/data_preflight.json'
    if prior.exists():
        backup = ROOT / 'audit' / ('data_preflight_before_' + time.strftime('%Y%m%d_%H%M%S'))
        backup.mkdir(exist_ok=False)
        shutil.copy2(prior, backup / prior.name)
        for key, _ in MODELS:
            model_dir = ROOT / 'data' / key
            for name in ['manifest.json', 'abc_boundary_failures.json']:
                if (model_dir / name).exists():
                    shutil.copy2(model_dir / name, backup / (key + '_' + name))
    data, groups = freeze()
    reports = []
    for key, _ in MODELS:
        result = {'model': key, 'text_changes': False, 'EOS_appended': False, 'chat_template_added': False}
        tok = tokenizer(key)
        for stage, func in [('v3', lambda: build_abc(key, tok, data, groups)), ('v4', lambda: build_pilot(key, tok))]:
            try:
                result[stage] = {'status': 'pass', **func()}
            except Exception as exc:
                result[stage] = {'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc()}
        write(ROOT / 'data' / key / 'manifest.json', result)
        reports.append(result)
        emit(result)
    write(ROOT / 'audit/data_preflight.json', {'models': reports, 'GPU_loaded': False})

if __name__ == '__main__':
    main()
