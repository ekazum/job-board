-- How many postings each board column holds, unfiltered (the "total" in "shown / total").
SELECT status, COUNT(*) AS total
FROM postings
GROUP BY status;
