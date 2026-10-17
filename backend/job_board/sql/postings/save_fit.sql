-- Store a scoring result, and the status/outcome it leads to.
UPDATE postings
SET fit        = :fit,
    fit_reason = :fit_reason,
    fit_gaps   = :fit_gaps,
    status     = :status,
    outcome    = :outcome
WHERE id = :id;
