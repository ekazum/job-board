-- Add a posting as status new; an existing (source, external_id) row is left untouched.
-- ON CONFLICT DO NOTHING, not INSERT OR IGNORE: OR IGNORE would also swallow CHECK violations.
INSERT INTO postings (source, external_id, company, title, url, text)
VALUES (:source, :external_id, :company, :title, :url, :text)
ON CONFLICT (source, external_id) DO NOTHING;
