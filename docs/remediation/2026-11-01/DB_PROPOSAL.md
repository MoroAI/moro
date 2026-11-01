# MoroAI Database Deep Dive — Proposal

Date: 2026-11-01 | Status: proposal only (no engine swap in code) | Scope: read-only analysis

## 1. Current state (inspected evidence)

Six independent SQLite databases, all file-local, no server process:

| # | File | Owner module | Tables | WAL | Versions |
|---|------|--------------|--------|-----|----------|
| 1 | `data/production_logs.db` | `moro/flywheel/storage/schema.py` | `inference_logs`, `preference_pairs`, `dpo_epochs`, `flywheel_state` (+ `webhook_requests` created ad-hoc by `flywheel/webhook/receiver.py:79`) | yes | none |
| 2 | `.moro/db.sqlite` | `moro/storage/db.py` | `projects`, `dataset_sources`, `dataset_versions`, `dataset_snapshots`, `runs`, `eval_runs`, `artifacts` | yes | `PRAGMA user_version=1`, rejects newer |
| 3 | `.moro/analytics.db` | `moro/analytics/schema.py` + `tracker.py` | `experiments`, `hyperparameters`, `metrics`, `eval_results`, `model_outputs`, `recommendations` | yes | none |
| 4 | `.moro/state.db` | `moro/state/schema.py` + `manager.py` | `nodes`, `edges`, `model_registry`, `operation_log`, `service_state` | yes | none |
| 5 | `.moro/registry.db` | `moro/registry/manager.py` | `registered_models` | **no** (plain `sqlite3.connect`) | none |
| 6 | `.moro/state_graph.db` | `moro/storage/state_graph.py` | `lineage_nodes` | **no** (plain `sqlite3.connect`) | none |

Environment: SQLite 3.54.1 (system python3). `test_flywheel_storage.py` passes (2 passed);
`test_flywheel_webhook.py` socket-bind tests fail in this sandbox with `PermissionError`
(socket bind blocked) — unrelated to the DB layer.

### 1.1 Fragmentation / duplication (real findings)

- **Two registries**: `registry.db.registered_models` (`registry/manager.py`) overlaps
  `state.db.model_registry` (`state/schema.py`). Dashboard reads `state.db`
  (`dashboard/mission_control.py:303`); CLI registry commands use `registry.db`.
  A model registered in one is invisible in the other.
- **Two lineage graphs**: `state_graph.db.lineage_nodes` (minimal: id/parent/name/json)
  overlaps `state.db` nodes/edges. `StateGraphManager` and `StateManager` do not share data.
- **Schema drift**: `webhook_requests` is created by the receiver at ingest time, not in
  `PRODUCTION_LOG_SCHEMA`. Any tool that calls `initialize_production_db` alone gets a DB
  without that table.

### 1.2 Concurrency — what is solid, what is missing

Solid (keep in any option):

- `BEGIN IMMEDIATE` wraps webhook ingest check-then-insert (`receiver.py:81`) and epoch
  publication (`orchestrator.py:233`) — correct single-writer serialization for SQLite.
- Webhook idempotency: `request_id = sha256(sender:key)`, body digest compare, 409 on
  key-reuse-with-different-body (`receiver.py:71-88`). Correct semantics.
- Epoch publication verifies every source row still unprocessed inside the transaction,
  writes the dataset file with `O_EXCL` + `fsync`, inserts epoch+pairs, marks logs
  processed, commits; on failure rolls back and unlinks only the file it created
  (`orchestrator.py:224-280`). `mark_processed` also guards with `AND is_processed = 0`.
- Training mutual exclusion via `fcntl.flock` on `.moro/training.execution.lock`
  (`training/locking.py`) — works across CLI/SDK/HTTP on one POSIX host.

Missing / risky:

- **No `busy_timeout` anywhere** (default 0): any two concurrent writers
  (webhook + `flywheel run`, dashboard + trainer) fail fast with
  `sqlite3.OperationalError: database is locked` instead of waiting.
