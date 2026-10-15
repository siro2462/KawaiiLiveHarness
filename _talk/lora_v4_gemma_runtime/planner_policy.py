"""Harness v5: whole-output parsing and bounded retry. No substring rescue."""
import ast
import copy
import json
from pathlib import Path
from generation_errors import audit_error, classify

ROOT = Path(__file__).resolve().parent
TALK = ROOT.parent
CONTRACT_PATH = TALK / 'lora_v4_planner_talk/contracts.py'


def load_pure_contracts():
    namespace = {'json': json, 'PLAN_KEYS': {'use_memory', 'memory_id', 'topic', 'flow'},
                 'INPUT_KEYS': {'recent', 'current_state', 'memory_candidates', 'previous_plan'}}
    for path, names in [(CONTRACT_PATH, {'validate_input', 'planner_prompt', 'parse_plan', 'validate_plan'})]:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        assert {node.name for node in body} == names
        exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


CONTRACT = load_pure_contracts()
SCHEMA_INSTRUCTION = (
    '出力はPlanのJSONを1個だけ。説明文や見出しは付けない。'
    'キーはuse_memory、memory_id、topic、flowの4つを全て含め、他のキーは使わない。'
    'use_memoryはtrueかfalse。trueならmemory_idは候補のidをそのまま使う。'
    'falseでもmemory_idを省略せずnullにする。topicは空でない文字列。'
    'flowは空でない文字列を2〜4個並べた配列。\n\n'
)


def planner_prompt(inp):
    return SCHEMA_INSTRUCTION + CONTRACT['planner_prompt'](inp)


def parse_plan(raw, ids):
    if not isinstance(raw, str):
        raise ValueError('Plan output must be a string')
    return CONTRACT['parse_plan'](raw, ids)


def decoding_schema(ids):
    """Mask supported schema; boolean/ID relation is checked at adoption.

    LMFE 0.11.3 cannot correctly enforce boolean const. No dependency patch.
    """
    memory_id = {'type': 'null'} if not ids else {'anyOf': [
        {'type': 'string', 'enum': list(ids)}, {'type': 'null'}]}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['use_memory', 'memory_id', 'topic', 'flow'],
            'properties': {'use_memory': {'type': 'boolean'}, 'memory_id': memory_id,
                           'topic': {'type': 'string', 'minLength': 1},
                           'flow': {'type': 'array', 'minItems': 2, 'maxItems': 4,
                                    'items': {'type': 'string', 'minLength': 1}}}}


def adoption_schema(ids):
    schema = decoding_schema(ids)
    branches = [{'properties': {'use_memory': {'const': False}, 'memory_id': {'type': 'null'}}}]
    if ids:
        branches.append({'properties': {'use_memory': {'const': True},
                                        'memory_id': {'type': 'string', 'enum': list(ids)}}})
    schema['oneOf'] = branches
    return schema


def validation_feedback(raw, ids):
    try:
        parse_plan(raw, ids)
        return ''
    except (ValueError, TypeError, KeyError) as exc:
        error = str(exc)
    return ('前の出力はPlanの形式を満たさなかった: ' + error +
            '。4キーを含むJSONを1個だけ、元の入力から出し直す。')


def obtain_plan(generate, inp, fact_check=None):
    """At most two calls, separate schema/fact gates; no fact check for format probe."""
    CONTRACT['validate_input'](inp)
    current = copy.deepcopy(inp)
    ids = [m['id'] for m in inp['memory_candidates']]
    attempts = []
    for retry in range(2):
        prompt = planner_prompt(current)
        try:
            record = copy.deepcopy(generate(prompt, current['recent'], retry))
        except Exception as exc:
            error = audit_error(exc, prompt, current['recent'], ids)
            record = {'text':None, 'input_text':prompt, 'schema_valid':False,
                      'strict_schema_error':None, 'substring_rescue':False,
                      'planner_retry':retry, 'generation_error':error,
                      'factual_validation':{'status':'not_checked'}}
            attempts.append(record)
            if classify(exc) is None:
                exc.v5_generation_attempts=copy.deepcopy(attempts)
                raise
            if not error['retry'] or retry==1:break
            if error['action']=='shrink_recent_only':
                current['recent']=current['recent'][len(current['recent'])//2:]
            current['current_state']['plan_validation_feedback']='生成失敗: '+error['code']+'。元Memoryを変えずJSONを1個だけ出す。'
            continue
        selected = None
        try:
            selected = parse_plan(record['text'], ids)
            strict_error = None
        except (ValueError, TypeError, KeyError) as exc:
            strict_error = str(exc)
        check = fact_check(selected, inp) if selected is not None and fact_check else None
        record.update(schema_valid=selected is not None, strict_schema_error=strict_error,
                      substring_rescue=False, planner_retry=retry,
                      factual_validation=check if check is not None else {'status': 'not_checked'})
        if check is not None and not check['accepted']:
            selected = None
        attempts.append(record)
        if selected is not None:
            return selected, attempts
        if retry == 0:
            current['current_state']['plan_validation_feedback'] = (
                validation_feedback(record['text'], ids) if strict_error else check['feedback'])
    return None, attempts
