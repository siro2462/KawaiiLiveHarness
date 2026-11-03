"""Lossless, snapshot-scoped compatibility views. No inference or DB mutation."""
from __future__ import annotations

import copy
import hashlib
import json

PROJECTION_VERSION = "memory-db-projection-v1"
ENGINE_EPISTEMIC = {
    "observed", "speaker_report", "speaker_reaction", "speaker_desire",
    "speaker_evaluation", "speaker_expectation", "uncertain_memory",
    "unverified_suspicion", "counterfactual",
}


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _episodes(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("mode") not in {"approved", "validation"}:
        raise ValueError("a frozen approved or validation snapshot is required")
    if not snapshot.get("snapshot_id") or not snapshot.get("namespace"):
        raise ValueError("snapshot identity/namespace missing")
    if snapshot.get("projection_version") != PROJECTION_VERSION:
        raise ValueError("Unsupported projection version; do not silently reinterpret snapshot")
    episodes = snapshot.get("episodes", [])
    if not isinstance(episodes, list):
        raise ValueError("snapshot episodes must be embedded revisions")
    seen = set()
    for episode in episodes:
        rid = episode.get("revision_id")
        if not rid or rid in seen:
            raise ValueError("duplicate or missing snapshot revision")
        seen.add(rid)
        if episode.get("namespace") != snapshot["namespace"]:
            raise ValueError("cross-namespace candidate in snapshot")
        if snapshot["mode"] == "approved" and episode.get("review_status") != "accepted":
            raise ValueError("approved snapshot contains unaccepted revision")
    return episodes


def _engine_kind(atom):
    kind, status = atom["kind"], atom.get("execution_status", "unknown")
    if kind == "F":
        return "F", None
    if kind == "R":
        return "E", None
    if kind in {"T", "Q"}:
        return "T", None
    if kind == "W":
        if atom.get("epistemic") == "speaker_desire":
            return "E", None
        if atom.get("epistemic") == "speaker_expectation":
            return "T", None
        return "T", "ambiguous W: desire/expectation is not established"
    if kind == "P":
        if status == "completed":
            return "F", None
        if status in {"planned", "desired", "hypothetical"}:
            return "T", None
        return "T", "P execution status does not establish completed or future action"
    raise ValueError("unsupported source kind")


def _provenance(snapshot, episode):
    return {
        "snapshot_id": snapshot["snapshot_id"], "snapshot_mode": snapshot["mode"],
        "sandbox_only": snapshot["mode"] == "validation",
        "namespace": episode["namespace"], "world_scope": episode.get("world_scope", "unknown"),
        "episode_id": episode["episode_id"], "revision_id": episode["revision_id"],
        "external_id": episode.get("external_id"), "review_status": episode.get("review_status"),
        "content_sha256": episode.get("content_sha256"),
        "snapshot_projection_version": snapshot.get("projection_version"),
        "adapter_projection_version": PROJECTION_VERSION,
    }


def project_episode(snapshot, revision_id):
    """Project only a revision actually embedded in the supplied frozen snapshot.

    Nodes retain their complete source atom in ``raw_atom`` and source metadata in
    ``sidecar``. Ambiguous W/P atoms remain visible but explicitly non-emittable.
    Semantic edges preserve direction; only requires_context populates requires.
    """
    episodes = _episodes(snapshot)
    episode = next((e for e in episodes if e["revision_id"] == revision_id), None)
    if episode is None:
        raise ValueError("revision is not selected by this snapshot")
    provenance = _provenance(snapshot, episode)
    nodes, ids, local_ids = [], set(), set()
    for atom in episode.get("atoms", []):
        aid, local_id = atom.get("atom_id"), atom.get("local_id")
        if not aid or aid in ids or not local_id or local_id in local_ids:
            raise ValueError("duplicate or missing atom/local IDs")
        ids.add(aid)
        local_ids.add(local_id)
        if not isinstance(atom.get("content"), str) or not atom["content"].strip():
            raise ValueError("atom content must be nonempty text")
        engine_kind, reason = _engine_kind(atom)
        original_epistemic = atom.get("epistemic", "unknown")
        compatibility_epistemic = original_epistemic if original_epistemic in ENGINE_EPISTEMIC else "uncertain_memory"
        sidecar = {
            **copy.deepcopy(provenance), "atom_id": aid, "local_id": local_id,
            "original_kind": atom["kind"], "original_epistemic": original_epistemic,
            "origin": copy.deepcopy(atom.get("origin", "unknown")),
            "execution_status": atom.get("execution_status", "unknown"),
            "utterance_hint": copy.deepcopy(atom.get("utterance_hint")),
            "attributes": copy.deepcopy(atom.get("attributes", {})),
            "evidence": copy.deepcopy(atom.get("evidence", [])),
        }
        nodes.append({
            **copy.deepcopy(atom), "id": aid, "title": atom["content"],
            "kind": engine_kind, "original_kind": atom["kind"],
            "epistemic": compatibility_epistemic, "original_epistemic": original_epistemic,
            "topic": episode["episode_id"], "importance": 1.0, "tags": [],
            "requires": [], "source_lines": [], "source_quotes": [],
            "sidecar": sidecar, "raw_atom": copy.deepcopy(atom),
            "projection_deferred": reason,
        })
    by = {n["id"]: n for n in nodes}
    edges = []
    for link in episode.get("links", []):
        if link.get("src") not in ids or link.get("dst") not in ids:
            raise ValueError("dangling or cross-revision semantic link")
        if link["src"] == link["dst"]:
            raise ValueError("self-referential semantic link")
        relation = link.get("relation")
        if not isinstance(relation, str) or not relation:
            raise ValueError("link relation missing")
        edges.append({**copy.deepcopy(link), "rel": relation})
        if relation == "requires_context":
            by[link["dst"]]["requires"].append(link["src"])
    for node in nodes:
        node["requires"] = sorted(set(node["requires"]))
    # H06 needs an explicit entry. Select by content hash among eligible roots,
    # never JSON/ID order. This is adapter metadata, not an asserted source fact.
    roots = [n for n in nodes if not n["requires"] and not n["projection_deferred"]]
    if roots:
        entry = min(roots, key=lambda n: (n["kind"] != "F", content_hash([n["title"], n["kind"], n["epistemic"]])))
        entry["tags"] = ["entry"]
    return {
        "id": episode["episode_id"], "title": episode.get("title", ""),
        "nodes": nodes, "edges": edges, "provenance": provenance,
        "context": copy.deepcopy(episode.get("context")),
        "central_theme": copy.deepcopy(episode.get("central_theme")),
        "unknowns": copy.deepcopy(episode.get("unknowns", [])),
        "prohibitions": copy.deepcopy(episode.get("prohibitions", [])),
        "sources": copy.deepcopy(episode.get("sources", [])),
        "raw_document": copy.deepcopy(episode.get("raw_document")),
    }


def alpha_records(snapshot):
    """Return Alpha.populate fixture-file records with a lossless audit sidecar.

    Body labels are metadata, not promoted speech claims. Alpha's own namespace
    split remains fixtures/reference; the original namespace survives in sidecar.
    Unknown world scopes remain unavailable to legacy Alpha.
    """
    records = []
    for episode in sorted(_episodes(snapshot), key=lambda e: e["revision_id"]):
        world = episode.get("world_scope", "unknown")
        if world not in {"fictional", "reference"}:
            continue
        namespace = "fixtures" if world == "fictional" else "reference"
        atoms = sorted(episode.get("atoms", []), key=lambda a: a["local_id"])
        beats = [canonical_json({"kind": a["kind"], "content": a["content"],
                                 "epistemic": a.get("epistemic", "unknown"),
                                 "execution_status": a.get("execution_status", "unknown"),
                                 "origin": a.get("origin", "unknown")}) for a in atoms]
        provenance = _provenance(snapshot, episode)
        records.append({
            "id": "memory-db:" + content_hash([snapshot["snapshot_id"], episode["namespace"], episode["episode_id"], episode["revision_id"]]),
            "namespace": namespace,
            "authority": "synthetic_fixture" if world == "fictional" else "reference_transcript_unverified",
            "source": "memory-db:" + snapshot["snapshot_id"] + ":" + episode["revision_id"],
            "title": episode.get("title", ""), "text": "\n".join(beats), "beats": beats,
            "ordinal": 0, "_memory_db": {**provenance, "source_revision": copy.deepcopy(episode)},
        })
    return records


def resolve_recall(snapshot, candidate):
    """Resolve an existing Alpha candidate only within the supplied snapshot."""
    records = {r['id']: r for r in alpha_records(snapshot)}
    record = records.get(candidate.get('id'))
    if record is None or candidate.get('authority') != record['authority']:
        raise ValueError('Recall candidate is not from this snapshot/authority')
    return project_episode(snapshot, record['_memory_db']['revision_id'])