- **No `PRAGMA synchronous` tuning** (default FULL): safe but pays full fsync cost per
  commit; WAL+NORMAL is the standard combination and is not set.
- **No WAL checkpoint management** (`wal_checkpoint(TRUNCATE)`, `journal_size_limit`):
  under sustained webhook writes the `-wal` file grows until the last connection closes;
  a long-lived receiver process means it never checkpoints.
- **No `VACUUM` / auto-vacuum, no online backup** (`sqlite3.Connection.backup` unused):
  deletes never shrink files; there is no hot-backup path — copying a live WAL-mode DB
  without checkpoint is a corruption risk.
- `registry.db` and `state_graph.db` open without WAL *or* `foreign_keys`, and dashboard
  `mission_control.py` opens raw connections without pragmas — inconsistent with the
  four WAL databases.
- `insert_logs_from_jsonl` opens/commits **one connection per log row** — fine for tens
  of rows, minutes for 100k-row imports, and each commit is a separate fsync.
- `fcntl` is POSIX-only: training lock breaks on Windows and is unreliable on NFS.
- Dataset file write happens *inside* the `BEGIN IMMEDIATE` transaction: holds the DB
  write lock during file I/O (comment at `orchestrator.py:227` acknowledges the orphan
  tradeoff — acceptable, but throughput-capped).

### 1.3 Flywheel epochs, experiments, snapshots

- Epochs: `dpo_epochs` status lifecycle pending→extracted→trained/failed, `pair_count`,
  `dataset_path` pointer to `data/dpo/dpo_<epoch>.jsonl`. Pair IDs are deterministic
  (`uuid5` over source+content, `orchestrator.py:158`) — retry-safe. Good design.
- Experiment tracking: `analytics.db` via `ExperimentTracker` (one connection per call,
  autocommit-per-method). `metrics` is a per-step time-series table with no retention or
  partitioning story; long runs will bloat it. No concurrent-run write test.
- Immutable snapshots: `data/versions.py` content-hashes every artifact (`manifest.json`
  + per-file sha256), binds `build_key` to source fingerprint + config + implementation
  file hashes, verifies on load (`verify_snapshot`), stores pointer + digest in
  `dataset_snapshots`. This is the strongest integrity story in the codebase and must
  survive any migration unchanged in semantics.

### 1.4 Migrations

- Only `.moro/db.sqlite` has any versioning (`user_version=1` + fail-on-newer).
  The other five rely on `CREATE TABLE IF NOT EXISTS` — there is **no ALTER path**:
  adding a column requires manual SQL or a new table. No migration runner, no
  down-migrations, no schema-hash check.

## 2. Options comparison

### Option A — Stay on SQLite+WAL, harden it (recommended for now)

Fix the §1.2 gaps behind a shared connection helper; consolidate the duplicate stores.

