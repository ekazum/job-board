-- One posting by id.
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit, location, fit_reason,
       fit_gaps, is_remote, country
FROM postings
WHERE id = :id;
