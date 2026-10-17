-- Edit the profile (NULL keeps the stored value); profile/create.sql makes sure the row exists first.
UPDATE profile
SET cv_text            = COALESCE(:cv_text, cv_text),
    targets            = COALESCE(:targets, targets),
    location           = COALESCE(:location, location),
    allow_fully_remote = COALESCE(:allow_fully_remote, allow_fully_remote)
WHERE id = 1;
