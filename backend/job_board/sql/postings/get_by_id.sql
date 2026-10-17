-- One posting by id.
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit
FROM postings
WHERE id = :id;
