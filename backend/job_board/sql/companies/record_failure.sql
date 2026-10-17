-- Discovery could not reach a company's boards: keep what was found before, save the error and stamp last_checked.
-- A company seen for the first time is added so the error shows in the Companies view.
INSERT INTO companies (name, domain, careers_url, last_checked, last_error)
VALUES (:name, :domain, :careers_url, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), :last_error)
ON CONFLICT (name) DO UPDATE SET last_checked = excluded.last_checked,
                                 last_error   = excluded.last_error;
