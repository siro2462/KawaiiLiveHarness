"""Append-only SQLite revisions with explicit import, review and snapshot boundaries."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import copy
import hashlib
import sqlite3
import uuid

from .normalize import ValidationError, canonical_json, digest, normalize_document, strict_json_loads


class SchemaError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class MemoryDB:
    def __init__(self, path, create=True):
        self.path = Path(path)
        exists = self.path.exists()
        if not exists and not create:
            raise FileNotFoundError(path)
        if not exists:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        try:
            if exists:
                # Inspect before WAL/schema writes: refuse every legacy or unknown DB.
                try:
                    version = self.con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                except sqlite3.DatabaseError as exc:
                    raise SchemaError("Not a MemoryDB; legacy files are never migrated in-place") from exc
                if not version or version[0] != '1' or not self.con.execute("SELECT 1 FROM sqlite_master WHERE name='revisions'").fetchone():
                    raise SchemaError("Unsupported MemoryDB schema")
            self.con.execute('PRAGMA foreign_keys=ON')
            self.con.execute('PRAGMA busy_timeout=5000')
            self.con.execute('PRAGMA journal_mode=WAL')
            if not exists:
                ddl = Path(__file__).with_name('schema.sql').read_text('utf-8')
                triggers = ''
                for table in ('episodes', 'revisions', 'atoms', 'sources', 'atom_evidence', 'atom_links', 'reviews', 'snapshots', 'projections'):
                    for action in ('UPDATE', 'DELETE'):
                        triggers += f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable revision data'); END;\n"
                self.con.executescript('BEGIN IMMEDIATE;\n' + ddl + triggers + '\nCOMMIT;')
        except Exception:
            self.con.close()
            raise

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def transaction(self):
        self.con.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    def import_document(self, doc, namespace, world_scope, review_status='unreviewed', source_bytes=None, source_name=None):
        if review_status not in {'unreviewed', 'changes_requested', 'accepted'}:
            raise ValidationError('Invalid review status')
        # Import is never an approval operation, including on the initial version.
        if review_status != 'unreviewed':
            raise ValidationError('Use review_revision with explicit reviewer/hash after import')
        n = normalize_document(doc, namespace, world_scope)
        raw = source_bytes if source_bytes is not None else canonical_json(doc).encode('utf-8')
        if not isinstance(raw, bytes) or strict_json_loads(raw.decode('utf-8-sig')) != doc:
            raise ValidationError('Source bytes and document disagree')
        content_sha = digest(doc)
        eid = 'ep_' + uuid.uuid5(uuid.NAMESPACE_URL, namespace + '\0' + n['external_id']).hex
        rid = 'rev_' + digest([eid, content_sha])
        with self.transaction():
            old = self.con.execute('SELECT world_scope FROM episodes WHERE episode_id=?', (eid,)).fetchone()
            if old and old[0] != world_scope:
                raise ValidationError('World scope change requires a different namespace/episode')
            prior = self.con.execute('SELECT revision_id FROM revisions WHERE episode_id=? AND content_sha256=?', (eid, content_sha)).fetchone()
            if prior:
                return dict(episode_id=eid, revision_id=prior[0], content_sha256=content_sha, created=False)
            self.con.execute('INSERT OR IGNORE INTO episodes VALUES(?,?,?,?)', (eid, namespace, n['external_id'], world_scope))
            version = self.con.execute('SELECT coalesce(max(version),0)+1 FROM revisions WHERE episode_id=?', (eid,)).fetchone()[0]
            self.con.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?,?,?)', (rid, eid, version, content_sha, hashlib.sha256(raw).hexdigest(), raw, canonical_json(doc), canonical_json(n), now()))
            aid = {a['local_id']: rid + ':' + a['local_id'] for a in n['atoms']}
            # All writes below are in this transaction; no partially public episode.
            for a in n['atoms']:
                self.con.execute('INSERT INTO atoms VALUES(?,?,?,?,?,?,?,?,?,?)', (aid[a['local_id']], rid, a['local_id'], a['kind'], a['content'], a['origin'], a['epistemic'], a['execution_status'], a['utterance_hint'], canonical_json(a['attributes'])))
            sources = [('input', {'source_name': source_name, 'raw_sha256': hashlib.sha256(raw).hexdigest()})]
            if doc.get('元DB'):
                sources.append(('original_evidence', doc['元DB']))
            if doc.get('参考'):
                sources.append(('style_reference', doc['参考']))
            for role, metadata in sources:
                sid = rid + ':source:' + role
                self.con.execute('INSERT INTO sources VALUES(?,?,?,?)', (sid, rid, role, canonical_json(metadata)))
            for a in n['atoms']:
                for i, q in enumerate(a['attributes'].get('原文根拠', [])):
                    self.con.execute('INSERT INTO atom_evidence(revision_id,atom_id,source_id,role,quote,locator_json) VALUES(?,?,?,?,?,?)', (rid, aid[a['local_id']], rid + ':source:original_evidence', 'original_evidence', q, canonical_json({'local_id': a['local_id'], 'quote_index': i})))
            for link in n['links']:
                self.con.execute('INSERT INTO atom_links(revision_id,src,dst,relation,origin,review_status,evidence_json) VALUES(?,?,?,?,?,?,?)', (rid, aid[link['src']], aid[link['dst']], link['relation'], link['origin'], link['review_status'], canonical_json(link['evidence'])))
        return dict(episode_id=eid, revision_id=rid, content_sha256=content_sha, created=True)

    def review_revision(self, revision_id, status, reviewer, note, expected_sha256):
        if status not in {'unreviewed', 'changes_requested', 'accepted'} or not reviewer or not note:
            raise ValidationError('Explicit review status, reviewer and note required')
        row = self.con.execute('SELECT content_sha256 FROM revisions WHERE revision_id=?', (revision_id,)).fetchone()
        if not row or row[0] != expected_sha256:
            raise ValidationError('Review target/hash mismatch')
        with self.transaction():
            cur = self.con.execute('INSERT INTO reviews(revision_id,status,reviewer,note,expected_sha256,created_at) VALUES(?,?,?,?,?,?)', (revision_id, status, reviewer, note, expected_sha256, now()))
        return dict(revision_id=revision_id, status=status, review_seq=cur.lastrowid)

    def export_document(self, revision_id):
        row = self.con.execute('SELECT document_json FROM revisions WHERE revision_id=?', (revision_id,)).fetchone()
        if not row:
            raise KeyError(revision_id)
        return strict_json_loads(row[0])

    def read_revision(self, revision_id):
        row = self.con.execute('SELECT r.*,e.namespace,e.external_id,e.world_scope FROM revisions r JOIN episodes e USING(episode_id) WHERE revision_id=?', (revision_id,)).fetchone()
        if not row:
            raise KeyError(revision_id)
        n = strict_json_loads(row['normalized_json'])
        review = self.con.execute('SELECT * FROM reviews WHERE revision_id=? ORDER BY seq DESC LIMIT 1', (revision_id,)).fetchone()
        n.update(episode_id=row['episode_id'], revision_id=revision_id, version=row['version'], content_sha256=row['content_sha256'], raw_sha256=row['raw_sha256'], review_status=review['status'] if review else 'unreviewed', review=dict(review) if review else None)
        n['atoms'] = []
        for a in self.con.execute('SELECT * FROM atoms WHERE revision_id=? ORDER BY local_id', (revision_id,)):
            data = dict(a);data['attributes'] = strict_json_loads(data.pop('attributes_json'))
            data['evidence'] = [dict(x) for x in self.con.execute('SELECT source_id,role,quote,locator_json FROM atom_evidence WHERE atom_id=?', (a['atom_id'],))]
            n['atoms'].append(data)
        n['links'] = []
        for link in self.con.execute('SELECT * FROM atom_links WHERE revision_id=? ORDER BY link_id', (revision_id,)):
            data = dict(link);data['evidence'] = strict_json_loads(data.pop('evidence_json'));n['links'].append(data)
        n['sources'] = [{**dict(s), 'metadata': strict_json_loads(s['metadata_json'])} for s in self.con.execute('SELECT * FROM sources WHERE revision_id=? ORDER BY source_id', (revision_id,))]
        return n

    def create_snapshot(self, namespace, revision_ids=None, mode='approved', projection_version='memory-db-projection-v1'):
        if mode not in {'approved', 'validation'}:
            raise ValidationError('Unknown snapshot mode')
        with self.transaction():
            if revision_ids is None:
                revision_ids = [r[0] for r in self.con.execute('SELECT r.revision_id FROM revisions r JOIN episodes e USING(episode_id) WHERE e.namespace=? AND r.version=(SELECT max(x.version) FROM revisions x WHERE x.episode_id=r.episode_id) ORDER BY e.external_id', (namespace,))]
            if len(revision_ids) != len(set(revision_ids)):
                raise ValidationError('Duplicate revisions in snapshot')
            episodes = [self.read_revision(r) for r in revision_ids]
            if any(e['namespace'] != namespace for e in episodes) or len({e['episode_id'] for e in episodes}) != len(episodes):
                raise ValidationError('Cross-namespace or conflicting episode versions')
            if mode == 'approved':
                episodes = [e for e in episodes if e['review_status'] == 'accepted']
            payload = dict(namespace=namespace, mode=mode, projection_version=projection_version, episodes=sorted(episodes, key=lambda e: e['episode_id']))
            sid = 'snapshot_' + digest(payload);payload['snapshot_id'] = sid
            txt = canonical_json(payload)
            self.con.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)', (sid, namespace, mode, projection_version, txt, hashlib.sha256(txt.encode()).hexdigest()))
        return copy.deepcopy(payload)

    def load_snapshot(self, snapshot_id):
        row = self.con.execute('SELECT payload_json,payload_sha256 FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        if not row:
            raise KeyError(snapshot_id)
        if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
            raise SchemaError('Snapshot integrity failure')
        return strict_json_loads(row[0])

    def save_projection(self, snapshot_id, backend, payload):
        self.load_snapshot(snapshot_id)
        sha = digest(payload);pid = 'projection_' + digest([snapshot_id, backend, sha])
        with self.transaction():
            self.con.execute('INSERT OR IGNORE INTO projections VALUES(?,?,?,?,?)', (pid, snapshot_id, backend, canonical_json(payload), sha))
        return dict(projection_id=pid, snapshot_id=snapshot_id, backend=backend, payload_sha256=sha)
