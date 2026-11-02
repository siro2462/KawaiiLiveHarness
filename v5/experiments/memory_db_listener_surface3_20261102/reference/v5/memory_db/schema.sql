CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO meta VALUES('schema_version','1');
CREATE TABLE episodes(
 episode_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,external_id TEXT NOT NULL,
 world_scope TEXT NOT NULL CHECK(world_scope IN ('fictional','reference','unknown')),
 UNIQUE(namespace,external_id)
);
CREATE TABLE revisions(
 revision_id TEXT PRIMARY KEY,episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
 version INTEGER NOT NULL CHECK(version>0),content_sha256 TEXT NOT NULL,
 raw_sha256 TEXT NOT NULL,raw_bytes BLOB NOT NULL,document_json TEXT NOT NULL CHECK(json_valid(document_json)),
 normalized_json TEXT NOT NULL CHECK(json_valid(normalized_json)),created_at TEXT NOT NULL,
 UNIQUE(episode_id,version),UNIQUE(episode_id,content_sha256),UNIQUE(revision_id,content_sha256)
);
CREATE TABLE atoms(
 atom_id TEXT PRIMARY KEY,revision_id TEXT NOT NULL REFERENCES revisions(revision_id),local_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('F','W','R','T','Q','P')),content TEXT NOT NULL CHECK(length(trim(content))>0),
 origin TEXT NOT NULL,epistemic TEXT NOT NULL CHECK(epistemic IN ('observed','speaker_report','speaker_reaction','speaker_desire','speaker_evaluation','speaker_expectation','uncertain_memory','unverified_suspicion','counterfactual','unknown')),
 execution_status TEXT NOT NULL CHECK(execution_status IN ('completed','planned','desired','hypothetical','habitual','state','unknown')),
 utterance_hint TEXT,attributes_json TEXT NOT NULL CHECK(json_valid(attributes_json)),
 UNIQUE(revision_id,local_id),UNIQUE(revision_id,atom_id)
);
CREATE TABLE sources(
 source_id TEXT PRIMARY KEY,revision_id TEXT NOT NULL REFERENCES revisions(revision_id),
 role TEXT NOT NULL CHECK(role IN ('input','original_evidence','style_reference')),
 metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),UNIQUE(revision_id,source_id)
);
CREATE TABLE atom_evidence(
 evidence_id INTEGER PRIMARY KEY,revision_id TEXT NOT NULL,atom_id TEXT NOT NULL,source_id TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('original_evidence','style_reference','input')),
 quote TEXT,locator_json TEXT NOT NULL CHECK(json_valid(locator_json)),
 FOREIGN KEY(revision_id,atom_id) REFERENCES atoms(revision_id,atom_id),
 FOREIGN KEY(revision_id,source_id) REFERENCES sources(revision_id,source_id)
);
CREATE TABLE atom_links(
 link_id INTEGER PRIMARY KEY,revision_id TEXT NOT NULL,src TEXT NOT NULL,dst TEXT NOT NULL CHECK(src<>dst),
 relation TEXT NOT NULL CHECK(relation IN ('reaction','appraisal','about','answer','comparison','requires_context','temporal_before')),
 origin TEXT NOT NULL,review_status TEXT NOT NULL CHECK(review_status='explicit_validated_unreviewed'),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
 FOREIGN KEY(revision_id,src) REFERENCES atoms(revision_id,atom_id),
 FOREIGN KEY(revision_id,dst) REFERENCES atoms(revision_id,atom_id)
);
CREATE TABLE reviews(
 seq INTEGER PRIMARY KEY,revision_id TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('unreviewed','changes_requested','accepted')),
 reviewer TEXT NOT NULL,note TEXT NOT NULL,expected_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(revision_id,expected_sha256) REFERENCES revisions(revision_id,content_sha256)
);
CREATE TABLE snapshots(
 snapshot_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,mode TEXT NOT NULL CHECK(mode IN ('approved','validation')),
 projection_version TEXT NOT NULL,payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),payload_sha256 TEXT NOT NULL
);
CREATE TABLE projections(
 projection_id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),backend TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),payload_sha256 TEXT NOT NULL,
 UNIQUE(snapshot_id,backend,payload_sha256)
);
CREATE INDEX atoms_revision ON atoms(revision_id);
CREATE INDEX links_src ON atom_links(revision_id,src);
CREATE INDEX links_dst ON atom_links(revision_id,dst);
CREATE INDEX reviews_revision ON reviews(revision_id,seq);
