-- Whether a posting with this dedup key is already stored (scan skips scoring it again).
SELECT EXISTS (SELECT 1 FROM postings WHERE source = :source AND external_id = :external_id) AS found;
