-- Version 6 -> 7: the role filter (job_board/rules/keyword_filter.py) moves from config.yaml's keywords.include and
-- keywords.exclude to the profile: the job-title words or phrases wanted and excluded, as JSON arrays of strings.
-- Both start empty, which lets every title through.

BEGIN;

ALTER TABLE profile ADD COLUMN include_keywords TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(include_keywords));
ALTER TABLE profile ADD COLUMN exclude_keywords TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(exclude_keywords));

PRAGMA user_version = 7;

COMMIT;
