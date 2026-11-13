"""Render and check manually annotated discourse chunks from local JSON inputs.

No model calls, network access, source-text rewriting or automatic quality labels.
"""
import argparse
from collections import Counter
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonspace(text):
    return sum(not c.isspace() for c in text)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TextCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = None
        self.texts = {}
        self.order = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-chunk-text" in attrs:
            assert self.active is None
            self.active = attrs["data-chunk-text"]
            assert self.active not in self.texts
            self.order.append(self.active)
            self.texts[self.active] = ""

    def handle_data(self, data):
        if self.active is not None:
            self.texts[self.active] += data

    def handle_endtag(self, tag):
        if tag == "pre" and self.active is not None:
            self.active = None


def main(run):
    inputs = read(run / "inputs.json")
    ann = read(run / "chunk_annotations.json")
    findings = read(run / "findings.json")
    records = {r["id"]: r for r in inputs["records"]}
    annotated = {r["id"]: r for r in ann["records"]}
    assert len(records) == len(inputs["records"]) == len(annotated) == len(ann["records"])
    assert records.keys() == annotated.keys()
    chunk_map = {}
    for rid, record in records.items():
        row = annotated[rid]
        assert row["group"] == record["group"] and row["topic"] == record["topic"]
        cursor = 0
        for i, chunk in enumerate(row["chunks"], 1):
            assert chunk["id"] == f"{rid}-C{i:02}"
            assert chunk["id"] not in chunk_map
            assert chunk["start"] == cursor < chunk["end"] <= len(record["text"])
            assert record["text"][chunk["start"]:chunk["end"]] == chunk["text"]
            assert chunk["role"] in ann["roles"]
            assert all(role in ann["roles"] for role in chunk["secondary_roles"])
            assert chunk["progress"] in ann["progress_labels"]
            cursor = chunk["end"]
            chunk_map[chunk["id"]] = chunk
        assert cursor == len(record["text"])
        assert "".join(c["text"] for c in row["chunks"]) == record["text"]
    for example in findings["examples"]:
        assert example["ai"] and example["vtuber"]
        assert all(cid in chunk_map for cid in example["ai"] + example["vtuber"])
        assert all(cid.startswith("R") for cid in example["ai"])
        assert all(cid.startswith("V") for cid in example["vtuber"])
    groups = []
    for gid, name in inputs["groups"].items():
        selected = [r for r in ann["records"] if r["group"] == gid]
        chunks = [c for r in selected for c in r["chunks"]]
        lengths = [nonspace(c["text"]) for c in chunks]
        merged_lengths = []
        for record in selected:
            merged = []
            for c in record["chunks"]:
                if merged and merged[-1][0] == c["role"]:
                    merged[-1][1] += nonspace(c["text"])
                else:
                    merged.append([c["role"], nonspace(c["text"])])
            merged_lengths.extend(length for _, length in merged)
        groups.append(dict(id=gid, label=name, records=len(selected),
                           topics=len({r["topic"] for r in selected}),
                           chunks=len(chunks), body_chars_nonspace=sum(lengths),
                           chunk_chars_median=statistics.median(lengths),
                           chunk_chars_mean=round(statistics.mean(lengths), 2),
                           chunk_chars_range=[min(lengths), max(lengths)],
                           primary_role_counts=dict(Counter(c["role"] for c in chunks)),
                           manual_progress_counts=dict(Counter(c["progress"] for c in chunks)),
                           adjacent_same_role_merge=dict(chunks=len(merged_lengths),
                               median_chars=statistics.median(merged_lengths))))
    metrics = dict(status="pass", groups=groups, definitions=dict(
        chunk="Root manual discourse-function/meaning unit; not acoustic, fixed-length or model-call unit.",
        length="Unicode non-whitespace characters of the preserved text, not tokens or speaking duration.",
        role="One primary manual functional label plus optional secondary roles; not F/E/T/N or CPU operation.",
        progress="Relation to preceding material in same topic; introduce does not imply source-supported truth.",
        sensitivity="Merge adjacent chunks of the same primary role within each preserved record; not a second independent review."),
        human_ratings=0, new_model_calls=0, operation_execution_rate=None)
    write(run / "metrics.json", metrics)
    css = """body{margin:0;background:#f5f5f0;color:#20282d;font:16px/1.7 system-ui,sans-serif}
main{max-width:1450px;margin:auto;padding:28px}h1{font-size:28px;line-height:1.35}h2{margin-top:36px}
a{color:#126479}.lead,.limits{padding:18px;background:#fff;border:1px solid #d6dedc;border-radius:10px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;align-items:start}
article{background:#fff;border:1px solid #d6dedc;border-radius:10px;padding:16px;margin:12px 0}
.chunk{border-left:5px solid var(--color);background:#f7f9f9;padding:10px 12px;margin:10px 0}
.chunk pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;margin:4px 0}.meta{font-size:12px;color:#52636b}
.note{font-size:13px;color:#71420d;background:#fff3de;padding:7px;border-radius:5px}
.seq{font-size:14px;color:#304c57;line-height:2}.pill{display:inline-block;border-bottom:3px solid var(--color);padding:2px 6px;margin:2px}
table{border-collapse:collapse;background:#fff;width:100%;font-size:14px}td,th{border:1px solid #d6dedc;padding:8px;text-align:left}
button{padding:8px 14px;border:1px solid #698088;background:#fff;border-radius:6px;cursor:pointer}
body.hide-notes .note{display:none}.legend{margin:14px 0}.example{background:#eaf1f2;padding:16px;border-radius:10px}
@media(max-width:900px){.grid{grid-template-columns:1fr}main{padding:16px}h1{font-size:23px}}
@media print{button{display:none}.chunk{break-inside:avoid}body{background:white}main{padding:0}}
"""
    colors = dict(bridge="#6c7587", context="#bd8235", event="#318c91", reaction="#d16a70",
                  interpretation="#8067b0", repair="#5183bd", interaction="#5d9271", summary="#9a8873")
    esc = lambda value: escape(str(value), quote=True)

    def pills(chunks):
        return " → ".join(f'<span class="pill" style="--color:{colors[c["role"]]}">{esc(c["id"])} {esc(ann["roles"][c["role"]])}</span>' for c in chunks)

    page = f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Chunk比較：AIと保存VTuber原文</title><style>{css}</style></head><body><main>'
    page += '<h1>Chunkで見る、AIの発話とVTuberの語り</h1>'
    page += f'<div class="lead"><b>{esc(findings["conclusion"])}</b><p>{esc(findings["scope"])}</p><p>Chunk＝意味と語りの役割がまとまる単位。句点・改行・4操作・モデルの1コールとは別。全文は無改変で区切り、色は機能を示す。正しさや品質の合格色ではない。</p></div>'
    page += '<p><a href="result.md">評価結果</a> ／ <a href="chunk_annotations.json">全境界・役割・注記JSON</a> ／ <a href="metrics.json">定義付き集計</a></p>'
    page += '<button onclick="document.body.classList.toggle(\'hide-notes\')">分析注記を表示／非表示</button><div class="legend">'
    page += ''.join(f'<span class="pill" style="--color:{colors[k]}">{esc(v)}</span>' for k, v in ann["roles"].items()) + '</div>'
    page += '<h2>手動分割の記述統計</h2><table><tr><th>群</th><th>話題／保存本文</th><th>全文字数</th><th>Chunk数</th><th>中央値</th><th>平均</th></tr>'
    for g in groups:
        page += f'<tr><td>{esc(g["label"])}</td><td>{g["topics"]}／{g["records"]}</td><td>{g["body_chars_nonspace"]}</td><td>{g["chunks"]}</td><td>{g["chunk_chars_median"]}字</td><td>{g["chunk_chars_mean"]}字</td></tr>'
    page += '</table><p class="meta">非空白文字数。分割は条件既知AIの手動判断で、統計的有意差・自然さ・発話時間の点数ではない。VTuberは編集文、AIは4コールの境界を保持。話題と全体の長さが異なる。</p>'
    page += '<h2>Chunk列を比べる代表箇所</h2>'
    for example in findings["examples"]:
        page += f'<section class="example"><h3>{esc(example["title"])}</h3><div class="grid">'
        for key, title in [("ai", "AI"), ("vtuber", "VTuber保存原文")]:
            page += f'<div><b>{title}</b>'
            for cid in example[key]:
                c = chunk_map[cid]
                page += f'<blockquote><a href="#{esc(cid)}">{esc(cid)}</a> {esc(ann["roles"][c["role"]])}<br>{esc(c["text"].strip())}</blockquote>'
            page += '</div>'
        page += f'</div><p>{esc(example["finding"])}</p></section>'
    page += '<h2>全12 AI発話：全文Chunkハイライト</h2>'
    for group in inputs["groups"]:
        if group == "vtuber":
            page += '<h2>VTuber5話題：保存編集原文の全文Chunkハイライト</h2>'
        for topic in dict.fromkeys(r["topic"] for r in ann["records"] if r["group"] == group):
            page += f'<h3>{esc(topic)}</h3><div class="grid">'
            for row in [r for r in ann["records"] if r["group"] == group and r["topic"] == topic]:
                source = records[row["id"]]
                page += f'<article id="{esc(row["id"])}"><h3>{esc(row["id"])} {esc(source.get("title", source["topic"]))}</h3><div class="seq">{pills(row["chunks"])}</div>'
                for c in row["chunks"]:
                    secondary = ' ＋ '.join(ann["roles"][v] for v in c["secondary_roles"])
                    page += f'<div class="chunk" id="{esc(c["id"])}" style="--color:{colors[c["role"]]}"><div class="meta">{esc(c["id"])} ／ {esc(ann["roles"][c["role"]])} {esc(secondary)} ／ {nonspace(c["text"])}字 ／ {esc(ann["progress_labels"][c["progress"]])}</div><pre data-chunk-text="{esc(c["id"])}">{esc(c["text"])}</pre>'
                    if c["note"]:
                        page += f'<div class="note">{esc(c["note"])}</div>'
                    page += '</div>'
                page += '</article>'
            page += '</div>'
    page += '<h2>読み方と限界</h2><div class="limits">'
    page += ''.join(f'<p>{esc(x)}</p>' for x in findings["limits"])
    page += '<p>入力で選ばれた39操作の意味実行率は、このChunk分割から算出しない。新しい観察に見える追加にも元記憶と矛盾するものがあり、機能・進展・忠実さは別の観点。</p></div></main></body></html>'
    (run / "comparison.html").write_text(page, encoding="utf-8")
    parsed = TextCheck()
    parsed.feed(page)
    assert parsed.active is None and parsed.order == list(chunk_map)
    assert parsed.texts == {k: v["text"] for k, v in chunk_map.items()}
    for rid, row in annotated.items():
        assert ''.join(parsed.texts[c["id"]] for c in row["chunks"]) == records[rid]["text"]
    protected = read(run / "protected_before.json")
    assert all(sha(Path(item["path"])) == item["sha256"] for item in protected)
    audit = dict(status="pass", records=len(records), ai_records=sum(r["group"] == "ai" for r in records.values()),
                 vtuber_records=sum(r["group"] == "vtuber" for r in records.values()), chunks=len(chunk_map),
                 every_character_preserved=True, offsets_contiguous=True, html_parser_full_text_exact=True,
                 all_example_ids_resolve=True, protected_sources_unchanged=True,
                 annotation_sha256=sha(run / "chunk_annotations.json"), inputs_sha256=sha(run / "inputs.json"),
                 program_sha256=sha(Path(__file__)), html_sha256=sha(run / "comparison.html"),
                 new_model_calls=0, human_ratings=0, operation_execution_rate=None,
                 scope="Structural preservation and saved inputs; not an independent semantic-quality judgment.")
    write(run / "audit.json", audit)
    print(json.dumps(dict(audit=audit, groups=groups), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    main(parser.parse_args().run)
