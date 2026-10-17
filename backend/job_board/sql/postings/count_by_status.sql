-- How many postings each board column holds, unfiltered (the "total" in "shown / total"). Postings in the Archive
-- (closed as not_relevant by the scorer, with a fit, or by the location rule) are not on the board, so they are not
-- counted.
SELECT status, COUNT(*) AS total
FROM postings
WHERE COALESCE(status = 'closed' AND outcome = 'not_relevant' AND (fit IS NOT NULL OR fit_reason LIKE 'location: %'), 0) = 0
GROUP BY status;
