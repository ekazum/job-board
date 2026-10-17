-- Postings Re-score all works on: not scored yet, or still in New; not the ones the location rule archived.
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit, location, fit_reason,
       fit_gaps, is_remote, country
FROM postings
WHERE (fit IS NULL OR status = 'new')
  AND NOT COALESCE(status = 'closed' AND outcome = 'not_relevant' AND fit_reason LIKE 'location: %', 0)
ORDER BY created_at DESC, id DESC;
