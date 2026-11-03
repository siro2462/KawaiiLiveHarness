"""Copy an isolated, bounded harness and derive candidate inputs mechanically."""
import ast
import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
TALK = OUT.parents[2]
BASE = OUT.parent / 'memory_db_v2_full_surface3_20261103_v1'
MATERIAL = OUT.parent / 'v_memory_structure_20261103_v1'
SRC = OUT / 'executed_source'


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    assert not any((OUT / x).exists() for x in ['protocol.json', 'launch.json', 'launch_intent.json', 'controller.json'])
    assert read(MATERIAL / 'completion.json')['status'] == 'candidate_design_complete_surface_untested'
    overrides = {p.name for p in SRC.glob('*') if p.is_file()}
    for file in (BASE / 'executed_source').glob('*'):
        if file.is_file() and file.name not in overrides:
            shutil.copyfile(file, SRC / file.name)
    controller = SRC / 'run_cpu.py'
    old_assert = b"assert len(records)==d.n==cfg['max_calls']==11 and len(groups)==3"
    new_assert = b"assert len(records)==d.n==cfg['max_calls']==len(schedule) and len(groups)==3"
    data = controller.read_bytes()
    assert data.count(old_assert) == 1
    controller.write_bytes(data.replace(old_assert, new_assert))
    # Archive only; original v2 presentation ignores these style blocks.
    for name in ['grouping_style.txt', 'reaction_style.txt', 'unit_instruction.txt', 'listener_style.txt', 'meaning_legend.json']:
        shutil.copyfile(BASE / name, OUT / name)
    ref = OUT / 'reference'
    for file in (BASE / 'reference/v5/memory_db').rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.suffix in ['.py', '.sql', '.json', '.md']:
            target = ref / file.relative_to(BASE / 'reference')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
    for name in ['candidates.json', 'normalized_candidates.json', 'source_freeze.json']:
        shutil.copyfile(MATERIAL / name, OUT / ('source_' + name))
    (OUT / 'authored_sources').mkdir()
    for file in (MATERIAL / 'authored_sources').glob('*.json'):
        shutil.copyfile(file, OUT / 'authored_sources' / file.name)
    candidates = read(OUT / 'source_candidates.json')
    authored = {x['document']['記憶']['記憶ID']: read(OUT / x['authored_source']) for x in candidates}
    sys.path[:0] = [str(SRC), str(ref)]
    from candidate_projection import make_snapshot
    from v5.memory_db.projection import project_episode
    from v5.memory_db.selector_adapter import select_episode
    from v5.memory_db.surface import render_surface
    snapshot, normalized = make_snapshot(candidates, authored)
    assert normalized == read(OUT / 'source_normalized_candidates.json')
    assert all(sha(OUT / name) == value for name, value in read(OUT / 'source_source_freeze.json').items())
    write(ref / 'validation_snapshot.json', snapshot)
    samples = []
    for revision in snapshot['episodes']:
        projected = project_episode(snapshot, revision['revision_id'])
        selected = select_episode(projected, backend='rhythm')
        samples.append(dict(id=revision['external_id'], source_id=revision['external_id'], title=revision['title'],
                            category='new_root_authored_fiction', initial_history=[], revision=revision,
                            db_sample=projected, selection=selected, steps=selected['steps'],
                            surface=render_surface(projected, selected), review_status='unreviewed'))
    assert len(samples) == 3 and all(s['steps'] for s in samples)
    selections = {s['id']: s['selection'] for s in samples}
    schedule = [dict(unit_key=s['id'] + f':G{i+1:02}', sample_id=s['id'], unit_index=i+1)
                for s in samples for i in range((len(s['steps']) + 3) // 4)]
    write(OUT / 'samples.json', samples)
    write(OUT / 'cpu_selections.json', selections)
    write(OUT / 'unit_schedule.json', schedule)
    for name in ['requests', 'turns', 'deliveries', 'cpu_temp']:
        (OUT / name).mkdir(exist_ok=False)
    oldcfg = read(BASE / 'protocol.json')
    cfg = copy.deepcopy(oldcfg)
    cfg.update(experiment=OUT.name, created_jst='2026-11-03', source_run=str(BASE),
               baseline_run=None, memory_source_run=str(MATERIAL), memory_db_source_run=None,
               max_calls=len(schedule), max_new_model_calls=len(schedule), prefix_reuse=[],
               snapshot_id=snapshot['snapshot_id'], selected_sample_ids=[s['id'] for s in samples],
               selected_operations=sum(len(s['steps']) for s in samples),
               selected_deferred=sum(len(s['selection']['deferred_nodes']) for s in samples),
               selected_review_status={s['id']: 'unreviewed_root_authored_candidate' for s in samples},
               source_review_status={'standalone_fictional_candidates': 3, 'persistent_db_registration': 0},
               only_manipulated_variable='new fixed candidate Memory; same existing CPU rhythm selector/full-v2 group4 presentation and model settings',
               unit_counts={s['id']: (len(s['steps']) + 3) // 4 for s in samples},
               comparison_scope='source Memory / automatically selected operations / new actual speech; no paired old-output baseline',
               history_mode='independent empty initial histories; fixed CPU-selected groups up to4; adopted actual text last2/800',
               generation_retry_policy='no quality retry, no manual operation/order supplementation',
               source_text_rewrite=False, default_runtime_changed=False)
    # Preserve prior execution dependencies and add the new immutable overlay.
    cfg['frozen_files'] = copy.deepcopy(oldcfg['frozen_files'])
    static = [OUT / x for x in ['samples.json', 'cpu_selections.json', 'unit_schedule.json',
              'source_candidates.json', 'source_normalized_candidates.json', 'source_source_freeze.json',
              'grouping_style.txt', 'reaction_style.txt', 'unit_instruction.txt', 'listener_style.txt', 'meaning_legend.json']]
    static += [p for root in [SRC, ref, OUT / 'authored_sources'] for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for file in static:
        cfg['frozen_files'][str(file)] = sha(file)
    for name in ['candidates.json', 'normalized_candidates.json', 'source_freeze.json', 'technical_audit.json', 'root_review.json']:
        cfg['frozen_files'][str(MATERIAL / name)] = sha(MATERIAL / name)
    manifest = read(BASE / 'setup_manifest.json')
    unchanged = {file.name: sha(file) for file in SRC.glob('*') if file.is_file()
                 and (BASE / 'executed_source' / file.name).exists()
                 and sha(file) == sha(BASE / 'executed_source' / file.name)}
    write(OUT / 'setup_manifest.json', dict(unchanged_core=unchanged, source_run=str(BASE),
          dependency_source=str(BASE / 'executed_source/token_journal.py'), dependency_sha256=sha(SRC / 'token_journal.py'),
          original_v2_sources=manifest['original_v2_sources'], source_db_files=manifest['source_db_files'],
          source_material_files={str(MATERIAL / name): sha(MATERIAL / name) for name in ['candidates.json', 'normalized_candidates.json', 'source_freeze.json']},
          samples_sha256=sha(OUT / 'samples.json'), reference_code_source=str(BASE / 'reference/v5/memory_db'),
          source_material_unedited=True, persistent_db_registration=0))
    for file in SRC.glob('*.py'):
        ast.parse(file.read_text(encoding='utf-8-sig'))
    write(OUT / 'protocol.json', cfg)
    print(json.dumps(dict(status='prepared_data_only', samples=len(samples), operations=cfg['selected_operations'],
                         deferred=cfg['selected_deferred'], max_surface_calls=len(schedule),
                         groups=cfg['unit_counts'], model_calls=0, normalized_exact=True), ensure_ascii=False))


if __name__ == '__main__':
    main()
