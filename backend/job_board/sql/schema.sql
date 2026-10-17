-- job-board schema. Every statement is IF NOT EXISTS, so this runs safely on every start.
-- The CHECK value lists must match job_board/enums; tests/test_database.py tries every enum value against them.

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS companies
(
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    domain       TEXT,
    careers_url  TEXT,
    platform     TEXT CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'comeet', 'none')),
    slug         TEXT,
    verified     INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    enabled      INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS postings
(
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL CHECK (source IN ('greenhouse', 'lever', 'ashby', 'comeet', 'manual')),
    external_id TEXT NOT NULL,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'applied', 'interview', 'closed')),
    outcome     TEXT CHECK (outcome IN ('rejected', 'withdrawn', 'offer', 'not_relevant')),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (source, external_id),
    CHECK (outcome IS NULL OR status = 'closed')
);

CREATE INDEX IF NOT EXISTS idx_postings_status_created ON postings (status, created_at DESC);
