-- Version 5 -> 6: the location rule (job_board/location_rule.py). The profile gets the location postings must be in
-- and whether fully remote postings pass too; it starts empty, so nothing passes until it is set. The profile row
-- is created if it was missing. postings get is_remote (the posting says it is remote) and country (the ISO 3166-1
-- alpha-2 code(s) its location resolves to, "IL" or "DE,IL"; NULL until resolved).

BEGIN;

ALTER TABLE profile ADD COLUMN location TEXT NOT NULL DEFAULT '';
ALTER TABLE profile ADD COLUMN allow_fully_remote INTEGER NOT NULL DEFAULT 0 CHECK (allow_fully_remote IN (0, 1));

INSERT INTO profile (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

ALTER TABLE postings ADD COLUMN is_remote INTEGER NOT NULL DEFAULT 0 CHECK (is_remote IN (0, 1));
ALTER TABLE postings ADD COLUMN country TEXT;

PRAGMA user_version = 6;

COMMIT;
