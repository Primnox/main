-- ============================================================================
-- Primnox V2 — primnox.db
-- Conforms to CRS/1.0 (docs/CONVERSATION_RUNTIME_SPEC.md)
--
-- One database. Every state change and its event commit together (CRS §4.2),
-- which is only possible because they live here together (CRS §4.1).
-- ============================================================================

-- ── Connection setup ────────────────────────────────────────────────────────
-- CRS §4.3. foreign_keys is PER-CONNECTION in SQLite and must be set on every
-- connection the pool hands out, not once at startup.

PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;


-- ── Migrations ──────────────────────────────────────────────────────────────
-- CRS §4.4. Forward-only, idempotent. The runtime refuses to start against a
-- version it does not understand rather than corrupting it.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    applied_at  INTEGER NOT NULL
);


-- ── Global event sequence ───────────────────────────────────────────────────
-- CRS §3.1. A single counter row, incremented inside the same transaction as
-- the event insert. NOT AUTOINCREMENT: a rolled-back AUTOINCREMENT burns its
-- value and leaves a permanent gap, which destroys the client's ability to
-- tell "nothing happened" from "I missed something".
--
-- This serializes event appends on one row. Costs nothing — WAL already
-- permits exactly one writer.

CREATE TABLE IF NOT EXISTS event_seq (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    value             INTEGER NOT NULL DEFAULT 0,
    min_retained_seq  INTEGER NOT NULL DEFAULT 0   -- CRS §3.7.2
);
INSERT OR IGNORE INTO event_seq (id, value, min_retained_seq) VALUES (1, 0, 0);


-- ── Conversations ───────────────────────────────────────────────────────────
-- Owns turns. Owns nothing else. Deleting one must not delete the workspaces
-- or assets it referenced (CRS §2.1).

CREATE TABLE IF NOT EXISTS folders (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT    PRIMARY KEY,          -- conv_<uuid7>
    title       TEXT    NOT NULL DEFAULT 'New Chat',
    folder_id   TEXT    REFERENCES folders(id) ON DELETE SET NULL,
    incognito   INTEGER NOT NULL DEFAULT 0,   -- immutable after creation
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    archived_at INTEGER,
    pinned_at   INTEGER                       -- when, not whether: pins keep their order
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated
    ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_folder
    ON conversations(folder_id) WHERE folder_id IS NOT NULL;


-- ── Turns ───────────────────────────────────────────────────────────────────
-- The abstraction V1 lacks entirely. One user message, one response, every
-- job that response required.

CREATE TABLE IF NOT EXISTS turns (
    id                  TEXT    PRIMARY KEY,   -- turn_<uuid7>
    conversation_id     TEXT    NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    seq_in_conversation INTEGER NOT NULL,
    status              TEXT    NOT NULL,
    error_code          TEXT,
    error_message       TEXT,
    error_retryable     INTEGER,
    retry_of_turn_id    TEXT    REFERENCES turns(id) ON DELETE SET NULL,
    created_at          INTEGER NOT NULL,
    completed_at        INTEGER,

    -- CRS §5.1. `building_context` and `thinking` are deliberately distinct
    -- from `streaming`: "assembling the prompt", "waiting for the first token"
    -- and "tokens arriving" are three different things to a user, and
    -- collapsing them is how V1 ended up unable to say anything more useful
    -- than a global spinner. `awaiting_input` is required by the permission
    -- flow, which otherwise has no state to park in.
    CHECK (status IN ('queued','building_context','thinking','streaming','tool_running',
                      'awaiting_input','completed','failed','cancelled')),
    -- CRS §5.2.3: terminal turns carry a completion time; live ones do not
    CHECK ((status IN ('completed','failed','cancelled')) = (completed_at IS NOT NULL)),
    UNIQUE (conversation_id, seq_in_conversation)
);

CREATE INDEX IF NOT EXISTS idx_turns_conversation
    ON turns(conversation_id, seq_in_conversation);
-- Boot sweep (CRS §10.3.2) reads exactly this.
CREATE INDEX IF NOT EXISTS idx_turns_live
    ON turns(status) WHERE status NOT IN ('completed','failed','cancelled');


-- ── Messages ────────────────────────────────────────────────────────────────
-- `text` is what the user sees. `model_text` is what was actually sent to the
-- model (extracted file contents, injected context). V1 conflated these and
-- the file-chip display bug came out of it.

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT    PRIMARY KEY,           -- msg_<uuid7>
    turn_id     TEXT    NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL CHECK (role IN ('user','assistant','system')),
    text        TEXT    NOT NULL,
    model_text  TEXT,
    partial     INTEGER NOT NULL DEFAULT 0,    -- CRS §9.3: cancelled turns keep their text
    blocks      TEXT,                          -- JSON: tool_call / tool_result / cards
    usage       TEXT,                          -- JSON: tokens, model, duration
    created_at  INTEGER NOT NULL,

    -- CRS §2.2: at most one assistant message per turn
    UNIQUE (turn_id, role)
);

CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);

-- ── Assets ──────────────────────────────────────────────────────────────────
-- Content-addressed. Ingestion is a job, not inline work in an HTTP handler.
-- Defined before jobs and turn_assets because both reference it.

CREATE TABLE IF NOT EXISTS assets (
    id             TEXT    PRIMARY KEY,        -- asset_<uuid7>
    kind           TEXT    NOT NULL,
    source         TEXT    NOT NULL,
    original_name  TEXT    NOT NULL,
    path           TEXT    NOT NULL,           -- appdata/assets/<sha256[0:2]>/<sha256>
    sha256         TEXT    NOT NULL,
    bytes          INTEGER NOT NULL,
    mime           TEXT,
    status         TEXT    NOT NULL DEFAULT 'ingesting',
    extracted_text TEXT,
    page_count     INTEGER,
    metadata       TEXT,                       -- JSON: ocr_required, truncated, …
    created_at     INTEGER NOT NULL,
    ingested_at    INTEGER,

    CHECK (kind IN ('pdf','image','audio','video','text','code','screenshot',
                    'transcript','archive','other')),
    CHECK (source IN ('upload','screenshot','recording','watch_folder','tool_output')),
    CHECK (status IN ('ingesting','ready','failed'))
);

-- CRS §2.6: identical bytes deduplicate to one asset.
CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_sha ON assets(sha256);
CREATE INDEX IF NOT EXISTS idx_assets_status
    ON assets(status) WHERE status != 'ready';

CREATE TABLE IF NOT EXISTS asset_chunks (
    id          TEXT    PRIMARY KEY,
    asset_id    TEXT    NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    page        INTEGER,
    metadata    TEXT,
    UNIQUE (asset_id, ordinal)
);

CREATE TABLE IF NOT EXISTS asset_embeddings (
    chunk_id    TEXT    PRIMARY KEY REFERENCES asset_chunks(id) ON DELETE CASCADE,
    model       TEXT    NOT NULL,
    dim         INTEGER NOT NULL,
    vector      BLOB    NOT NULL,
    created_at  INTEGER NOT NULL
);

-- Asset lineage. A workspace gets version history and revert; an asset got
-- neither, so "regenerate that deck" silently replaced the old one with no way
-- back. This closes that asymmetry.
--
-- It stores no bytes, unlike workspace_files, and does not need to: assets are
-- content-addressed and deduplicated by sha256, so a regenerated deck is
-- already a distinct row at its own path. Superseding is therefore a matter of
-- recording the order, not of copying anything.
--
-- asset_id is deliberately NOT unique. Reverting appends a new version that
-- points back at an existing asset — history is append-only, the same rule
-- workspace_versions follows, so "undo that" is itself undoable.
CREATE TABLE IF NOT EXISTS asset_versions (
    lineage_id         TEXT    NOT NULL,
    version            INTEGER NOT NULL,
    asset_id           TEXT    NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    summary            TEXT,
    created_by_turn_id TEXT    REFERENCES turns(id) ON DELETE SET NULL,
    created_at         INTEGER NOT NULL,
    PRIMARY KEY (lineage_id, version)
);

-- Asset → lineage. Not unique: an asset appears twice in its lineage once it
-- has been reverted to.
CREATE INDEX IF NOT EXISTS idx_asset_versions_asset ON asset_versions(asset_id);

-- Turn ↔ asset references. A turn references assets; it does not own them.
CREATE TABLE IF NOT EXISTS turn_assets (
    turn_id   TEXT NOT NULL REFERENCES turns(id)   ON DELETE CASCADE,
    asset_id  TEXT NOT NULL REFERENCES assets(id)  ON DELETE CASCADE,
    PRIMARY KEY (turn_id, asset_id)
);


