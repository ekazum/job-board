-- Add a posting; an existing (source, external_id) row is left untouched.
-- ON CONFLICT DO NOTHING, not INSERT OR IGNORE: OR IGNORE would also swallow CHECK violations.
INSERT INTO postings (source, external_id, company, title, url, text, location, is_remote, country, status, outcome, fit,
                      fit_reason, fit_gaps)
VALUES (:source, :external_id, :company, :title, :url, :text, :location, :is_remote, :country, :status, :outcome, :fit,
        :fit_reason, :fit_gaps)
ON CONFLICT (source, external_id) DO NOTHING;
