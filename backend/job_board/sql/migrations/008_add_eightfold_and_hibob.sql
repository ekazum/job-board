-- Version 7 -> 8: careers sites run on Eightfold (jobs.amdocs.com) or HiBob (<company>.careers.hibob.com).
-- Adds 'eightfold' and 'hibob' to companies.platform and postings.source. SQLite cannot change a CHECK constraint in place, so
-- both tables are rebuilt and every row is copied.

BEGIN;

CREATE TABLE companies_v8
(
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    domain       TEXT,
    careers_url  TEXT,
    platform     TEXT CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'eightfold', 'hibob',
                                      'google', 'microsoft', 'apple', 'amazon', 'meta', 'none')),
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

INSERT INTO companies_v8 (id, name, domain, careers_url, platform, slug, company_uid, token, tenant, wd_host, site, verified,
                          enabled, last_checked, last_error)
SELECT id, name, domain, careers_url, platform, slug, company_uid, token, tenant, wd_host, site, verified, enabled,
       last_checked, last_error
FROM companies;

DROP TABLE companies;
ALTER TABLE companies_v8 RENAME TO companies;

CREATE TABLE postings_v8
(
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL CHECK (source IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'eightfold', 'hibob',
                                         'google', 'microsoft', 'apple', 'amazon', 'meta', 'manual')),
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
    location    TEXT NOT NULL DEFAULT '',
    fit_reason  TEXT,
    fit_gaps    TEXT CHECK (fit_gaps IS NULL OR json_valid(fit_gaps)),
    is_remote   INTEGER NOT NULL DEFAULT 0 CHECK (is_remote IN (0, 1)),
    country     TEXT,
    UNIQUE (source, external_id),
    CHECK (outcome IS NULL OR status = 'closed')
);

INSERT INTO postings_v8 (id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit, location,
                         fit_reason, fit_gaps, is_remote, country)
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit, location, fit_reason,
       fit_gaps, is_remote, country
FROM postings;

DROP TABLE postings;
ALTER TABLE postings_v8 RENAME TO postings;

CREATE INDEX IF NOT EXISTS idx_postings_status_created ON postings (status, created_at DESC);

PRAGMA user_version = 8;

COMMIT;
