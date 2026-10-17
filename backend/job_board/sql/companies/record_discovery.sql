-- Upsert what discovery found, stamp last_checked and clear last_error. enabled is never touched, so a company
-- switched off in the UI stays off after rediscovery.
INSERT INTO companies (name, domain, careers_url, platform, slug, company_uid, token, tenant, wd_host, site, verified,
                       last_checked, last_error)
VALUES (:name, :domain, :careers_url, :platform, :slug, :company_uid, :token, :tenant, :wd_host, :site, :verified,
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL)
ON CONFLICT (name) DO UPDATE SET domain       = excluded.domain,
                                 careers_url  = excluded.careers_url,
                                 platform     = excluded.platform,
                                 slug         = excluded.slug,
                                 company_uid  = excluded.company_uid,
                                 token        = excluded.token,
                                 tenant       = excluded.tenant,
                                 wd_host      = excluded.wd_host,
                                 site         = excluded.site,
                                 verified     = excluded.verified,
                                 last_checked = excluded.last_checked,
                                 last_error   = NULL;
