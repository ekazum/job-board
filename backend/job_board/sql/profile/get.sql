-- The candidate profile (at most one row).
SELECT cv_text, targets, filename, uploaded_at, location, allow_fully_remote, include_keywords, exclude_keywords
FROM profile
WHERE id = 1;
