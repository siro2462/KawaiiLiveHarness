"""Validate and normalize the Japanese memory contract without inventing content."""
import copy
import hashlib
import json
import re

CATEGORIES = {"出来事": "F", "望み・期待": "W", "反応": "R", "考え・評価": "T", "疑問・推測": "Q", "その後・今後": "P"}
EPI = {"observed", "speaker_report", "speaker_reaction", "speaker_desire", "speaker_evaluation", "speaker_expectation", "uncertain_memory", "unverified_suspicion", "counterfactual", "unknown"}
STATES = {"completed", "planned", "desired", "hypothetical", "habitual", "state", "unknown"}
RELATIONS = {"reaction", "appraisal", "about", "answer", "comparison", "requires_context", "temporal_before"}


class ValidationError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json_loads(text):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValidationError("Duplicate JSON key: " + k)
            result[k] = v
        return result
    def bad(value):
        raise ValidationError("Non-finite JSON value: " + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(name + " must be nonempty text")
    return value


def execution(item, kind):
    if "execution_status" in item:
        value = item["execution_status"]
        if value not in STATES:
            raise ValidationError("Invalid execution_status")
        return value
    # Classify stated status, never infer an event from its prose or a wish.
    state = item.get("状態", "")
    if not isinstance(state, str):
        raise ValidationError("状態 must be text")
    if state:
        if "仮定" in state:
            return "hypothetical"
        if "希望" in state or "願望" in state:
            return "desired"
        if "未実行" in state or "未実施" in state or "予定" in state or "方針" in state or "案" in state:
            return "planned"
        if "実行済み" in state or "実施済み" in state:
            return "completed"
        return "unknown"
    if kind == "W":
        return "desired"
    if kind == "F" and any(w in item.get("確かさ", "") for w in ("習慣", "毎回ではない", "継続")):
        return "habitual"
    return "unknown"


def certainty(item, kind, state):
    if "epistemic" in item:
        if item["epistemic"] not in EPI:
            raise ValidationError("Invalid epistemic code")
        return item["epistemic"]
    raw = item.get("確かさ", "")
    if not isinstance(raw, str):
        raise ValidationError("確かさ must be text")
    if "疑念" in raw or "疑い" in raw:
        return "unverified_suspicion"
    if state == "hypothetical" or "反実仮想" in raw:
        return "counterfactual"
    if kind == "Q":
        return "uncertain_memory"
    if kind == "W":
        when = item.get("いつの望み・期待か", "")
        if not isinstance(when, str):
            raise ValidationError("いつの望み・期待か must be text")
        return "speaker_expectation" if any(w in raw + when for w in ("予想", "予感", "期待")) else "speaker_desire"
    if raw and any(w in raw for w in ("未確認", "不明", "不確か", "未検証", "推測")):
        return "uncertain_memory"
    if kind == "R":
        return "speaker_reaction"
    if kind == "T":
        return "speaker_evaluation"
    if kind == "P":
        return {"desired": "speaker_desire", "planned": "speaker_expectation", "completed": "speaker_report"}.get(state, "unknown")
    # A reported event is not independently verified, even if it came from DB.
    if not raw or any(w in raw for w in ("元記憶", "本人", "創作設定", "事実", "報告", "習慣")):
        return "speaker_report"
    return "unknown"


def normalize_document(doc, namespace, world_scope):
    if not isinstance(doc, dict) or doc.get("形式") != "talk_memory_input_draft.v1":
        raise ValidationError("Unsupported memory format")
    canonical_json(doc)  # reject NaN and non-JSON values before writing
    if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", namespace):
        raise ValidationError("Invalid namespace")
    if world_scope not in {"fictional", "reference", "unknown"}:
        raise ValidationError("Invalid world scope")
    m = doc.get("記憶")
    if not isinstance(m, dict):
        raise ValidationError("Missing 記憶 object")
    external = required_text(m.get("記憶ID"), "記憶ID")
    title = required_text(m.get("題名"), "題名")
    for k in ("不明なこと", "補ってはいけないこと"):
        if not isinstance(m.get(k, []), list):
            raise ValidationError(k + " must be an array")
    original = doc.get("元DB", {})
    if not isinstance(original, dict):
        raise ValidationError("元DB must be an object")
    episode = original.get("episode")
    if episode is not None:
        required_text(episode, "元DB.episode")
        if original.get("episode_sha256") != hashlib.sha256(episode.encode("utf-8")).hexdigest():
            raise ValidationError("Original episode SHA mismatch")
    atoms, links, ids = [], [], set()
    for category, kind in CATEGORIES.items():
        values = m.get(category)
        if not isinstance(values, list):
            raise ValidationError("Missing array " + category)
        for item in values:
            if not isinstance(item, dict):
                raise ValidationError("Fragment must be an object")
            local = required_text(item.get("ID"), "ID")
            if local in ids:
                raise ValidationError("Duplicate local ID " + local)
            ids.add(local)
            text = required_text(item.get("内容"), "内容")
            origin = item.get("由来", "創作設定" if world_scope == "fictional" else "unknown")
            required_text(origin, "由来")
            quotes = item.get("原文根拠", [])
            if not isinstance(quotes, list) or any(not isinstance(q, str) or not q for q in quotes):
                raise ValidationError("Invalid source quotes")
            if origin == "元記憶" and (episode is None or not quotes):
                raise ValidationError("Original fragment needs original episode and quotes")
            if origin in {"創作補完", "創作設定"} and quotes:
                raise ValidationError("Creative fragment cannot claim original evidence")
            if episode is not None and any(q not in episode for q in quotes):
                raise ValidationError("Quote not present in original episode")
            hint = item.get("短い言葉")
            if hint is not None and not isinstance(hint, str):
                raise ValidationError("短い言葉 must be text")
            state = execution(item, kind)
            atoms.append(dict(local_id=local, kind=kind, content=text, origin=origin,
                              epistemic=certainty(item, kind, state), execution_status=state,
                              utterance_hint=hint, attributes=copy.deepcopy(item)))
            for field in ("対応ID", "根拠ID", "答えになる情報ID"):
                refs = item.get(field, [])
                if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs) or len(refs) != len(set(refs)):
                    raise ValidationError("Invalid reference array " + local)
                for target in refs:
                    relation = "answer" if field == "答えになる情報ID" else "appraisal" if field == "根拠ID" and kind == "T" else "reaction" if field == "対応ID" and kind == "R" else "about"
                    src, dst = (local, target) if relation == "answer" else (target, local)
                    links.append(dict(src=src, dst=dst, relation=relation, origin="explicit_json_reference",
                                      review_status="explicit_validated_unreviewed", evidence={"field": field, "owner": local, "target": target, "category": category}))
    if not atoms:
        raise ValidationError("No fragments")
    explicit = m.get("関係", [])
    if not isinstance(explicit, list):
        raise ValidationError("関係 must be an array")
    for row in explicit:
        if not isinstance(row, dict) or row.get("関係") not in RELATIONS:
            raise ValidationError("Unknown explicit relation")
        links.append(dict(src=row.get("起点ID"), dst=row.get("終点ID"), relation=row["関係"], origin="explicit_typed_json_relation",
                          review_status="explicit_validated_unreviewed", evidence=copy.deepcopy(row)))
    parents = {x: set() for x in ids}
    for link in links:
        if link["src"] not in ids or link["dst"] not in ids or link["src"] == link["dst"]:
            raise ValidationError("Dangling or self-referential link")
        if link["relation"] == "requires_context":
            parents[link["dst"]].add(link["src"])
    remaining = set(ids)
    while remaining:
        ready = {x for x in remaining if not (parents[x] & remaining)}
        if not ready:
            raise ValidationError("requires_context cycle")
        remaining -= ready
    return dict(normalization_version='memory-db-normalize-v1', external_id=external, namespace=namespace, world_scope=world_scope, title=title,
                central_theme=m.get("話の中心"), context=copy.deepcopy(m.get("場面", {})),
                unknowns=copy.deepcopy(m.get("不明なこと", [])), prohibitions=copy.deepcopy(m.get("補ってはいけないこと", [])),
                atoms=atoms, links=links, raw_document=copy.deepcopy(doc))
