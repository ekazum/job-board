-- Save (or clear, with NULL) the latest scan error of a company.
UPDATE companies
SET last_error = :last_error
WHERE name = :name;
