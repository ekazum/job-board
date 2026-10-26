-- Pasted postings whose company is not in the list (names compare ignoring case), newest first: Discover adds
-- those companies.
SELECT p.company, p.url
FROM postings AS p
WHERE p.source = :source
  AND NOT EXISTS (SELECT 1 FROM companies AS c WHERE c.name = p.company)
ORDER BY p.id DESC;
