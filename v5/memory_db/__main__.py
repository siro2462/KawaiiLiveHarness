"""Explicit-path, offline commands. No default database or generation process."""
import argparse
import json
from pathlib import Path

from .store import MemoryDB


def emit(value, output=None):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if output:
        path = Path(output)
        if path.exists():
            raise FileExistsError(f"Output already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Separate versioned memory database; CPU only")
    parser.add_argument("--db", required=True, help="Explicit new MemoryDB path; never the legacy DB")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    imp = commands.add_parser("import")
    imp.add_argument("--input", required=True, help="A single memory JSON or directory of individual JSON files")
    imp.add_argument("--namespace", required=True)
    imp.add_argument("--world-scope", required=True, choices=("fictional", "reference", "unknown"))
    rev = commands.add_parser("review")
    rev.add_argument("--revision", required=True)
    rev.add_argument("--status", required=True, choices=("unreviewed", "changes_requested", "accepted"))
    rev.add_argument("--reviewer", required=True)
    rev.add_argument("--note", required=True)
    rev.add_argument("--expected-sha256", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--namespace", required=True)
    snap.add_argument("--validation", action="store_true", help="Explicit draft-inclusive sandbox snapshot")
    snap.add_argument("--output")
    exp = commands.add_parser("export")
    exp.add_argument("--revision", required=True)
    exp.add_argument("--output")
    plan = commands.add_parser("plan")
    plan.add_argument("--snapshot", required=True)
    plan.add_argument("--revision", required=True)
    plan.add_argument("--backend", choices=("rhythm", "h06"), default="rhythm")
    plan.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command == "init" and Path(args.db).exists():
        parser.error("init refuses an existing file")
    with MemoryDB(args.db, create=args.command in ("init", "import")) as db:
        if args.command == "init":
            emit({"database": str(Path(args.db).resolve()), "created": True, "model_calls": 0})
        elif args.command == "import":
            src = Path(args.input)
            files = sorted(src.glob("*.json")) if src.is_dir() else [src]
            if not files:
                raise ValueError("No memory JSON files")
            results = []
            for path in files:
                raw = path.read_bytes()
                doc = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(doc, dict):
                    raise ValueError(f"Expected one memory document per file: {path}")
                results.append(db.import_document(doc, namespace=args.namespace, world_scope=args.world_scope,
                                                  source_bytes=raw, source_name=str(path.resolve())))
            emit({"imports": results, "review_status": "unreviewed", "model_calls": 0})
        elif args.command == "review":
            emit(db.review_revision(args.revision, args.status, args.reviewer, args.note, args.expected_sha256))
        elif args.command == "snapshot":
            emit(db.create_snapshot(args.namespace, mode="validation" if args.validation else "approved"), args.output)
        elif args.command == "export":
            emit(db.export_document(args.revision), args.output)
        else:
            from .projection import project_episode
            from .selector_adapter import select_episode
            from .surface import render_surface
            snapshot = db.load_snapshot(args.snapshot)
            sample = project_episode(snapshot, args.revision)
            selected = select_episode(sample, backend=args.backend)
            emit({"sample": sample, "plan": selected, "surface_input": render_surface(sample, selected),
                  "generated": False, "model_calls": 0}, args.output)


if __name__ == "__main__":
    main()
