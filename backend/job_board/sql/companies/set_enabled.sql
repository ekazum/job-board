-- Turn scanning on or off for a company.
UPDATE companies
SET enabled = :enabled
WHERE id = :id;
