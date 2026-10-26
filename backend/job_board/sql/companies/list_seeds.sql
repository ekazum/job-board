-- Stored companies that discovery can work on (they have a domain or a careers URL), alphabetically.
SELECT name, domain, careers_url
FROM companies
WHERE domain IS NOT NULL
   OR careers_url IS NOT NULL
ORDER BY name;
