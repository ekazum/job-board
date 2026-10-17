-- One posting by its dedup key.
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at
FROM postings
WHERE source = :source
  AND external_id = :external_id;
