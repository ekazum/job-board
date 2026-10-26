-- job-board schema, version 9. Runs only on a new database; existing ones are brought up to date by
-- sql/migrations/<version>_*.sql. The CHECK value lists must match job_board/enums
-- (tests/test_database.py tries every enum value against them).

PRAGMA journal_mode = WAL;

-- company_uid/token: Comeet careers API; tenant/wd_host/site: Workday (tenant: the API domain on Eightfold);
-- last_error: latest discover/scan failure.
CREATE TABLE IF NOT EXISTS companies
(
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    domain       TEXT,
    careers_url  TEXT,
    platform     TEXT CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'eightfold', 'hibob',
                                      'tyco', 'google', 'microsoft', 'apple', 'amazon', 'meta', 'none')),
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

-- location: the board's wording; country: ISO 3166-1 alpha-2 code(s) it resolves to ("IL", "DE,IL"), NULL if unknown.
CREATE TABLE IF NOT EXISTS postings
(
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL CHECK (source IN ('greenhouse', 'lever', 'ashby', 'comeet', 'workday', 'eightfold', 'hibob',
                                         'tyco', 'google', 'microsoft', 'apple', 'amazon', 'meta', 'manual')),
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

CREATE INDEX IF NOT EXISTS idx_postings_status_created ON postings (status, created_at DESC);

-- The candidate the LLM scorer compares postings against, the job-title keywords (JSON arrays) and the location
-- postings must be in; exactly one row, created here with no keywords (every title passes) and an empty location, so
-- no posting passes the location rule until one is set.
CREATE TABLE IF NOT EXISTS profile
(
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    cv_text            TEXT    NOT NULL DEFAULT '',
    targets            TEXT    NOT NULL DEFAULT '',
    filename           TEXT,
    uploaded_at        TEXT,
    location           TEXT    NOT NULL DEFAULT '',
    allow_fully_remote INTEGER NOT NULL DEFAULT 0 CHECK (allow_fully_remote IN (0, 1)),
    include_keywords   TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(include_keywords)),
    exclude_keywords   TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(exclude_keywords))
);

INSERT INTO profile (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

PRAGMA user_version = 8;
