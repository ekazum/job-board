-- One company by name; the column is COLLATE NOCASE, so the match ignores case.
SELECT id, name, domain, careers_url, platform, slug, verified, enabled, last_checked, last_error
FROM companies
WHERE name = :name;
