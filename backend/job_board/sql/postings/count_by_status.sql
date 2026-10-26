-- How many postings each board column holds, unfiltered (the "total" in "shown / total"). Postings in the Archive
-- (closed as not_relevant by the role filter or the location rule) are not on the board, so they are not counted.
SELECT status, COUNT(*) AS total
FROM postings
WHERE COALESCE(status = 'closed' AND outcome = 'not_relevant' AND (fit_reason LIKE 'keywords: %' OR fit_reason LIKE 'location: %'), 0) = 0
GROUP BY status;
