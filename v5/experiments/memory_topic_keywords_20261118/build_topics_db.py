"""Build an independent review database from a verified transcript and reviewed attributes."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE source_document(
    document_id INTEGER PRIMARY KEY CHECK(document_id=1),
    sha256 TEXT NOT NULL,
    transcript_utf8 BLOB NOT NULL
);
CREATE TABLE source_lines(
    line_no INTEGER PRIMARY KEY CHECK(line_no>0),
    kind TEXT NOT NULL CHECK(kind IN ('heading','editorial','speech','blank')),
    text TEXT NOT NULL
);
CREATE TABLE topics(
    topic_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    heading_line INTEGER NOT NULL UNIQUE REFERENCES source_lines(line_no),
    end_line INTEGER NOT NULL REFERENCES source_lines(line_no),
    CHECK(end_line>=heading_line)
);
CREATE TABLE attributes(
    attribute_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(topic_id),
    position INTEGER NOT NULL,
    label TEXT NOT NULL,
    UNIQUE(topic_id, label),
    UNIQUE(topic_id, position)
);
CREATE TABLE attribute_keywords(
    attribute_id TEXT NOT NULL REFERENCES attributes(attribute_id),
    keyword TEXT NOT NULL CHECK(length(keyword)>0),
    PRIMARY KEY(attribute_id, keyword)
);
CREATE TABLE attribute_evidence(
    attribute_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    line_no INTEGER NOT NULL REFERENCES source_lines(line_no),
    start_char INTEGER NOT NULL CHECK(start_char>=0),
    PRIMARY KEY(attribute_id, keyword, line_no),
    FOREIGN KEY(attribute_id, keyword) REFERENCES attribute_keywords(attribute_id, keyword)
);
CREATE VIEW graph_topics AS SELECT topic_id, title FROM topics;
CREATE VIEW graph_attributes AS SELECT attribute_id, topic_id, position, label FROM attributes;
CREATE VIEW evidence_lines AS
    SELECT e.attribute_id, e.keyword, e.line_no, e.start_char, s.text
    FROM attribute_evidence AS e JOIN source_lines AS s USING (line_no);
"""


def line_kind(text):
    if text.startswith("# "):
        return "heading"
    if text.startswith("## "):
        return "editorial"
    return "speech" if text else "blank"


def build(transcript, reviewed, output):
    raw = transcript.read_bytes()
    text = raw.decode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    annotation = json.loads(reviewed.read_text(encoding="utf-8"))
    if digest != annotation["source_sha256"]:
        raise ValueError("Transcript SHA-256 mismatch.")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    rows = {n: (line_kind(line), line) for n, line in enumerate(lines, 1)}
    heading_numbers = [n for n, (kind, _) in rows.items() if kind == "heading"]
    topics = annotation["topics"]
    if heading_numbers != [topic["heading_line"] for topic in topics]:
        raise ValueError("Each # heading must have one topic, in source order.")

    topic_rows, attribute_rows, keyword_rows, evidence_rows = [], [], [], []
    for i, topic in enumerate(topics):
        title, first = topic["title"], topic["heading_line"]
        last = heading_numbers[i + 1] - 1 if i + 1 < len(topics) else len(rows)
        if rows[first][1] != "# " + title:
            raise ValueError(f"Heading mismatch at L{first}.")
        topic_id = topic["topic_id"]
        topic_rows.append((topic_id, title, first, last))
        for order, attr in enumerate(topic["attributes"], 1):
            label, keywords, evidence = attr["label"], attr["keywords"], attr["lines"]
            attr_id = f"{topic_id}-A{order:02}"
            if not label.strip() or not keywords or not evidence:
                raise ValueError(f"{attr_id} must have a label, keywords and evidence.")
            if len(set(keywords)) != len(keywords) or len(set(evidence)) != len(evidence):
                raise ValueError(f"{attr_id} has duplicate keywords or evidence.")
            attribute_rows.append((attr_id, topic_id, order, label))
            for line_no in evidence:
                if not first <= line_no <= last or rows[line_no][0] != "speech":
                    raise ValueError(f"{attr_id} L{line_no} is outside the topic's spoken lines.")
                if not any(keyword in rows[line_no][1] for keyword in keywords):
                    raise ValueError(f"{attr_id} L{line_no} has no listed keyword.")
            for keyword in keywords:
                if not keyword.strip():
                    raise ValueError(f"{attr_id} has an empty keyword.")
                hits = [(line_no, rows[line_no][1].find(keyword)) for line_no in evidence]
                if not any(offset >= 0 for _, offset in hits):
                    raise ValueError(f"{attr_id} keyword absent from evidence: {keyword!r}")
                keyword_rows.append((attr_id, keyword))
                evidence_rows.extend((attr_id, keyword, line_no, offset)
                                     for line_no, offset in hits if offset >= 0)

    # Finish and validate in memory so an incomplete database cannot become the deliverable.
    with sqlite3.connect(":memory:") as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO source_document VALUES(1,?,?)", (digest, raw))
        db.executemany("INSERT INTO source_lines VALUES(?,?,?)",
                       ((n, kind, line) for n, (kind, line) in rows.items()))
        db.executemany("INSERT INTO topics VALUES(?,?,?,?)", topic_rows)
        db.executemany("INSERT INTO attributes VALUES(?,?,?,?)", attribute_rows)
        db.executemany("INSERT INTO attribute_keywords VALUES(?,?)", keyword_rows)
        db.executemany("INSERT INTO attribute_evidence VALUES(?,?,?,?)", evidence_rows)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok" or db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Invalid database relations.")
        for keyword, offset, line in db.execute("SELECT keyword,start_char,text FROM evidence_lines"):
            if line[offset:offset + len(keyword)] != keyword:
                raise ValueError("Keyword evidence offset mismatch.")
        db.commit()
        # Exclusive creation also protects a previously delivered output.
        with output.open("xb") as handle:
            handle.write(db.serialize())

    counts = [len(topic["attributes"]) for topic in topics]
    return {
        "source_sha256": digest,
        "source_lines": len(rows),
        "speech_lines": sum(kind == "speech" for kind, _ in rows.values()),
        "topics": len(topic_rows), "attributes": len(attribute_rows),
        "attributes_min": min(counts), "attributes_max": max(counts),
        "keywords": len(keyword_rows),
        "keyword_line_links": len(evidence_rows),
        "evidence_lines": len({row[2] for row in evidence_rows}),
        "integrity": integrity,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("reviewed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.transcript, args.reviewed, args.output), ensure_ascii=False))
