"""Database schema for Aether Mark 1 — SQLite with WAL + foreign keys.

Tables:
    items          — tasks and calendar events (kind column; single-table)
    evidence       — source references attached to items (FK cascade)
    item_history   — append-only audit trail (no FK — survives item deletion)
    review_queue   — uncertain items awaiting human confirmation (FK cascade)
    import_batches — JSON import bookkeeping (content_hash dedupes re-imports)

Defense-in-depth CHECKs mirror ScheduleService validation (service is the
primary gate; SQL CHECKs are the backstop). Migration lives in
aether.task.migrations — never edit applied migrations.

Usage:
    from aether.task.schema import SCHEMA_SQL_V1
    cursor.executescript(SCHEMA_SQL_V1)
"""

SCHEMA_SQL_V1 = """
-- ── Items (tasks + events, single table) ──────────────────────────
CREATE TABLE IF NOT EXISTS items (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL CHECK (kind IN ('task', 'event')),
    title           TEXT NOT NULL CHECK (length(trim(title)) > 0),
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed', 'cancelled')),
    internal_status TEXT NOT NULL DEFAULT 'confirmed'
                    CHECK (internal_status IN ('confirmed', 'needs_confirmation')),
    due_date        TEXT,             -- YYYY-MM-DD; task deadlines only
    start_at        TEXT,             -- ISO-8601 datetime, or YYYY-MM-DD when all_day
    end_at          TEXT,             -- ISO-8601 datetime, or YYYY-MM-DD when all_day
    all_day         INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    tz              TEXT NOT NULL DEFAULT 'Asia/Bangkok',
    owner           TEXT,
    source          TEXT NOT NULL DEFAULT 'manual',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    -- Kind-shape rules (service enforces the full matrix):
    CHECK (kind <> 'event' OR start_at IS NOT NULL OR internal_status = 'needs_confirmation'), -- events require start unless uncertain
    CHECK (kind <> 'event' OR due_date IS NULL),               -- events use start_at, not due_date
    CHECK (kind <> 'task' OR all_day = 0),                     -- all_day is event-only
    CHECK (due_date IS NULL OR length(due_date) = 10),         -- due_date is date-only
    CHECK (all_day = 0 OR start_at IS NULL OR length(start_at) = 10),
    CHECK (all_day = 0 OR end_at IS NULL OR length(end_at) = 10),
    CHECK (all_day = 1 OR start_at IS NULL OR instr(start_at, 'T') > 0),
    CHECK (all_day = 1 OR end_at IS NULL OR instr(end_at, 'T') > 0),
    CHECK (end_at IS NULL OR start_at IS NOT NULL)              -- end requires start
);

CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_due_date ON items(due_date);
CREATE INDEX IF NOT EXISTS idx_items_start_at ON items(start_at);
CREATE INDEX IF NOT EXISTS idx_items_updated_at ON items(updated_at);

-- ── Evidence (source references; cascades with item) ──────────────
CREATE TABLE IF NOT EXISTS evidence (
    id          TEXT PRIMARY KEY,
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    source_ref  TEXT NOT NULL DEFAULT '',
    excerpt     TEXT NOT NULL DEFAULT '',
    confidence  REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_item ON evidence(item_id);

-- ── Item history (append-only; survives item deletion) ────────────
CREATE TABLE IF NOT EXISTS item_history (
    id             TEXT PRIMARY KEY,
    item_id        TEXT NOT NULL,
    action         TEXT NOT NULL CHECK (action IN
                   ('created', 'updated', 'completed', 'cancelled',
                    'deleted', 'imported', 'reviewed')),
    before_json    TEXT,
    after_json     TEXT,
    changed_fields TEXT NOT NULL DEFAULT '[]',
    note           TEXT,
    actor          TEXT NOT NULL DEFAULT 'system',
    created_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_item ON item_history(item_id, created_at);

-- ── Review queue (uncertain items; cascades with item) ────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id          TEXT PRIMARY KEY,
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    reason      TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    confidence  REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    state       TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'confirmed', 'rejected', 'edited')),
    created_at  REAL NOT NULL,
    resolved_at REAL
);

CREATE INDEX IF NOT EXISTS idx_review_state ON review_queue(state, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_one_pending
    ON review_queue(item_id) WHERE state = 'pending';

-- ── Import batches (JSON import bookkeeping) ──────────────────────
CREATE TABLE IF NOT EXISTS import_batches (
    id             TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    format_version TEXT NOT NULL DEFAULT '1',
    content_hash   TEXT NOT NULL UNIQUE,
    item_count     INTEGER NOT NULL DEFAULT 0,
    stats          TEXT NOT NULL DEFAULT '{}',
    imported_at    REAL NOT NULL
);
"""
