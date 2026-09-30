"""Database schema for Memory Core — SQLite with WAL + FTS5 + R-Tree.

Tables:
    semantic:    Facts and knowledge (FTS5 indexed on key + value)
    episodic:    Timeline of events (FTS5 indexed on key + context)
    spatial:     Objects with 3D positions (R-Tree spatial index)
    working:     Short-term memory with TTL expiration
    metadata:    Memory system metadata (version, config, stats)

Usage:
    from aether.memory.schema import SCHEMA_SQL
    cursor.executescript(SCHEMA_SQL)
"""

SCHEMA_SQL = """
-- Enable WAL mode for concurrent reads/writes
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── Semantic memory (facts, knowledge) ───────────────────────────
CREATE TABLE IF NOT EXISTS semantic (
    id          TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    value       TEXT,
    context     TEXT DEFAULT '{}',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    access_count INTEGER DEFAULT 0,
    ttl_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_semantic_key ON semantic(key);
CREATE INDEX IF NOT EXISTS idx_semantic_updated ON semantic(updated_at);

-- ── Episodic memory (timeline events) ────────────────────────────
CREATE TABLE IF NOT EXISTS episodic (
    id          TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    value       TEXT,
    context     TEXT DEFAULT '{}',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    access_count INTEGER DEFAULT 0,
    ttl_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_episodic_key ON episodic(key);
CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic(created_at);

-- ── Working memory (short-term, fast expire) ─────────────────────
CREATE TABLE IF NOT EXISTS working (
    id          TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    value       TEXT,
    context     TEXT DEFAULT '{}',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    access_count INTEGER DEFAULT 0,
    ttl_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_working_key ON working(key);

-- ── Spatial memory (3D objects) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS spatial (
    id          TEXT PRIMARY KEY,
    key         TEXT NOT NULL,
    label       TEXT DEFAULT '',
    value       TEXT,
    context     TEXT DEFAULT '{}',
    x           REAL DEFAULT 0.0,
    y           REAL DEFAULT 0.0,
    z           REAL DEFAULT 0.0,
    confidence  REAL DEFAULT 1.0,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    access_count INTEGER DEFAULT 0,
    ttl_seconds REAL
);

CREATE INDEX IF NOT EXISTS idx_spatial_key ON spatial(key);
CREATE INDEX IF NOT EXISTS idx_spatial_label ON spatial(label);

-- R-Tree spatial index for nearest-neighbor queries
CREATE VIRTUAL TABLE IF NOT EXISTS spatial_rtree USING rtree(
    id,        -- Integer primary key matching spatial.rowid
    min_x, max_x,
    min_y, max_y,
    min_z, max_z
);

-- ── FTS5 full-text search indexes ────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(
    key,
    value,
    context,
    content='semantic',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
    key,
    value,
    context,
    content='episodic',
    content_rowid='rowid'
);

-- Triggers to keep FTS indexes in sync
CREATE TRIGGER IF NOT EXISTS semantic_ai AFTER INSERT ON semantic BEGIN
    INSERT INTO semantic_fts(rowid, key, value, context)
    VALUES (new.rowid, new.key, new.value, new.context);
END;

CREATE TRIGGER IF NOT EXISTS semantic_ad AFTER DELETE ON semantic BEGIN
    INSERT INTO semantic_fts(semantic_fts, rowid, key, value, context)
    VALUES ('delete', old.rowid, old.key, old.value, old.context);
END;

CREATE TRIGGER IF NOT EXISTS semantic_au AFTER UPDATE ON semantic BEGIN
    INSERT INTO semantic_fts(semantic_fts, rowid, key, value, context)
    VALUES ('delete', old.rowid, old.key, old.value, old.context);
    INSERT INTO semantic_fts(rowid, key, value, context)
    VALUES (new.rowid, new.key, new.value, new.context);
END;

CREATE TRIGGER IF NOT EXISTS episodic_ai AFTER INSERT ON episodic BEGIN
    INSERT INTO episodic_fts(rowid, key, value, context)
    VALUES (new.rowid, new.key, new.value, new.context);
END;

CREATE TRIGGER IF NOT EXISTS episodic_ad AFTER DELETE ON episodic BEGIN
    INSERT INTO episodic_fts(episodic_fts, rowid, key, value, context)
    VALUES ('delete', old.rowid, old.key, old.value, old.context);
END;

CREATE TRIGGER IF NOT EXISTS episodic_au AFTER UPDATE ON episodic BEGIN
    INSERT INTO episodic_fts(episodic_fts, rowid, key, value, context)
    VALUES ('delete', old.rowid, old.key, old.value, old.context);
    INSERT INTO episodic_fts(rowid, key, value, context)
    VALUES (new.rowid, new.key, new.value, new.context);
END;

-- ── Metadata table (system info) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('created_at', strftime('%s','now'));
"""