-- ── Jobs ────────────────────────────────────────────────────────────────────
-- turn_id NULL = ambient or maintenance work (CRS §2.2).

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT    PRIMARY KEY,      -- job_<uuid7>
    turn_id          TEXT    REFERENCES turns(id) ON DELETE CASCADE,
    kind             TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    idempotent       INTEGER NOT NULL DEFAULT 0,
    cancellable      INTEGER NOT NULL DEFAULT 1,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    priority         INTEGER NOT NULL DEFAULT 0,
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 1,
    payload          TEXT    NOT NULL,         -- JSON
    result           TEXT,                     -- JSON
    result_ref       TEXT    REFERENCES assets(id) ON DELETE SET NULL,  -- CRS §6.2.4
    error            TEXT,
    created_at       INTEGER NOT NULL,
    started_at       INTEGER,
    finished_at      INTEGER,

    -- Namespaced by owning service (chat.reply, tool.python, asset.ocr…), so a
    -- new job kind is a registration inside a service rather than a schema
    -- migration — while still making an unnamespaced kind impossible.
    CHECK (kind GLOB 'chat.*' OR kind GLOB 'tool.*' OR kind GLOB 'asset.*'
        OR kind GLOB 'context.*' OR kind GLOB 'workspace.*'
        OR kind GLOB 'memory.*' OR kind GLOB 'maintenance.*'),
    CHECK (status IN ('queued','running','completed','failed','cancelled')),
    -- CRS §6.2.3: automatic retry is only legal for idempotent jobs
    CHECK (max_attempts = 1 OR idempotent = 1)
);

-- The scheduler's hot path.
CREATE INDEX IF NOT EXISTS idx_jobs_queued
    ON jobs(priority DESC, created_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_jobs_turn      ON jobs(turn_id);
-- Boot sweep (CRS §10.3.1).
CREATE INDEX IF NOT EXISTS idx_jobs_running   ON jobs(status) WHERE status = 'running';


-- ── Events ──────────────────────────────────────────────────────────────────
-- Append-only. Committed before delivery (CRS §3.4). Recovery mechanism, NOT
-- the history — history is reconstructable from the tables above with no
-- reference to this one (CRS §3.3).
--
-- Ambient events are never written here (CRS §11.1.2).

CREATE TABLE IF NOT EXISTS events (
    sequence        INTEGER PRIMARY KEY,       -- global, gapless, from event_seq
    event_id        TEXT    NOT NULL UNIQUE,   -- evt_<uuid7>
    ts              INTEGER NOT NULL,          -- informational only (CRS §13.3.2)
    scope           TEXT    NOT NULL,
    conversation_id TEXT    REFERENCES conversations(id) ON DELETE CASCADE,
    turn_id         TEXT    REFERENCES turns(id)         ON DELETE CASCADE,
    kind            TEXT    NOT NULL,
    payload         TEXT    NOT NULL,          -- JSON

    CHECK (scope IN ('conversation','ambient','system')),
    -- CRS §3.2: conversation-scoped events must name their conversation
    CHECK ((scope = 'conversation') = (conversation_id IS NOT NULL))
);

-- The reconnect query (CRS §8.1/§8.2): everything after the cursor, filtered
-- to the conversations this client has open.
CREATE INDEX IF NOT EXISTS idx_events_replay
    ON events(sequence, conversation_id);
CREATE INDEX IF NOT EXISTS idx_events_turn
    ON events(turn_id) WHERE turn_id IS NOT NULL;


-- ── Workspaces ──────────────────────────────────────────────────────────────
-- Generated artifacts stop living inside message text. Versioned, because
-- "only modify line 742" and "undo that" are what break V1 today.
--
-- ON DELETE SET NULL on origin_turn_id, not CASCADE: a workspace must survive
-- the deletion of the conversation that produced it (CRS §2.5).

CREATE TABLE IF NOT EXISTS workspaces (
    id              TEXT    PRIMARY KEY,       -- ws_<uuid7>
    kind            TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    origin_turn_id  TEXT    REFERENCES turns(id) ON DELETE SET NULL,
    current_version INTEGER NOT NULL DEFAULT 1,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,

    CHECK (kind IN ('react','python','markdown','html','notebook','doc','shell'))
);

CREATE TABLE IF NOT EXISTS workspace_versions (
    workspace_id       TEXT    NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    version            INTEGER NOT NULL,
    created_by_turn_id TEXT    REFERENCES turns(id) ON DELETE SET NULL,
    summary            TEXT,
    created_at         INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, version)
);

