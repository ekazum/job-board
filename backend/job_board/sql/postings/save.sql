-- Persist the fields a user can change on a posting.
UPDATE postings
SET status  = :status,
    outcome = :outcome,
    note    = :note
WHERE id = :id;
