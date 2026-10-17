-- Every company that has a posting, for the filter bar's company list.
SELECT DISTINCT company
FROM postings
ORDER BY company COLLATE NOCASE;
