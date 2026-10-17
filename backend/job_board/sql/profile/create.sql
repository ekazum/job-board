-- The profile row with its column defaults, unless it exists already.
INSERT INTO profile (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;
