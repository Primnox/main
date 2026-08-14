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
    archived_at INTEGER
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
