-- One company by id.
SELECT id, name, domain, careers_url, platform, slug, verified, enabled, last_checked
FROM companies
WHERE id = :id;
