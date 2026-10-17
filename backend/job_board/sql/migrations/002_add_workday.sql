-- Version 1 -> 2: Workday and Comeet-API boards, and per-company errors.
-- Adds 'workday' to companies.platform and postings.source, and the columns company_uid, token (Comeet), tenant,
-- wd_host, site (Workday) and last_error to companies. SQLite cannot change a CHECK constraint in place, so both
-- tables are rebuilt and every row is copied.

BEGIN;

CREATE TABLE companies_v2
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

INSERT INTO companies_v2 (id, name, domain, careers_url, platform, slug, verified, enabled, last_checked)
SELECT id, name, domain, careers_url, platform, slug, verified, enabled, last_checked
FROM companies;

DROP TABLE companies;
ALTER TABLE companies_v2 RENAME TO companies;

CREATE TABLE postings_v2
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
    UNIQUE (source, external_id),
    CHECK (outcome IS NULL OR status = 'closed')
);

INSERT INTO postings_v2 (id, source, external_id, company, title, url, text, status, outcome, note, created_at)
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at
FROM postings;

DROP TABLE postings;
ALTER TABLE postings_v2 RENAME TO postings;

CREATE INDEX IF NOT EXISTS idx_postings_status_created ON postings (status, created_at DESC);

PRAGMA user_version = 2;

COMMIT;
