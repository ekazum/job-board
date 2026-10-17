-- Add a company; an existing company with the same name (any case) is left untouched.
INSERT INTO companies (name, domain, careers_url)
VALUES (:name, :domain, :careers_url)
ON CONFLICT (name) DO NOTHING;
