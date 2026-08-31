-- Primnox Web — the single runtime database (CRS/1.0-W §4.1).
-- Replaces desktop's primnox.db. Payload columns are bytea ciphertext,
-- encrypted client-side with the user's DEK; the database has no function
-- that can read them. Envelope columns stay cleartext for ordering /
-- filtering / replay (CRS/1.0-W §4.2).
--
-- House rules (see .claude/rules/database): no foreign-key constraints,
-- TEXT not VARCHAR, soft delete via deleted_at, uuid_generate_v4().
-- Runtime-object ids are app-generated "<prefix>_<uuidv7>" strings (CRS §1.1)
-- and are TEXT primary keys; infra rows use uuid.

create extension if not exists "uuid-ossp";

-- ── bookkeeping ──────────────────────────────────────────────────────────

create table schema_migrations (
  version    text primary key,
  applied_at timestamptz not null default now()
);
insert into schema_migrations (version) values ('0001_init');

-- CRS §3.1 — ONE global, gapless sequence for the whole runtime. Not per user.
-- Incremented inside the same transaction as each event insert. SERIAL/IDENTITY
-- must never be used here: a rolled-back allocation burns a value and a client
-- then cannot tell "nothing happened" from "I missed something".
create table event_seq (
  id    smallint primary key default 1,
  value bigint   not null    default 0,
  constraint event_seq_singleton check (id = 1)
);
insert into event_seq (id, value) values (1, 0);

create table min_retained_seq (
  id    smallint primary key default 1,
  value bigint   not null    default 0,
  constraint min_retained_seq_singleton check (id = 1)
);
insert into min_retained_seq (id, value) values (1, 0);

-- ── identity / device ───────────────────────────────────────────────────

create table profiles (
  user_id    uuid primary key,               -- = auth.uid()
  handle     text,
  created_at timestamptz not null default now()
);

create table devices (
  id           uuid primary key default uuid_generate_v4(),
  user_id      uuid not null,
  label        text,
  created_at   timestamptz not null default now(),
  last_seen_at timestamptz,
  revoked_at   timestamptz
);
create index idx_devices_user on devices (user_id) where revoked_at is null;

create table sessions (
  id         uuid primary key default uuid_generate_v4(),
  user_id    uuid not null,
  device_id  uuid not null,
  issued_at  timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);
create index idx_sessions_user on sessions (user_id) where revoked_at is null;

-- ── vault (CRS/1.0-W §5, §W1) ───────────────────────────────────────────
-- Everything here is inert without the passphrase or the recovery mnemonic.
-- The KDF salt is not a secret. wrapped_dek / wrapped_dek_recovery are the
-- DEK sealed under the KEK / recovery-KEK respectively.

create table vault (
  user_id              uuid primary key,
  kdf                  jsonb  not null,       -- {alg,m,t,p,saltB64}
  wrapped_dek          jsonb  not null,       -- {v,alg,iv,ct}
  wrapped_dek_recovery jsonb,                 -- {v,alg,iv,ct} — set when recovery enabled
  recovery_salt_b64    text,                  -- HKDF salt for recovery-KEK; never rotated
  keys_ct              jsonb,                 -- provider API keys, sealed under the DEK (§D3)
  key_version          integer not null default 1,
  updated_at           timestamptz not null default now()
);

-- ── conversation model (CRS §2) ─────────────────────────────────────────

create table folders (
  id         text primary key,               -- fld_<uuidv7>
  user_id    uuid not null,
  parent_id  text,
  title_ct   jsonb not null,                  -- sealed
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  deleted_at timestamptz
);
create index idx_folders_user on folders (user_id) where deleted_at is null;

create table conversations (
  id         text primary key,               -- conv_<uuidv7>
  user_id    uuid not null,
  folder_id  text,
  title_ct   jsonb,                           -- sealed; null until first autotitle
  incognito  boolean not null default false, -- immutable after creation (CRS §2.1)
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  archived_at timestamptz,
  deleted_at timestamptz
);
create index idx_conversations_user on conversations (user_id) where deleted_at is null;

