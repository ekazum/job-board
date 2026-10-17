-- job-board schema, version 3. Runs only on a new database; existing ones are brought up to date by
-- sql/migrations/<version>_*.sql. The CHECK value lists must match job_board/enums
-- (tests/test_database.py tries every enum value against them).

PRAGMA journal_mode = WAL;

-- company_uid/token: Comeet careers API; tenant/wd_host/site: Workday; last_error: latest discover/scan failure.
CREATE TABLE IF NOT EXISTS companies
(
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    domain       TEXT,
    careers_url  TEXT,
    platform     TEXT CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'none')),
    slug         TEXT,
    company_uid  TEXT,
    token        TEXT,
    tenant       TEXT,
    wd_host      TEXT,
    site         TEXT,
    verified     INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    enabled      INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_checked TEXT,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS postings
(
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL CHECK (source IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'manual')),
    external_id TEXT NOT NULL,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    text        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'applied', 'interview', 'closed')),
    outcome     TEXT CHECK (outcome IN ('rejected', 'withdrawn', 'offer', 'not_relevant')),
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    fit         INTEGER CHECK (fit IS NULL OR fit BETWEEN 0 AND 10),
    UNIQUE (source, external_id),
    CHECK (outcome IS NULL OR status = 'closed')
);

CREATE INDEX IF NOT EXISTS idx_postings_status_created ON postings (status, created_at DESC);

PRAGMA user_version = 3;
