-- Set (or clear, with NULL) the careers page Discover fetches first for a company.
UPDATE companies
SET careers_url = :careers_url
WHERE id = :id;
