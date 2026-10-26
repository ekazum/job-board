# job-board

Collect job postings in one place and track where each application stands.

## How postings get in

- **Paste** (main path): found a posting anywhere — LinkedIn, a careers page, a recruiter email — paste
  URL, title, company and the description into the form and it becomes a card. LinkedIn has no API you're
  allowed to read, so this is how most postings arrive.
- **Scan** (complement): `discover` finds which applicant-tracking system each company in your list uses
  (Greenhouse, Lever, Ashby, Comeet, Workday), or its own careers site (Google, Microsoft, Apple, Amazon, Meta);
  `scan` reads those boards, keeps titles matching your profile's job-title keywords and drops the ones outside its
  location (not stored, no LLM call), has the LLM score the rest against your profile, and adds each as a `new` card
  with its score. It only covers companies you've named.

Duplicates are ignored on `(source, external_id)`: a rescan never re-adds a posting or resets its status,
and pasting the same link twice is a no-op (`source = manual`, `external_id` = normalized URL).

## Status

`new → applied → interview → closed`. A closed posting may carry an `outcome`
(`rejected`, `withdrawn`, `offer`, `not_relevant`); the database refuses an outcome on any other status.

## Setup (Windows, conda)

```powershell
conda env create -f environment.yml
conda activate job-board
npm --prefix frontend install
npm --prefix frontend run build
```

After `environment.yml` changes: `conda env update -f environment.yml --prune`.

## Run

From the repo root:

```powershell
conda activate job-board
npm --prefix frontend run build
uvicorn job_board.main:app --app-dir backend
```

Then open http://localhost:8000. **Board** is the Kanban; **Companies** has Add company, Discover and Scan.
A first Discover over the 50 seeded companies takes a few minutes; then Scan fills the New column.

The database is created at `data/job_board.db` on first start. `JOB_BOARD_CONFIG` overrides the config path
(default: `config.yaml` at the repo root).

Development, with hot reload on both sides:

```powershell
uvicorn job_board.main:app --app-dir backend --reload
npm --prefix frontend run dev     # http://localhost:5173, proxies /api to :8000
```

## Discover and scan

List companies in `config.yaml`:

```yaml
companies:
  - {name: Acme, domain: acme.com}
  - {name: Globex, domain: globex.co.il, careers_url: "https://globex.co.il/about/careers"}
```

```powershell
python -m job_board.runs.discover   # or POST /api/discover
python -m job_board.runs.scan       # or POST /api/scan (in the background; GET /api/scan/status)
```

