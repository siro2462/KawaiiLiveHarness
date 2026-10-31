"""Separate, reopenable utterance log pinned to one immutable memory snapshot.

Compatible events(seq,kind,payload) layout. It never writes to a MemoryDB.
"""
import copy
from pathlib import Path
import sqlite3

from .normalize import canonical_json, digest, strict_json_loads
from .projection import project_episode
from .surface import render_surface


class EventLog:
    def __init__(self, path, snapshot):
        self.path = Path(path)
        self.snapshot = copy.deepcopy(snapshot)
        exists = self.path.exists()
        if not exists:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        try:
            if exists:
                try:
                    meta = dict(self.db.execute('SELECT key,value FROM event_meta'))
                except sqlite3.DatabaseError as exc:
                    raise ValueError('Not a versioned event log; existing file preserved') from exc
                if meta.get('schema') != 'memory-db-events-v1' or meta.get('snapshot_sha256') != digest(snapshot):
                    raise ValueError('Event log schema/snapshot mismatch')
            else:
                self.db.executescript('''
                CREATE TABLE event_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL CHECK(json_valid(payload)));
                CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable events'); END;
                CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable events'); END;
                CREATE TRIGGER meta_no_update BEFORE UPDATE ON event_meta BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END;
                CREATE TRIGGER meta_no_delete BEFORE DELETE ON event_meta BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END;
                ''')
                self.db.executemany('INSERT INTO event_meta VALUES(?,?)', [('schema','memory-db-events-v1'),
                    ('snapshot_sha256',digest(snapshot)),('snapshot_json',canonical_json(snapshot))])
                self.db.commit()
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _append(self, kind, payload):
        cursor = self.db.execute('INSERT INTO events(kind,payload) VALUES(?,?)',(kind,canonical_json(payload)))
        self.db.commit()
        return cursor.lastrowid

    def record_input(self, revision_id, plan):
        sample = project_episode(self.snapshot, revision_id)
        surface = render_surface(sample, plan, self.recent())
        payload = dict(provenance=sample['provenance'], plan=plan, surface=surface,
                       input_sha256=digest(surface), semantic_status='unverified')
        return self._append('surface_input', payload), surface

    def record_output(self, input_seq, text, delivered=False):
        if type(delivered) is not bool or not isinstance(text, str) or (delivered and not text.strip()):
            raise ValueError('Invalid output text')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute("SELECT payload FROM events WHERE seq=? AND kind='surface_input'",(input_seq,)).fetchone()
            if row is None:
                raise ValueError('Missing Surface input')
            if self.db.execute("SELECT 1 FROM events WHERE kind IN ('text_delivery_confirmed','surface_output_held') AND json_extract(payload,'$.input_seq')=?",(input_seq,)).fetchone():
                raise ValueError('Input already has an output receipt')
            source = strict_json_loads(row[0])
            provenance = source['provenance']
            payload = dict(input_seq=input_seq, text=text, provenance=provenance,
                           memory_id=provenance['episode_id'], input_sha256=source['input_sha256'],
                           atom_ids=[s['memory_id'] for s in source['plan']['steps']],
                           semantic_status='unverified', memory_promotion=False)
            cursor = self.db.execute('INSERT INTO events(kind,payload) VALUES(?,?)',
                ('text_delivery_confirmed' if delivered else 'surface_output_held',canonical_json(payload)))
        return cursor.lastrowid

    def recent(self):
        rows = self.db.execute("SELECT seq,payload FROM events WHERE kind='text_delivery_confirmed' ORDER BY seq DESC LIMIT 2").fetchall()
        result = []
        for row in rows:
            item = strict_json_loads(row['payload'])
            if sum(len(x['text']) for x in result) + len(item['text']) > 800:
                break
            result.insert(0, dict(item, seq=row['seq']))
        return result
