-- Store whether a posting says it is remote, and its country where none is stored yet (a country read from the
-- board's own field when it was scanned is kept).
UPDATE postings
SET is_remote = :is_remote,
    country   = COALESCE(country, :country)
WHERE id = :id;