create table turns (
  id                text primary key,         -- turn_<uuidv7>
  conversation_id   text not null,
  user_id           uuid not null,
  seq_in_conversation integer not null,
  status            text not null,            -- CRS §5.1 TurnStatus
  error_code        text,
  error_ct          jsonb,                    -- sealed {message,retryable,...}
  origin_device_id  uuid,                     -- CRS/1.0-W §4.4
  created_at        timestamptz not null default now(),
  completed_at      timestamptz
);
create index idx_turns_conversation on turns (conversation_id, seq_in_conversation);
create index idx_turns_open on turns (user_id) where status not in ('completed','failed','cancelled');

create table messages (
  id         text primary key,               -- msg_<uuidv7>
  turn_id    text not null,
  user_id    uuid not null,
  role       text not null,                  -- 'user' | 'assistant'
  body_ct    jsonb not null,                 -- sealed, AAD = 'msg:<id>/body'
  created_at timestamptz not null default now()
);
create index idx_messages_turn on messages (turn_id);

-- ── jobs (CRS §2.3, §6) ─────────────────────────────────────────────────

create table jobs (
  id               text primary key,          -- job_<uuidv7>
  turn_id          text,                       -- null = ambient / maintenance
  user_id          uuid not null,
  kind             text not null,              -- chat|tool|skill|asset|memory|maintenance
  status           text not null,              -- queued|running|completed|failed|cancelled
  cancel_requested boolean not null default false,
  attempts         integer not null default 0,
  payload_ct       jsonb,                      -- sealed
  result_ct        jsonb,                      -- sealed
  error            text,
  created_at       timestamptz not null default now(),
  started_at       timestamptz,
  finished_at      timestamptz
);
create index idx_jobs_turn on jobs (turn_id);
create index idx_jobs_runnable on jobs (user_id, status) where status in ('queued','running');

-- ── the event log (CRS §3, CRS/1.0-W §4.1–§4.3) ─────────────────────────
-- One row per event. INSERT always happens inside the event_seq bump txn
-- (see server/src/events.ts). payload_ct is opaque ciphertext; the server
-- never inspects it. ts is epoch ms (CRS §13.3.1).

create table events (
  event_id        text primary key,           -- evt_<uuidv7>
  sequence        bigint not null unique,      -- global, gapless, strictly increasing
  ts              bigint not null,             -- epoch ms
  scope           text not null,               -- conversation | ambient | system
  conversation_id text,
  turn_id         text,
  kind            text not null,
  user_id         uuid not null,
  payload_ct      jsonb not null               -- sealed {v,alg,iv,ct}
);
create index idx_events_user_seq on events (user_id, sequence);
create index idx_events_conversation on events (conversation_id, sequence);

-- ── assets / workspaces / canvas (CRS §2.5, §2.6, CRS/1.0-W §4.10, §12) ─

create table assets (
  id                text primary key,          -- asset_<uuidv7>
  user_id           uuid not null,
  kind              text not null,
  source            text not null,
  sha256            text not null,
  bytes             bigint not null,
  status            text not null,             -- ingesting | ready | failed
  extracted_text_ct jsonb,                     -- sealed
  page_count        integer,
  metadata_ct       jsonb,                     -- sealed
  created_at        timestamptz not null default now()
);
create index idx_assets_user on assets (user_id);
create index idx_assets_sha on assets (user_id, sha256);

create table turn_assets (
  turn_id  text not null,
  asset_id text not null,
  primary key (turn_id, asset_id)
);

create table workspaces (
  id              text primary key,            -- ws_<uuidv7>
  user_id         uuid not null,
  kind            text not null,
  title_ct        jsonb not null,              -- sealed
  origin_turn_id  text not null,
  current_version integer not null default 1,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz
);
create index idx_workspaces_user on workspaces (user_id);

