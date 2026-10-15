"""v5 CPU context/state primitives used by the experimental Runtime; no production/TTS admission."""
import copy
import hashlib
from planner_policy import CONTRACT


def memory_reference(memory):
    if memory is None:
        return None
    if set(memory) != {'id', 'body'} or not all(isinstance(v, str) and v.strip() for v in memory.values()):
        raise ValueError('Canonical Memory requires id and original body')
    return {**copy.deepcopy(memory), 'sha256': hashlib.sha256(memory['body'].encode('utf-8')).hexdigest()}


def speech_context(initial, played, memory, plan=None):
    """Fact grounding is an explicit original Memory, independent of use_memory.

    Call only with a fact-checked Plan. The builder is not a factual checker.
    """
    recent = '\n'.join(p['text'] for p in played[-3:]) if played else initial
    ref = memory_reference(memory)
    if plan:
        CONTRACT['validate_plan'](plan, [ref['id']] if ref else [])
    body = ref['body'] if ref else 'なし'
    topic = plan['topic'] if plan else 'なし'
    flow = ''.join('- ' + beat + '\n' for beat in plan['flow']) if plan else 'なし\n'
    prompt = ('【情報の扱い】\n記憶は確定情報。直前の発話と話題・流れは会話の手掛かりで、'
              '具体的経験の新しい根拠にはしない。感想や自然な連想はそのまま話す。\n\n'
              '【記憶】\n' + body + '\n\n【話題】\n' + topic + '\n\n【流れ】\n' + flow +
              '\n【直前の発話】\n' + recent.rstrip('\n') + '\n')
    return {'prompt': prompt, 'recent': recent, 'grounding': ref,
            'mode': 'planned' if plan else 'grounded_planless', 'recent_utterances': min(3, len(played))}


class PlanStore:
    """Absolute expiry; fallback cannot renew a stale Plan. No conversation script."""
    def __init__(self):
        self.pending = self.active = self.last_valid = None
        self.invalidated_reason = None

    def stage(self, plan, memory, turn, fact_check, lifetime=3):
        if type(turn) is not int or type(lifetime) is not int or lifetime < 1:
            raise ValueError('Invalid Plan lifetime')
        ref = memory_reference(memory)
        CONTRACT['validate_plan'](plan, [ref['id']] if ref else [])
        if not fact_check or not fact_check.get('accepted'):
            raise ValueError('Fact validation required before pending Plan')
        self.pending = {'plan': copy.deepcopy(plan), 'grounding': ref,
                        'created_turn': turn, 'expires_before_turn': turn + lifetime,
                        'fact_check': copy.deepcopy(fact_check)}

    def commit(self):
        if self.pending is None:
            raise ValueError('No validated pending Plan')
        self.active = copy.deepcopy(self.pending)
        self.last_valid = copy.deepcopy(self.pending)
        self.pending = None
        self.invalidated_reason = None
        return copy.deepcopy(self.active)

    def invalidate(self, reason):
        self.active = self.pending = self.last_valid = None
        self.invalidated_reason = reason

    def fallback(self, turn, current_memory):
        self.pending = None
        bundle = self.last_valid
        if bundle is None or turn >= bundle['expires_before_turn']:
            return None
        if bundle['grounding'] != memory_reference(current_memory):
            return None
        self.active = copy.deepcopy(bundle)
        return copy.deepcopy(bundle)