CREATE TABLE IF NOT EXISTS workspace_files (
    workspace_id TEXT    NOT NULL,
    version      INTEGER NOT NULL,
    path         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    PRIMARY KEY (workspace_id, version, path),
    FOREIGN KEY (workspace_id, version)
        REFERENCES workspace_versions(workspace_id, version) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS turn_workspaces (
    turn_id      TEXT NOT NULL REFERENCES turns(id)      ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    PRIMARY KEY (turn_id, workspace_id)
);


-- ── Execution sessions ──────────────────────────────────────────────────────
-- The Sandbox Manager is a KERNEL service, not a helper under the tool
-- service: tools do not execute code, they request execution. Every run is an
-- object for the same reason a Turn is — a subprocess that isn't addressable
-- cannot be cancelled, attributed, or shown to the user afterwards.
--
-- workspace_id is ON DELETE SET NULL: an execution's logs and snapshot stay
-- meaningful after the workspace it touched is gone.

CREATE TABLE IF NOT EXISTS execution_sessions (
    id           TEXT    PRIMARY KEY,          -- exec_<uuid7>
    job_id       TEXT    REFERENCES jobs(id)       ON DELETE CASCADE,
    turn_id      TEXT    REFERENCES turns(id)      ON DELETE CASCADE,
    workspace_id TEXT    REFERENCES workspaces(id) ON DELETE SET NULL,
    runtime      TEXT    NOT NULL,
    manifest     TEXT    NOT NULL,             -- JSON permission manifest
    status       TEXT    NOT NULL,
    backend      TEXT,                         -- appcontainer | windows
    exit_code    INTEGER,
    stdout       TEXT,
    stderr       TEXT,
    snapshot     TEXT,                         -- JSON: created/modified/deleted
    session_dir  TEXT,
    code         TEXT,                         -- the source that actually ran
    error        TEXT,
    created_at   INTEGER NOT NULL,
    started_at   INTEGER,
    finished_at  INTEGER,

    CHECK (runtime IN ('python','node','shell')),
    CHECK (status IN ('created','running','completed','failed','cancelled','destroyed'))
);

CREATE INDEX IF NOT EXISTS idx_exec_job  ON execution_sessions(job_id);
CREATE INDEX IF NOT EXISTS idx_exec_turn ON execution_sessions(turn_id);
-- Boot sweep: a session left running is a process that outlived its runtime.
CREATE INDEX IF NOT EXISTS idx_exec_live
    ON execution_sessions(status) WHERE status IN ('created','running');


-- ── Knowledge graph ─────────────────────────────────────────────────────────
-- V2.2. The graph is built BEFORE the user asks, incrementally, and the model
-- queries it rather than generating it. That inversion is the whole point: a
-- 1.5B model can use a rich graph it could never have built.
--
-- V1 had a graph too (server.py /api/graph) but it was a picture, not an index:
-- recomputed from scratch on every request, never persisted, edges untyped, and
-- read by nothing but a <canvas>. The chat model never once saw it. What makes
-- this one different is the retrieval path, not the node/edge shape.
--
-- `scope` is the resolution namespace: an asset id, a workspace id, or '*' for
-- global. It is a plain NOT NULL string rather than a nullable asset_id because
-- SQLite treats NULLs as distinct in a UNIQUE index, so a nullable column would
-- let every global entity insert a duplicate of itself forever.

-- `key` is Graphify's own node id — a stable slug derived from path + symbol
-- (`primnox2_assets_service_ingest_bytes`). It is NOT re-normalised here: by
-- the time a node reaches this table Graphify's resolver chain has already
-- decided what is the same symbol, and a second normalisation pass on top of a
-- resolved identity can only merge things that were deliberately kept apart.
-- Reusing it also makes re-import an idempotent upsert rather than a diff.
--
-- source_file / source_location are first-class columns, not metadata JSON:
-- they are the citation, which is the entire reason a graph hit is useful.

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id              TEXT    PRIMARY KEY,       -- node_<uuid7>
    label           TEXT    NOT NULL,          -- display form: `ingest_bytes()`
    key             TEXT    NOT NULL,          -- Graphify node id
    type            TEXT    NOT NULL,
    file_type       TEXT,                      -- code | rationale | document
    source_file     TEXT,
    source_location TEXT,                      -- 'L58'
    scope           TEXT    NOT NULL,          -- 'conv:<id>' | 'ws:<id>' | 'asset:<id>' | '*'
    asset_id        TEXT    REFERENCES assets(id)        ON DELETE CASCADE,
    workspace_id    TEXT    REFERENCES workspaces(id)    ON DELETE CASCADE,
    -- A conversation's own graph. Set for scope='conv:<id>' so the graph is
    -- deleted by the same foreign key that deletes the conversation: a chat and
    -- what was derived from it must not be able to outlive each other.
    conversation_id TEXT    REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id       TEXT    REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    salience        REAL    NOT NULL DEFAULT 0,   -- conversation graphs: mention count
    metadata        TEXT,                      -- JSON
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,

    CHECK (type IN ('file','module','section','class','function',
                    'rationale','entity','concept',
                    -- conversation-graph kinds
                    'decision','tool','asset')),
    UNIQUE (scope, key)
);

