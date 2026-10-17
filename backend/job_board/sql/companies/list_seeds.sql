-- Stored companies that discovery can work on (they have a domain), alphabetically.
SELECT name, domain, careers_url
FROM companies
WHERE domain IS NOT NULL
ORDER BY name;