- **discover** first recognizes Google, Microsoft, Apple, Amazon and Meta by domain or careers URL: each has its own
  careers site, verified with one search. For everyone else it fetches `careers_url` (config, else the one saved in
  the Companies view) together with `https://<domain>/careers`, `/jobs`, `/join-us`, and takes the board linked from
  the first of them that has one: Greenhouse, Lever, Ashby, Comeet (hosted page, `careers-api` URL, or the careers
  widget's `company-uid`/`token`) or Workday (`<tenant>.wd<N>.myworkdayjobs.com/<site>`). A link is verified against
  that platform's API. Without a link, the domain stem (`acme` for `acme.co.il`) is probed on Greenhouse, Lever and
  Ashby; a guessed Greenhouse board whose name is another company's is rejected. Still nothing → the company name
  (`checkpoint` for "Check Point") and the stem are tried as a Workday tenant on `wd1`..`wd12`: the host where
  `robots.txt` answers 200 names the job sites, and the first site whose jobs endpoint answers is recorded. A tenant
  answering 401 has no public site and is skipped. A careers page served by **Eightfold** (the system behind
  Microsoft's site; `<code id="pcsx-data">` names its API domain) is read through its own host, e.g.
  `jobs.amdocs.com` with domain `amdocs.com`. A link to a **HiBob** careers site (`<company>.careers.hibob.com`) is
  read through its `api/job-ad` (every job at once). Nothing found → `platform = none`; a board the page loads from a
  script is missed, so put the board's own URL in `careers_url` (e.g. `https://job-boards.greenhouse.io/playtikaltd`).
- **scan** reads every verified + enabled company's board and adds jobs whose **title** matches a wanted role and
  no excluded word (the profile's [job titles](#job-titles)) as `new`. Postings already stored are skipped before scoring (and on insert, `ON CONFLICT DO NOTHING`),
  so a rescan never duplicates a card, resets its status, or spends LLM calls on known jobs; it only fills in the
  location of a stored job that has none. New ones go through the [location rule](#location) and are scored
  (see [Scoring](#scoring)), each inserted as soon as it is scored: a scan that stops early (server stopped) keeps
  those, and the next scan scores the rest. **Scan** in the Companies view runs in the background with a progress
  bar (boards read, then new jobs scored); the board reloads as cards arrive, and reopening the view during a scan
  picks the progress up again. Scoring is the slow part with a local model (`qwen2.5:7b` on a CPU takes about 50 s per job).
- **Comeet** boards with a token are read through `careers-api/2.0/company/<uid>/positions`; hosted-page boards
  (no token) through the page's embedded positions. **Workday** and **Eightfold** sites and the five company careers
  sites are searched once per wanted role (as plain text), narrowed on the way in to the profile location's country
  (`Haifa` searches `Israel`; no location searches everywhere). That only saves requests; the profile's location decides (a fully
  remote job on these sites is only found when it lists that country):

  | Platform | Endpoint (found in the careers page's network calls) | Location filter |
  |---|---|---|
  | Google | `POST google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute?rpcids=r06xKb` | location list in the query |
  | Microsoft | `GET apply.careers.microsoft.com/api/pcsx/search`, then `position_details` per job | `location=` |
  | Eightfold | the same API on the site's own host (`jobs.amdocs.com/api/pcsx/search?domain=amdocs.com`) | `location=` |
  | Apple | `POST jobs.apple.com/api/v1/search`, then `jobDetails/<id>` per position | ids from `refData/postlocation?input=Israel` |
  | Amazon | `GET amazon.jobs/en/search.json` (descriptions included) | `country=ISR`, looked up from job data |
  | Meta | `POST metacareers.com/graphql` (search page's persisted queries), then the job page's JSON-LD | offices whose name contains the location |

  Meta's query ids change when Meta redeploys its site; a scan then reports the GraphQL error in `last_error`.
- Companies run concurrently (10 requests at a time, 15 s timeout, one retry on timeout or 5xx). A company that
  fails gets its reason in `last_error` (shown in red in the Companies view) and the run carries on; a later
  successful run clears it. Both runs re-read `config.yaml`, and only one runs at a time (a second gets 409).
- The database schema is versioned (`PRAGMA user_version`); `sql/migrations/` brings older files up to date on
  start and keeps their rows.

Regenerate frontend types after changing API models (backend must be running):
`npm --prefix frontend run gen:types`. `frontend/src/api/types.ts` is committed.

## LLM provider

`backend/job_board/llm/llm_client.py` is the only code that talks to an LLM (and the only importer of `openai`). Every
provider is reached through its OpenAI-compatible API, chosen in `config.yaml`:

```yaml
llm:
  provider: ollama          # ollama | groq | github | anthropic | openai
  model: qwen2.5:7b
```

Switching provider is that one line, or the drop-down in the **Settings** view (it rewrites the line and keeps the
comments). Each entry under `providers:` has its `base_url`, the `.env` variable holding its key (`api_key_env`;
`NONE` for Ollama, which gets a dummy key), `concurrency` (1 for Ollama on CPU, 5 for hosted APIs) and `json_mode`
(`response_format=json_object`, on for Ollama). Requests use temperature 0 and the system prompt in
`backend/job_board/prompts/score_system.txt`, which holds the answer's JSON schema. Keys for hosted providers go in a
`.env` file at the repo root (git-ignored), e.g. `GROQ_API_KEY=...`.

### Ollama on Windows

1. Install Ollama: `winget install Ollama.Ollama` (or the installer from https://ollama.com/download/windows).
   It runs in the background at `http://localhost:11434`.
2. Download the model (about 4.7 GB): `ollama pull qwen2.5:7b`
3. Confirm it is there: `ollama list` should show `qwen2.5:7b`.
4. Open http://localhost:8000/#settings and click **Test**: it should answer with a small JSON object and its latency.
5. Run Scan from the Companies view.

## Job titles

The **Profile** view's **Job titles** block holds the **Wanted roles** and the **Excluded** words, as chips: type a
word or a phrase and press Enter (or Add), × removes one. They are stored in the `profile` table
(`include_keywords`, `exclude_keywords`, JSON arrays).

- `keyword_filter.py` matches the job **title**, whole words, any case. A phrase matches as written:
  `Engineering Director` matches "Engineering Director, AI" but not "Director of Engineering". `AI + engineer` needs
  both words, in any order. An excluded word wins. With no wanted roles, every title passes.
- **Scan**: a job that fails is not stored and costs no LLM call; once the keywords allow it, the next scan adds it.
- **Save** applies the keywords together with the [location](#location) to the stored postings: postings in New that
  fail move to the **Archive** with reason `keywords: excludes "intern"` or `keywords: no wanted role in the title`;
  ones archived that way that now pass come back to New. Pasted postings are never touched.

## Location

The **Profile** view has a **Location** (a country or a city, e.g. `Israel`) and **Also allow fully remote jobs**.
The profile starts with no location, so a scan stores nothing until you set one.

- `location_resolver.py` turns a location into ISO country codes, offline: the board's own country field when it has
  one (Comeet `location.country`, Workday `jobRequisitionLocation.country.alpha2Code`); else each place in the text
  (`Berlin / Tel Aviv`, `A | B`, `A; B`) by its last or first comma part as a country name (`Tel Aviv, Israel`,
  `Israel, Raanana`, `Remote - US`); else the city, looked up in [geonamescache](https://pypi.org/project/geonamescache/)
  (cities of 15,000+) after normalizing spellings (`Tel Aviv-Yafo`, `Petach Tikva`, `Ra'anana`). A city name used in
  several countries (`London`) takes the one the place's other parts point to (`San Francisco, CA` → US), else
  none. The codes are stored in `postings.country` (`IL`, or `DE,IL` for several) and shown on cards.
- `location_rule.py`: a posting passes when its country is the profile location's country. With the toggle, a fully
  remote posting passes too: its location or title says remote without naming a place, or its description says
  "fully remote", "remote anywhere" or "work from anywhere"; `Remote - US` names a place and fails. A posting (or a
  profile location) with no known country passes only when its location, title or description contains the profile
  location.
- **Scan**: a new job that fails is not stored and costs no LLM call. Each scan looks at it again, so it arrives
  once your location allows it.
- **Save** in the Profile view applies the job-title keywords and the location to the stored postings without
  scoring (`POST /api/rescore/filters`, `profile_sweep.py`): postings in New that fail move to the **Archive**,
  `closed` / `not_relevant` with reason `location: <its location>` (or `keywords: ...`), so a typo never deletes
  anything; ones the rules archived that now pass come back to New. **Re-score all** does the same first. Postings
  you pasted or moved yourself (Applied, Interview, Closed) are never touched. **Purge rejects** in the Archive
  deletes the keyword and location rejects for good (after a confirm).
- Cards show a **Remote** badge when the location or title says remote or the description uses one of the phrases
  above (`postings.is_remote`). The filter bar's **Location** box matches the location with spellings normalized
  (`tel-aviv` finds `Tel Aviv-Yafo`).

## Scoring

Upload your CV in the **Profile** view (drop a `.pdf`, `.docx`, `.md` or `.txt`, max 5 MB). Its text is extracted
(pypdf / python-docx / plain read) into an editable box, the original is kept in `data/profile/`, and you add
**Targets** (what you are looking for). Save stores both in the single-row `profile` table.

`scorer.py` sends the profile plus a posting's title, company, location and description (cut to
`llm.max_text_chars`) to the active provider and expects strict JSON
`{"relevant": bool, "fit": 0-10, "reason": "...", "gaps": ["..."]}`; the rubric in `prompts/score_system.txt` checks
hard requirements first, accepts only Israel or remote-from-Israel, and rejects intern/student/junior roles. The
answer is validated with Pydantic; a bad answer is retried once, then stored as `fit = NULL` with reason
`parse error`. Without a profile the reason is `no profile`. 429 and 5xx answers are retried once (honouring
`Retry-After`), and requests run `providers.<name>.concurrency` at a time.

- **Scan**: a new posting that passes the job-title keywords and the location rule (others are not stored) goes to
  `new` with its score. The score never moves a card: a low fit stays in New for you to judge, and its badge is greyed
  when it is below `llm.threshold`.
- **Board**: cards show a `fit N` badge (reason and gaps on hover); the New column is sorted by fit, best first,
  then newest.
- **Re-score all** (Profile view, after changing the CV or targets) applies the keywords and the location rule, then
  re-scores every posting that is unscored or in New, with a progress bar. A posting you have moved on (applied,
  interview, closed) keeps its status and only gets the new score. **Re-score** in a posting's
  side panel does one.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/postings` | newest first; filters (in SQL): `q` (title substring), `in_text` (also the description), `company` and `source` (repeatable), `min_fit` (0-10; unscored postings always pass), `location` (substring, spellings normalized), `archived` (true: only the scorer's, the keywords' and the location rule's rejects; default false hides them) |
| GET | `/api/postings/facets` | companies and sources that have postings, unfiltered count per column |
| POST | `/api/postings` | paste: `company, title, url, text?` → 201 created, 200 if the same job (canonical URL) exists |
| PATCH | `/api/postings/{id}` | `status?, outcome?, note?`; leaving closed clears outcome; outcome on an open posting → 422 |
| DELETE | `/api/postings/rejects` | Purge rejects: deletes the postings the keywords or the location rule archived → `{deleted}` |
| GET | `/api/companies` | alphabetical |
| POST | `/api/companies` | `name, domain?, careers_url?` → 201 created, 200 if the name exists (any case); with a domain it is included in Discover |
| PATCH | `/api/companies/{id}` | `enabled?, careers_url?` (null clears) |
| POST | `/api/discover` | → `{ok, failed, duration_s}` |
| POST | `/api/scan` | starts a scan in the background → 202 with its status; 409 while a discover or scan runs |
| GET | `/api/scan/status` | `{running, boards_done, boards, failed, scored, to_score, duration_s, error}` |
| GET | `/api/settings/llm` | active provider, model, endpoint, whether its key is set |
| PUT | `/api/settings/llm/provider` | `{provider}` → rewrites `llm.provider` in `config.yaml` |
| POST | `/api/settings/llm/test` | → `{ok, provider, model, latency_ms, raw, error}` |
| GET | `/api/profile` | `{cv_text, targets, filename, uploaded_at, location, allow_fully_remote, country, include_keywords, exclude_keywords}` (country: what the location resolves to); blank until you upload or save |
| POST | `/api/profile` | multipart `file` (.pdf, .docx, .md, .txt) → extracted text; 413 over 5 MB, 422 unsupported or no text |
| PATCH | `/api/profile` | `cv_text?, targets?, location?, allow_fully_remote?, include_keywords?, exclude_keywords?` (lists of words or phrases; trimmed, blanks and repeats dropped) |
| POST | `/api/rescore` | applies the keywords and the location rule, then 202 and re-scores unscored and New postings in the background; 409 while one runs |
| GET | `/api/rescore/status` | `{running, done, total, error}` |
| POST | `/api/rescore/filters` | applies the profile's keywords and location to the stored postings, no scoring → `{archived, restored}`; 409 during Re-score all |
| POST | `/api/rescore/{id}` | keywords and location rule, then re-score one posting → the posting; 404 if missing |

Interactive docs at `/docs` while the server runs.

## Test

```powershell
pytest backend
```

## Layout

```
config.yaml                 seed company names, LLM providers, db path
environment.yml             conda env "job-board" (Python 3.13)
backend/job_board/
  main.py                   ASGI entry point
  app_factory.py            FastAPI assembly: DB lifecycle, routes, static frontend
  api/                      one router per resource
    posting_routes.py         /api/postings
    company_routes.py         /api/companies
    run_routes.py             /api/discover, /api/scan, /api/scan/status (one run at a time)
    settings_routes.py        /api/settings/llm (show, switch provider, test)
    profile_routes.py         /api/profile (upload, show, edit)
    rescore_routes.py         /api/rescore (all in the background, progress, one)
  config/
    app_config.py             config.yaml loader
    company_seed.py           a company entry from config.yaml
    config_editor.py          rewrites llm.provider in config.yaml, keeping comments
    llm_settings.py, llm_settings_parser.py, llm_provider.py   the llm and providers sections
    paths.py                  repo-relative locations
  storage/
    database.py               SQLite connections, schema, migrations, WAL mode
    posting_repository.py     postings table access (posting_filter.py: the filter bar's query)
    company_repository.py     companies table access
    profile_repository.py     the single-row profile table
  llm/
    llm_client.py             the only LLM entry point (openai SDK, OpenAI-compatible providers)
    scorer.py                 profile + posting -> FitResult through the LLM
  rules/
    keyword_filter.py         wanted / excluded roles on the job title, or "keywords: ..." for the Archive
    location_rule.py          profile location / fully remote -> keep, or "location: ..." for the Archive
    location_resolver.py      location text -> ISO country codes (board field, country name, geonamescache city)
    place_names.py            one spelling per place (Tel-Aviv, Petach Tikva, Ra'anana)
    profile_sweep.py          applies the keywords and the location rule to the stored postings
  runs/
    discover.py               Discover orchestrator + CLI
    scan.py                   Scan orchestrator + CLI
    scan_job.py               background scan with progress
    rescore_job.py            background Re-score all with progress
  boards/                   BoardLinkFinder, CareersSiteFinder, WorkdayTenantProbe, one BoardSource per platform
                            (Greenhouse, Lever, Ashby, Comeet, Workday, Eightfold, HiBob, Google, Microsoft, Apple,
                            Amazon, Meta)
  utils/                    HTTP client, CV text from .pdf/.docx/.md/.txt, job URL normalizing, JSON narrowing,
                            HTML -> text, domain normalization, sql/ and prompts/ file loading
  enums/                    Status, Outcome, Platform, Source
  models/                   Pydantic API models, one per file
  sql/                      one .sql file per statement, by table; migrations/
  prompts/                  LLM prompt texts
backend/tests/
frontend/src/               Vite + TypeScript, no framework
  main.ts                   wires the views, tabs and panel together; style.css
  api/
    api.ts                    fetch wrappers
    types.ts                  generated from /openapi.json (committed)
    domain.ts                 type aliases and labels
  views/                    one per tab
    board.ts                  four columns ("shown / total"), SortableJS drag -> PATCH, fit greyed below the threshold
    filter-bar.ts             search, location, company/source pickers, min-fit slider, Clear
    filter-url.ts             filter <-> URL query and localStorage
    archive-view.ts           keyword and location rejects with reason, Re-open, Purge rejects
    companies-view.ts         companies table, Add company, Discover, Scan with progress
    profile-view.ts           location + fully remote, job titles, targets, CV drop zone and text, Re-score all
    settings-view.ts          LLM provider drop-down, Test button
  panels/                   what the right-hand panel shows
    side-panel.ts             the panel shell
    posting-details.ts        location, country, link, fit, description, note, outcome
    paste-form.ts             add a posting found elsewhere
  ui/
    outcome-dialog.ts         "How did it end?" when dropping into Closed
    confirm-dialog.ts         yes/no for actions that cannot be undone (Purge rejects)
    keyword-list.ts           editable chips for the job-title keywords
    notice.ts, dom.ts         toasts; the el() element builder
data/                       SQLite file, uploaded CV, backups/ (all git-ignored)
```

Conventions: one class per file, full type hints, zero PyCharm warnings.
