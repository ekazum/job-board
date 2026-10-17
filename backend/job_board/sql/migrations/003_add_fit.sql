-- Version 2 -> 3: postings.fit, the LLM fit score (0-10), NULL until a posting has been scored.

BEGIN;

ALTER TABLE postings ADD COLUMN fit INTEGER CHECK (fit IS NULL OR fit BETWEEN 0 AND 10);

PRAGMA user_version = 3;

COMMIT;
