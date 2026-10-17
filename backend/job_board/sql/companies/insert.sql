-- Add a company; an existing company with the same name (any case) is left untouched.
INSERT INTO companies (name, domain)
VALUES (:name, :domain)
ON CONFLICT (name) DO NOTHING;
