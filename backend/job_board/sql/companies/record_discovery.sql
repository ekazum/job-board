-- Upsert what discovery found and stamp last_checked. enabled is never touched, so a company
-- switched off in the UI stays off after rediscovery.
INSERT INTO companies (name, domain, careers_url, platform, slug, verified, last_checked)
VALUES (:name, :domain, :careers_url, :platform, :slug, :verified, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
ON CONFLICT (name) DO UPDATE SET domain       = excluded.domain,
                                 careers_url  = excluded.careers_url,
                                 platform     = excluded.platform,
                                 slug         = excluded.slug,
                                 verified     = excluded.verified,
                                 last_checked = excluded.last_checked;
