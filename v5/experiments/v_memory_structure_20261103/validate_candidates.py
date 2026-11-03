"""Read-only candidate validation; never calls a model or writes a memory DB."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate(run, normalizer_path):
    spec = importlib.util.spec_from_file_location("candidate_normalizer", normalizer_path)
    normalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(normalizer)
    frozen = read(run / "source_freeze.json")
    before = read(run / "protected_before.json")
    checks = []
    normalized = []

    def check(name, ok):
        checks.append({"check": name, "pass": bool(ok)})

    for record in before:
        check("protected:" + record["label"], sha(Path(record["path"])) == record["sha256"])
    ids = set()
    for item in read(run / "candidates.json"):
        doc = item["document"]
        memory = doc["記憶"]
        mid = memory["記憶ID"]
        check(mid + ":unique", mid not in ids)
        ids.add(mid)
        source_path = run / item["authored_source"]
        check(mid + ":source_frozen", sha(source_path) == frozen[item["authored_source"]])
        source = read(source_path)
        clauses = {x["id"]: x["text"] for x in source["clauses"]}
        check(mid + ":fiction_label", source["fictional"] is True and source["author"] == "root_ai_manual")
        result = normalizer.normalize_document(doc, "fiction_structure_candidate", "fictional")
        check(mid + ":existing_contract", result["world_scope"] == "fictional")
        for atom in result["atoms"]:
            row = atom["attributes"]
            aid = mid + ":" + atom["local_id"]
            evidence = row.get("創作仕様根拠", [])
            check(aid + ":evidence", bool(evidence) and all(
                e["clause_id"] in clauses and e["quote"] and e["quote"] in clauses[e["clause_id"]]
                for e in evidence))
            check(aid + ":origin", atom["origin"] == "創作設定" and row["原文根拠"] == [])
            if atom["kind"] == "R":
                check(aid + ":reaction_target", bool(row.get("対応ID")))
            if atom["kind"] == "T":
                check(aid + ":evaluation_basis", bool(row.get("根拠ID")))
            if atom["kind"] == "W":
                check(aid + ":wish_time", bool(row.get("いつの望み・期待か")))
            if row.get("短い言葉"):
                check(aid + ":hint_not_actual_quote", row.get("短い言葉の扱い") == "内心の表現候補・実際の発言ではない")
        check(mid + ":no_authored_operation_sequence", "steps" not in item and "操作列" not in memory)
        normalized.append(result)
    audit = {"status": "pass" if all(c["pass"] for c in checks) else "fail",
             "checks": checks, "candidate_count": len(normalized),
             "fragment_count": sum(len(x["atoms"]) for x in normalized),
             "normalizer_sha256": sha(normalizer_path),
             "surface_calls": 0, "db_writes": 0, "operation_selection_runs": 0,
             "scope": "参照と形式のみ。内容の意味・ライブ感・モデル品質は検査しない。"}
    return audit, normalized


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--normalizer", required=True, type=Path)
    args = parser.parse_args()
    audit, normalized = validate(args.run, args.normalizer)
    (args.run / "technical_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.run / "normalized_candidates.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in audit.items() if k != "checks"}, ensure_ascii=False))
    raise SystemExit(0 if audit["status"] == "pass" else 1)
