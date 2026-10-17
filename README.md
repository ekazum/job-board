# job-board

Collect job postings in one place and track where each application stands.

## How postings get in

- **Paste** (main path): found a posting anywhere — LinkedIn, a careers page, a recruiter email — paste
  URL, title, company and the description into the form and it becomes a card. LinkedIn has no API you're
  allowed to read, so this is how most postings arrive.
- **Scan** (complement): `discover` finds which applicant-tracking system each company in your list uses
  (Greenhouse, Lever, Ashby, Comeet); `scan` reads those boards, keeps titles matching your keywords, and
  adds them as `new` cards. It only covers companies you've named.

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
python -m job_board.discover   # or POST /api/discover
python -m job_board.scan       # or POST /api/scan
```

- **discover** fetches `careers_url` (config, else the one saved in the Companies view) together with
  `https://<domain>/careers`, `/jobs`, `/join-us`, and takes the board linked from the first of them that has one:
  Greenhouse, Lever, Ashby, Comeet (hosted page, `careers-api` URL, or the careers widget's `company-uid`/`token`)
  or Workday (`<tenant>.wd<N>.myworkdayjobs.com/<site>`). A link is verified against that platform's API. Without
  a link, the domain stem (`acme` for `acme.co.il`) is probed on Greenhouse, Lever and Ashby; a guessed Greenhouse
  board whose name is another company's is rejected. Nothing found → `platform = none`.
- **scan** reads every verified + enabled company's board and adds jobs whose **title** matches a wanted role
  (`keywords.include`) and no excluded one (`keywords.exclude`) as `new`. `"AI + engineer"` means the title
  contains both words. Existing `(source, external_id)` rows are skipped (`ON CONFLICT DO NOTHING`), so a rescan
  never duplicates a card or resets its status.
- **Comeet** boards with a token are read through `careers-api/2.0/company/<uid>/positions`; hosted-page boards
  (no token) through the page's embedded positions. **Workday** sites are searched once per wanted role, and only
  jobs located in `workday_locations` (default `[Israel]`) are kept.
- Companies run concurrently (10 requests at a time, 15 s timeout, one retry on timeout or 5xx). A company that
  fails gets its reason in `last_error` (shown in red in the Companies view) and the run carries on; a later
  successful run clears it. Both runs re-read `config.yaml`, and only one runs at a time (a second gets 409).
- The database schema is versioned (`PRAGMA user_version`); `sql/migrations/` brings older files up to date on
  start and keeps their rows.

Regenerate frontend types after changing API models (backend must be running):
`npm --prefix frontend run gen:types`. `frontend/src/types.ts` is committed.

## LLM provider

`backend/job_board/llm_client.py` is the only code that talks to an LLM (and the only importer of `openai`). Every
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

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/postings` | newest first; filters (in SQL): `q` (title substring), `in_text` (also the description), `company` and `source` (repeatable), `min_fit` (0-10; unscored postings always pass) |
| GET | `/api/postings/facets` | companies and sources that have postings, unfiltered count per column |
| POST | `/api/postings` | paste: `company, title, url, text?` → 201 created, 200 if the same job (canonical URL) exists |
| PATCH | `/api/postings/{id}` | `status?, outcome?, note?`; leaving closed clears outcome; outcome on an open posting → 422 |
| GET | `/api/companies` | alphabetical |
| POST | `/api/companies` | `name, domain?, careers_url?` → 201 created, 200 if the name exists (any case); with a domain it is included in Discover |
| PATCH | `/api/companies/{id}` | `enabled?, careers_url?` (null clears) |
| POST | `/api/discover` | → `{ok, failed, duration_s}` |
| POST | `/api/scan` | → `{ok, failed, duration_s}` |
| GET | `/api/settings/llm` | active provider, model, endpoint, whether its key is set |
| PUT | `/api/settings/llm/provider` | `{provider}` → rewrites `llm.provider` in `config.yaml` |
| POST | `/api/settings/llm/test` | → `{ok, provider, model, latency_ms, raw, error}` |

Interactive docs at `/docs` while the server runs.

## Test

```powershell
pytest backend
```

## Layout

```
config.yaml                 keywords, seed company names, db path
environment.yml             conda env "job-board" (Python 3.12, Node 22)
backend/job_board/
  main.py                   ASGI entry point
  app_factory.py            FastAPI assembly: DB lifecycle, routes, static frontend
  app_config.py             config.yaml loader
  database.py               SQLite connections, schema, WAL mode
  posting_repository.py     postings table access
  company_repository.py     companies table access
  posting_routes.py         /api/postings
  company_routes.py         /api/companies
  run_routes.py             /api/discover, /api/scan (one run at a time)
  settings_routes.py        /api/settings/llm (show, switch provider, test)
  llm_client.py             the only LLM entry point (openai SDK, OpenAI-compatible providers)
  config_editor.py          rewrites llm.provider in config.yaml, keeping comments
  prompts/                  LLM prompt texts
  discover.py               Discover orchestrator + CLI
  scan.py                   Scan orchestrator + CLI
  keyword_filter.py         wanted / excluded roles on the job title
  http_client.py            async httpx client: concurrency limit, timeout, one retry
  url_normalizer.py         canonical job URL (external_id for pasted postings)
  company_seed.py           a company entry from config.yaml
  paths.py                  repo-relative locations
  boards/                   BoardLinkFinder, one BoardSource per platform (Greenhouse, Lever, Ashby, Comeet, Workday)
  utils/                    JSON narrowing, HTML → text, domain normalization
  enums/                    Status, Outcome, Platform, Source
  models/                   Pydantic API models, one per file
backend/tests/
frontend/src/               Vite + TypeScript, no framework
  types.ts                  generated from /openapi.json (committed)
  domain.ts                 type aliases and labels
  api.ts                    fetch wrappers
  board.ts                  four columns ("shown / total"), SortableJS drag → PATCH
  filter-bar.ts             search, company/source pickers, min-fit slider, Clear
  filter-url.ts             filter <-> URL query and localStorage
  outcome-dialog.ts         "How did it end?" when dropping into Closed
  side-panel.ts             right-hand panel shell
  posting-details.ts        link, description, note, outcome
  paste-form.ts             add a posting found elsewhere
  companies-view.ts         companies table, Add company, Discover, Scan
  settings-view.ts          LLM provider drop-down, Test button
  notice.ts, dom.ts, main.ts
data/                       SQLite file (git-ignored)
```

Conventions: one class per file, full type hints, zero PyCharm warnings.
