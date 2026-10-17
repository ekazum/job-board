-- Version 3 -> 4: LLM scoring. postings get the job's location (the scorer reads it) and the scorer's reason and
-- gaps next to fit; the single-row profile table holds the CV text and targets the scorer compares against.

BEGIN;

ALTER TABLE postings ADD COLUMN location TEXT NOT NULL DEFAULT '';
ALTER TABLE postings ADD COLUMN fit_reason TEXT;
ALTER TABLE postings ADD COLUMN fit_gaps TEXT CHECK (fit_gaps IS NULL OR json_valid(fit_gaps));

CREATE TABLE profile
(
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    cv_text     TEXT NOT NULL DEFAULT '',
    targets     TEXT NOT NULL DEFAULT '',
    filename    TEXT,
    uploaded_at TEXT
);

PRAGMA user_version = 4;

COMMIT;
