-- Fill in the location of a posting stored before it had one (locations are read from the boards since version 4).
UPDATE postings
SET location  = :location,
    is_remote = :is_remote,
    country   = :country
WHERE source = :source
  AND external_id = :external_id
  AND location = '';
