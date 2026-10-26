-- Purge rejects: delete the postings the profile's rules closed as not_relevant (fit_reason 'keywords: ...' from the
-- role filter, 'location: ...' from the location rule).
DELETE
FROM postings
WHERE status = 'closed'
  AND outcome = 'not_relevant'
  AND (fit_reason LIKE 'keywords: %' OR fit_reason LIKE 'location: %');