create table workspace_versions (
  workspace_id       text not null,
  version            integer not null,
  files_ct           jsonb not null,           -- sealed { path -> content }
  created_by_turn_id text not null,
  created_at         timestamptz not null default now(),
  primary key (workspace_id, version)
);

-- Ordered, encrypted CRDT deltas. The server stores and orders; it never merges.
create table canvas_updates (
  id           text primary key,               -- cu_<uuidv7>
  workspace_id text not null,
  user_id      uuid not null,
  seq          bigint not null,                -- per-workspace order
  update_ct    jsonb not null,                 -- sealed CRDT update blob
  created_at   timestamptz not null default now()
);
create index idx_canvas_updates_ws on canvas_updates (workspace_id, seq);

-- ── memory (CRS/1.0-W §11) ─────────────────────────────────────────────

create table memories (
  id             text primary key,             -- mem_<uuidv7>
  user_id        uuid not null,
  kind           text not null,                -- preference|fact|project|relationship|goal|working|historical
  text_ct        jsonb not null,               -- sealed
  embedding_ct   jsonb not null,               -- sealed float32[] blob
  salience       real not null default 0.5,
  created_at     timestamptz not null default now(),
  last_used_at   timestamptz,
  expires_at     timestamptz,
  source_turn_id text,
  deleted_at     timestamptz
);
create index idx_memories_user on memories (user_id) where deleted_at is null;

-- ── usage / integrations ───────────────────────────────────────────────

create table usage (
  id            uuid primary key default uuid_generate_v4(),
  user_id       uuid not null,
  turn_id       text,
  provider      text not null,
  model         text not null,
  input_tokens  integer not null default 0,
  output_tokens integer not null default 0,
  latency_ms    integer,
  created_at    timestamptz not null default now()
);
create index idx_usage_user_time on usage (user_id, created_at);

create table github_connection (
  user_id         uuid primary key,
  installation_id text not null,
  repo_id         text,
  repo_full_name  text,
  status          text not null default 'connected',
  connected_at    timestamptz not null default now()
);

create table sync_state (
  user_id         uuid primary key,
  repo_head       text,
  last_synced_seq bigint not null default 0,
  updated_at      timestamptz not null default now()
);

-- ── Row-Level Security ─────────────────────────────────────────────────
-- Every user-scoped table: a row is visible only to its owner. Render
-- connects with the service role (bypasses RLS) to assign sequence and
-- append; clients read (and receive Realtime fan-out) only their own rows.

do $$
declare t text;
begin
  foreach t in array array[
    'profiles','devices','sessions','vault','folders','conversations','turns',
    'messages','jobs','events','assets','turn_assets','workspaces',
    'workspace_versions','canvas_updates','memories','usage',
    'github_connection','sync_state'
  ]
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- user_id-keyed tables: owner-only for all commands
do $$
declare t text;
begin
  foreach t in array array[
    'profiles','devices','sessions','vault','folders','conversations','turns',
    'messages','jobs','events','assets','workspaces','canvas_updates',
    'memories','usage','github_connection','sync_state'
  ]
  loop
    execute format(
      'create policy %I_owner on %I for all using (user_id = auth.uid()) with check (user_id = auth.uid())',
      t, t
    );
  end loop;
end $$;

-- child tables without a user_id column: gate through the parent
create policy turn_assets_owner on turn_assets for all
  using (exists (select 1 from turns where turns.id = turn_assets.turn_id and turns.user_id = auth.uid()))
  with check (exists (select 1 from turns where turns.id = turn_assets.turn_id and turns.user_id = auth.uid()));

create policy workspace_versions_owner on workspace_versions for all
  using (exists (select 1 from workspaces w where w.id = workspace_versions.workspace_id and w.user_id = auth.uid()))
  with check (exists (select 1 from workspaces w where w.id = workspace_versions.workspace_id and w.user_id = auth.uid()));

-- ── Realtime fan-out (CRS/1.0-W §4.4, resolved Q8) ─────────────────────
-- Clients subscribe to events inserts; RLS above scopes the stream per user.
alter publication supabase_realtime add table events;
