-- Set (or clear, with NULL) the domain Discover starts from for a company.
UPDATE companies
SET domain = :domain
WHERE id = :id;
