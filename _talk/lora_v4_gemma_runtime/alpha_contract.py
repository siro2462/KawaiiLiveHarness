"""Independent upstream proposal contract; no Planner Flow or utterance generation."""
import copy


def validate_proposal(proposal, bank):
    if set(proposal) != {'version', 'decision', 'trigger', 'memory_ids', 'topic_hint'}:
        raise ValueError('Alpha proposes recall only; no Flow or speech fields')
    if proposal['version'] != 'alpha.v0.1' or proposal['decision'] not in {'propose', 'wait'}:
        raise ValueError('Alpha version or decision')
    trigger = proposal['trigger']
    if not isinstance(trigger, dict) or set(trigger) != {'kind', 'event_id'}:
        raise ValueError('Trigger fields')
    if trigger['kind'] not in {'external_event', 'silence', 'recent_topic'}:
        raise ValueError('Unknown trigger')
    if not isinstance(trigger['event_id'], str) or not trigger['event_id'].strip():
        raise ValueError('Missing trigger provenance')
    ids = proposal['memory_ids']
    if not isinstance(ids, list) or any(not isinstance(x, str) or x not in bank for x in ids):
        raise ValueError('Unknown source Memory')
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate Memory IDs')
    if proposal['decision'] == 'wait':
        if ids or proposal['topic_hint'] is not None:
            raise ValueError('Wait carries no required topic')
    elif len(ids)!=1 or not isinstance(proposal['topic_hint'], str) or not proposal['topic_hint'].strip():
        raise ValueError('Initial alpha-to-v5 proposal requires exactly one source Memory and topic hint')
    return copy.deepcopy(proposal)


def resolve_memories(proposal, bank):
    validate_proposal(proposal, bank)
    # The candidate hint is never a substitute for the canonical Memory body.
    return [{'id': mid, 'body': bank[mid]} for mid in proposal['memory_ids']]