- Concurrency: central `get_connection()` setting
  `journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, `foreign_keys=ON`
  everywhere (including registry/state_graph/dashboard); keep `BEGIN IMMEDIATE` +
  webhook idempotency as-is; add periodic `wal_checkpoint(TRUNCATE)` + `journal_size_limit`.
- Epochs/experiments/snapshots: no semantic change. Add `metrics` retention
  (downsample or per-experiment purge) and batch JSONL import in one transaction.
- Backup: `VACUUM INTO` / `Connection.backup` hot-backup command (`moro db backup`);
  never `cp` a live WAL DB. Document checkpoint-before-copy.
- Migrations: extend the `user_version` pattern from `storage/db.py` to all six DBs
  with a tiny ordered-migration runner; fold `webhook_requests` into
  `PRODUCTION_LOG_SCHEMA` as migration 1.
- Consolidation (the real win): merge `registry.db` → `state.db.model_registry` and
  `state_graph.db` → `state.db` nodes/edges, with a one-shot data copy. Six DBs → four.
- Local-dev vs prod: identical — zero new infra, offline-first preserved, matches
  `local_only` privacy mode.
- Cost/ops: $0, no ops burden. Limits: single-host writes, ~tens of webhook writes/sec
  sustained (fine for current scale), POSIX `fcntl` stays (document Windows gap or swap
  to a lock-file + `msvcrt` shim later).

### Option B — Postgres (+ pgvector), single server

One Postgres (16+) replaces all six DBs as schemas; `pgvector` adds embedding search
for future retrieval/dedup over logs and datasets.

- Concurrency: real MVCC — concurrent webhook/CLI/dashboard writers, no lock errors;
  `fcntl` replaced by `pg_advisory_lock` (portable, NFS-safe); idempotency becomes
  `INSERT … ON CONFLICT DO NOTHING/UPDATE` on `request_id`.
- Epochs/experiments: transactions span tables properly; `metrics` gets hypertable-style
  partitioning or BRIN index + retention policy; JSON blobs become `jsonb` with GIN.
- Snapshots: keep files on disk/object store, keep `manifest_sha256` in Postgres;
  `verify_snapshot` logic unchanged, pointer reads move to one query with joins.
- Backup/WAL: `pg_basebackup` + WAL archiving (PITR) — strictly better than SQLite story.
- Migrations: Alembic or `sqitch`; down-migrations included.
- Local-dev vs prod: divergence — devs need Docker/embedded Postgres; offline `moro init`
  gets heavier; tests need `testing.postgresql` or containers.
- Cost/ops: self-host ~$10-20/mo VPS or existing host + backup storage; managed
  (RDS/AlloyDB/Neon) $20-100+/mo. Real ops: upgrades, vacuuming, connection pooling.
- Verdict: right when multi-host writers or >100 writes/sec sustained arrive, or when
  vector search becomes a requirement — not before. pgvector is the only capability
  SQLite cannot match here.

### Option C — Hybrid: SQLite (local) + Postgres (shared/prod)

Keep `.moro/*` SQLite for dev/single-node; production webhook + flywheel + analytics
write to Postgres behind a repository interface.

- Pros: offline dev preserved; prod gets MVCC/concurrency/PITR; migrate one store
  at a time (production_logs first — it has the only concurrent-writer pressure).
- Cons: **two dialects, two migration chains, two backup stories**; every query exists
  twice or behind an ORM; highest engineering cost of all options; consistency bugs
  across the seam (epoch IDs, snapshot pointers) are likely.
- Verdict: only if prod must scale while dev must stay dependency-free *and* the team
  commits to a strict repository abstraction first. Otherwise it is the worst of both.

### Option D — Managed SQLite-likes (Turso) / managed Postgres (Supabase)

- **Turso (libSQL)**: keeps the SQLite dialect, adds remote replicas + edge reads.
  Concurrency story is still effectively single-primary-writer; embedded replicas help
  reads only. Cheapest migration path *if* remote access is the goal — but current
  writers are all local, so it buys little today. Dormant-vendor risk for a
  privacy-sensitive local-first tool.
- **Supabase (managed Postgres)**: Option B without the ops (backups, pooling,
  auth included), plus pgvector. Cost ~$25/mo+ at scale; data leaves the host —
  conflicts with `local_only` privacy posture unless self-hosted (which is just
  Option B with a UI).
- Verdict: revisit when remote/multi-tenant access is required. Neither fixes the
  actual current problems (duplication, no busy_timeout, no migrations) — those are
  code fixes under any option.

## 3. Recommendation

1. **Now (this cycle): Option A.** Harden SQLite+WAL, unify connection setup, fold in
   `webhook_requests`, add `user_version` migrations to all DBs, consolidate the two
   duplicate stores, add hot backup + checkpoint discipline, batch the JSONL importer.
   No dependency, no infra, no privacy change.
2. **Trigger for Option B**: sustained >50 webhook writes/sec, a second writer host,
   or a committed vector-search feature. At that point migrate; the repository seam
   and migration runner built in step 1 make it mechanical.
3. **Never C** unless step-2 pressure arrives *with* a hard offline-dev constraint —
   and then only behind the repository abstraction with production_logs first.

## 4. Migration steps (Option A — hardening, zero-downtime, reversible)

Each step is independently shippable; each has a rollback.

1. **Shared connection helper** — new `moro/storage/sqlite.py`:
   `connect(path)` applying WAL + `busy_timeout=5000` + `synchronous=NORMAL` +
   `foreign_keys=ON`; route all six owners + dashboard through it.
   *Rollback*: revert import; DB files are byte-compatible (pragmas are per-connection).*
2. **Checkpoint discipline** — `wal_checkpoint(TRUNCATE)` after `flywheel run` and on
   receiver idle (SIGHUP/interval); set `journal_size_limit=32MB`.
   *Rollback*: remove calls; no format change.*
3. **Schema fold-in** — add `webhook_requests` to `PRODUCTION_LOG_SCHEMA`;
   `user_version` + ordered migrations for the five unversioned DBs (migration 1 =
   adopt current `CREATE TABLE IF NOT EXISTS` state as baseline).
   *Rollback*: `user_version` downgrade guard already fails safe; keep migration SQL
   additive-only.*
4. **Registry/lineage consolidation** — one-shot `moro db consolidate` copying
   `registry.db`→`state.db.model_registry`, `state_graph.db`→`state.db` nodes/edges;
   repoint `ModelRegistry`/`StateGraphManager` (or deprecate one); keep old files
   renamed `.bak` for one release.
   *Rollback*: restore `.bak` files + revert repoint commit.*
5. **Hot backup** — `moro db backup --all` via `VACUUM INTO` (or `Connection.backup`);
   document "checkpoint, then copy" in runbook; add pre-`flywheel run` auto-backup flag.
   *Rollback*: additive command; nothing to undo.*
6. **Importer batching + metrics retention** — single-transaction JSONL import;
   `moro analytics prune --older-than` for `metrics`/`model_outputs`.
   *Rollback*: revert; data format unchanged.*

Acceptance per step: existing suites
`test_flywheel_storage.py`, `test_flywheel_webhook.py`, `test_flywheel_orchestrator.py`,
`test_analytics.py`, `test_dataset_versions.py` green, plus a new concurrency probe
(webhook ingest ∥ `flywheel run` ∥ dashboard reads, 0 `database is locked` errors)
and a backup/restore round-trip test asserting `verify_snapshot` passes post-restore.

## 5. Migration sketch (Option B — when triggered)

1. Introduce repository interfaces for the three hot stores
   (`production_logs`, `analytics`, core `db.sqlite`); SQLite implementations first,
   behavior-identical, covered by existing tests.
2. Add Postgres implementations (psycopg3, `jsonb`, `ON CONFLICT` idempotency,
   `pg_advisory_lock` for training); Alembic baseline mirroring current DDL.
3. Dual-write shadow period for `production_logs` (SQLite primary, Postgres shadow,
   nightly diff); cut over reads; cut over writes; keep SQLite as file-backup.
4. Move `metrics` to partitioned table + retention; add pgvector only with a feature.
5. *Rollback*: cut reads/writes back to SQLite (schema unchanged during shadow);
   drop Postgres when stable.

## 6. Cost / ops summary

| | A: hardened SQLite | B: Postgres | C: hybrid | D: Turso/Supabase |
|---|---|---|---|---|
| Infra $ | 0 | 10–100+/mo | 10–100+/mo | 0–25+/mo |
| Ops | ~0 | backups/upgrades/pooling | B + dialect split | vendor + egress/privacy review |
| Writer scale | 1 host, ~10s/sec | multi-host, 1000s/sec | split | single-primary / multi |
| Vectors | no | pgvector | prod only | Supabase yes / Turso no |
| Offline dev | yes | containers | yes | needs network (or self-host) |
| Privacy | local-only safe | self-host safe | mixed | review required |

Proposal only — no code changes made. Evidence files inspected are listed in §1;
test observation: `test_flywheel_storage.py` 2 passed; webhook socket tests blocked
by sandbox `PermissionError` on bind (environmental, not DB-related).
