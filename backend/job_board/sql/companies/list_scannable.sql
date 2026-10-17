-- Companies to scan: verified, enabled, and on a supported platform, alphabetically.
SELECT name, platform, slug, company_uid, token, tenant, wd_host, site
FROM companies
WHERE verified = 1
  AND enabled = 1
  AND platform IS NOT NULL
  AND platform != 'none'
  AND slug IS NOT NULL
ORDER BY name;
