-- All postings, newest first.
SELECT id, source, external_id, company, title, url, text, status, outcome, note, created_at, fit
FROM postings
ORDER BY created_at DESC, id DESC;
