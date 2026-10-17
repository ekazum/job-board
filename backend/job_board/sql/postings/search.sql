-- Postings matching the board's filter bar, newest first. Every filter is optional (NULL = no filter):
--   :pattern    LIKE pattern on the title ('%llm%'; % and _ in the user's text are escaped with \), and on the
--               description too when :in_text is 1. LIKE is case-insensitive for ASCII in SQLite.
--   :companies  JSON array of company names, :sources JSON array of sources (one parameter each, expanded by json_each)
--   :min_fit    fit >= :min_fit; postings not scored yet (fit NULL) always pass
--   :location   substring of the location, both sides normalized by normalized_location() (PlaceNames.normalize,
--               registered on the connection by PostingRepository.search)
--   :archived   1 = only the Archive, 0 = everything else. The Archive holds postings closed as not_relevant by the
--               scorer (they have a fit) or by the location rule (fit_reason 'location: ...', see location_rule.py)
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit, location, fit_reason,
       fit_gaps, is_remote, country
FROM postings
WHERE (:pattern IS NULL
    OR title LIKE :pattern ESCAPE '\'
    OR (:in_text = 1 AND text LIKE :pattern ESCAPE '\'))
  AND (:companies IS NULL OR company IN (SELECT value FROM json_each(:companies)))
  AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
  AND (:min_fit IS NULL OR fit >= :min_fit OR fit IS NULL)
  AND (:location IS NULL OR instr(normalized_location(location), :location) > 0)
  AND COALESCE(status = 'closed' AND outcome = 'not_relevant' AND (fit IS NOT NULL OR fit_reason LIKE 'location: %'), 0)
    = :archived
ORDER BY created_at DESC, id DESC;