CREATE INDEX IF NOT EXISTS idx_knodes_conv
    ON knowledge_nodes(conversation_id) WHERE conversation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_knodes_scope  ON knowledge_nodes(scope, type);
CREATE INDEX IF NOT EXISTS idx_knodes_key    ON knowledge_nodes(key);
CREATE INDEX IF NOT EXISTS idx_knodes_asset  ON knowledge_nodes(asset_id) WHERE asset_id IS NOT NULL;

-- `confidence` is a tier, not a float, and the vocabulary is Graphify's own
-- (ARCHITECTURE.md "Confidence labels") so mirroring its output is lossless:
--   EXTRACTED — explicitly stated in the source: an import, a direct call.
--   INFERRED  — a reasonable deduction: call-graph second pass, co-occurrence.
--   AMBIGUOUS — uncertain; surfaced for human review rather than trusted.
-- A tier is also what makes eviction possible. Without a floor to discard
-- against, the graph only ever grows.

-- `context` is the relation SITE kind — call, import, decorator, parameter_type,
-- return_type, generic_arg. Graphify's query surface filters on it, so it is a
-- column rather than metadata: "who calls X" and "who type-hints X" are
-- different questions over the same pair of nodes.
--
-- source_file/source_location here are the site of the RELATION, not of either
-- endpoint's definition — so "who calls ingest_bytes" cites the call line, not
-- the caller's def line.

CREATE TABLE IF NOT EXISTS knowledge_edges (
    id               TEXT    PRIMARY KEY,      -- edge_<uuid7>
    source_id        TEXT    NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target_id        TEXT    NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relation         TEXT    NOT NULL,         -- calls | contains | imports | rationale_for | …
    -- NOT NULL with an empty-string default, never nullable: `context` is part
    -- of the uniqueness key below, and SQLite treats NULLs as DISTINCT in a
    -- UNIQUE index — a nullable column would let the same contextless edge
    -- insert without limit, which is exactly the duplicate this key prevents.
    context          TEXT    NOT NULL DEFAULT '',
    confidence       TEXT    NOT NULL,
    confidence_score REAL,
    weight           REAL    NOT NULL DEFAULT 1.0,
    source_file      TEXT,
    source_location  TEXT,
    chunk_id         TEXT    REFERENCES asset_chunks(id) ON DELETE SET NULL,
    created_at       INTEGER NOT NULL,

    CHECK (confidence IN ('EXTRACTED','INFERRED','AMBIGUOUS')),
    -- A node that calls itself carries no retrieval value — the neighbour walk
    -- already has the node. Recursive functions are the common source; the
    -- importer drops these rather than letting one crash a whole build.
    CHECK (source_id != target_id),
    UNIQUE (source_id, target_id, relation, context)
);

CREATE INDEX IF NOT EXISTS idx_kedges_source ON knowledge_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_kedges_target ON knowledge_edges(target_id);

