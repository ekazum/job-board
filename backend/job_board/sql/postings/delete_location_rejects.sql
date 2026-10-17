-- Purge rejects: delete the postings the location rule closed as not_relevant (fit_reason 'location: ...').
DELETE
FROM postings
WHERE status = 'closed'
  AND outcome = 'not_relevant'
  AND fit_reason LIKE 'location: %';
