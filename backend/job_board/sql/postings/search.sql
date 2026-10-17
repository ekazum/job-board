-- Postings matching the board's filter bar, newest first. Every filter is optional (NULL = no filter):
--   :pattern    LIKE pattern on the title ('%llm%'; % and _ in the user's text are escaped with \), and on the
--               description too when :in_text is 1. LIKE is case-insensitive for ASCII in SQLite.
--   :companies  JSON array of company names, :sources JSON array of sources (one parameter each, expanded by json_each)
--   :min_fit    fit >= :min_fit; postings not scored yet (fit NULL) always pass
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit
FROM postings
WHERE (:pattern IS NULL
    OR title LIKE :pattern ESCAPE '\'
    OR (:in_text = 1 AND text LIKE :pattern ESCAPE '\'))
  AND (:companies IS NULL OR company IN (SELECT value FROM json_each(:companies)))
  AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
  AND (:min_fit IS NULL OR fit >= :min_fit OR fit IS NULL)
ORDER BY created_at DESC, id DESC;