-- How a graph hit becomes prose. A query walks nodes, then follows mentions
-- back to the chunks that produced them — the model receives paragraphs with
-- citations, never an adjacency list.
CREATE TABLE IF NOT EXISTS entity_mentions (
    node_id   TEXT    NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    chunk_id  TEXT    NOT NULL REFERENCES asset_chunks(id)    ON DELETE CASCADE,
    count     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (node_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_mentions_chunk ON entity_mentions(chunk_id);

-- Entity resolution. `PaymentGateway`, `payment gateway` and `the gateway` are
-- one concept; without this they are three disconnected subgraphs, which is
-- worse than noise because it is confidently fragmented.
CREATE TABLE IF NOT EXISTS node_aliases (
    alias_key TEXT NOT NULL,
    scope     TEXT NOT NULL,
    node_id   TEXT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (scope, alias_key)
);

CREATE TABLE IF NOT EXISTS graph_clusters (
    id         TEXT    PRIMARY KEY,            -- clus_<uuid7>
    label      TEXT    NOT NULL,
    scope      TEXT    NOT NULL,
    size       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_members (
    cluster_id TEXT NOT NULL REFERENCES graph_clusters(id)  ON DELETE CASCADE,
    node_id    TEXT NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, node_id)
);

-- Incremental rebuild. Editing one file must not re-extract the other 599
-- chunks. The hash says whether a chunk's text actually changed; the bitmask
-- says which passes have already run over it.
CREATE TABLE IF NOT EXISTS graph_chunk_state (
    chunk_id   TEXT    PRIMARY KEY REFERENCES asset_chunks(id) ON DELETE CASCADE,
    text_hash  TEXT    NOT NULL,
    pass_mask  INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);


-- ── Memory ──────────────────────────────────────────────────────────────────
-- Carried over from V1 largely unchanged; re-homed into primnox.db so a
-- memory write and its event commit together.

CREATE TABLE IF NOT EXISTS memories (
    id              TEXT    PRIMARY KEY,
    text            TEXT    NOT NULL,
    category        TEXT,
    provenance      TEXT,                      -- inferred_chat | explicit | imported
    conversation_id TEXT    REFERENCES conversations(id) ON DELETE SET NULL,
    turn_id         TEXT    REFERENCES turns(id)         ON DELETE SET NULL,
    embedding       BLOB,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    deleted_at      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_memories_live
    ON memories(created_at DESC) WHERE deleted_at IS NULL;


-- ── Settings ────────────────────────────────────────────────────────────────
-- Secrets do NOT live here. They stay in keyring / the vault.

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,                  -- JSON
    updated_at INTEGER NOT NULL
);


-- ============================================================================
-- Reference queries
-- ============================================================================

-- Reconnect replay (CRS §8.1). :convs is the client's open conversation list.
--
--   SELECT sequence, event_id, ts, scope, conversation_id, turn_id, kind, payload
--     FROM events
--    WHERE sequence > :last_event_seen
--      AND (scope = 'system' OR conversation_id IN (:convs))
--    ORDER BY sequence
--    LIMIT 5000;
--
-- Then: SELECT value FROM event_seq WHERE id = 1;  → sync.complete { head }.
-- The client sets its cursor to head, not to the last row returned — filtered
-- events are not missing, their effects are in the state tables (CRS §3.3.4).

-- Turn completion (CRS §4.2). One transaction, or neither half happens.
--
--   BEGIN IMMEDIATE;
--     UPDATE event_seq SET value = value + 1 WHERE id = 1;
--     UPDATE turns SET status='completed', completed_at=:now WHERE id=:turn;
--     INSERT INTO messages (...) VALUES (...);
--     INSERT INTO events (sequence, event_id, ts, scope, conversation_id,
--                         turn_id, kind, payload)
--     VALUES ((SELECT value FROM event_seq WHERE id=1), :evt, :now,
--             'conversation', :conv, :turn, 'turn.completed', :payload);
--   COMMIT;
--   -- sockets are written AFTER commit, never inside the transaction

-- Boot sweep (CRS §10.3). No turn may stay non-terminal across a restart.
--
--   UPDATE jobs SET status='queued', started_at=NULL
--    WHERE status='running' AND idempotent=1;
--   UPDATE jobs SET status='failed', error='interrupted by shutdown',
--                   finished_at=:now
--    WHERE status='running' AND idempotent=0;
--   UPDATE turns SET status='failed', error_code='internal',
--                    error_message='interrupted by shutdown', completed_at=:now
--    WHERE status NOT IN ('completed','failed','cancelled');
