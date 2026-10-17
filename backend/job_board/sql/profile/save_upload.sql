-- Store an uploaded CV's text and file name; targets written earlier are kept.
INSERT INTO profile (id, cv_text, filename, uploaded_at)
VALUES (1, :cv_text, :filename, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
ON CONFLICT (id) DO UPDATE SET cv_text     = excluded.cv_text,
                               filename    = excluded.filename,
                               uploaded_at = excluded.uploaded_at;
