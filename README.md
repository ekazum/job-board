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

- **discover** fetches `careers_url` (if set), then `https://<domain>/careers`, `/jobs`, `/join-us`, and looks for
  a Greenhouse, Lever, Ashby or Comeet board link (including Greenhouse `embed?for=` and redirects straight to a
  board). A link is verified against that platform's public API. Without a link, the domain stem (`acme` for
  `acme.co.il`) is probed on the Greenhouse, Lever and Ashby APIs. Nothing found → `platform = none`.
  Companies are upserted by name; `enabled` is never changed. A company whose boards could not be reached is
  reported in `issues` and its row is left as it was.
- **scan** reads every verified + enabled company's board, keeps jobs whose title + description match an
  include keyword and no exclude keyword, and adds them as `new`. Existing `(source, external_id)` rows are
  skipped (`ON CONFLICT DO NOTHING`), so a rescan never duplicates a card or resets its status.
- Comeet has no public API by slug; its hosted page embeds the positions as JSON, which is what scan reads.
  Comeet boards can only be found from a link, so give `careers_url` when a company's site doesn't use one of
  the standard paths.
- Both runs re-read `config.yaml`, and only one runs at a time (a second request gets 409).

Regenerate frontend types after changing API models (backend must be running):
`npm --prefix frontend run gen:types`. `frontend/src/types.ts` is committed.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/postings` | newest first |
| POST | `/api/postings` | paste: `company, title, url, text?` → 201 created, 200 if the same job (canonical URL) exists |
| PATCH | `/api/postings/{id}` | `status?, outcome?, note?`; leaving closed clears outcome; outcome on an open posting → 422 |
| GET | `/api/companies` | alphabetical |
| POST | `/api/companies` | `name, domain?` → 201 created, 200 if the name exists (any case); with a domain it is included in Discover |
| PATCH | `/api/companies/{id}` | `enabled?` |
| POST | `/api/discover` | → `{companies, verified, unverified, no_platform, issues}` |
| POST | `/api/scan` | → `{companies, jobs_seen, matched, added, issues}` |

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
  discover.py               Discover orchestrator + CLI
  scan.py                   Scan orchestrator + CLI
  keyword_filter.py         include/exclude on title + text
  http_client.py            requests wrapper (timeouts, no exceptions)
  url_normalizer.py         canonical job URL (external_id for pasted postings)
  company_seed.py           a company entry from config.yaml
  paths.py                  repo-relative locations
  boards/                   BoardLinkFinder, one BoardSource per platform, value objects
  utils/                    JSON narrowing, HTML → text, domain normalization
  enums/                    Status, Outcome, Platform, Source
  models/                   Pydantic API models, one per file
backend/tests/
frontend/src/               Vite + TypeScript, no framework
  types.ts                  generated from /openapi.json (committed)
  domain.ts                 type aliases and labels
  api.ts                    fetch wrappers
  board.ts                  four columns, SortableJS drag → PATCH
  outcome-dialog.ts         "How did it end?" when dropping into Closed
  side-panel.ts             right-hand panel shell
  posting-details.ts        link, description, note, outcome
  paste-form.ts             add a posting found elsewhere
  companies-view.ts         companies table, Add company, Discover, Scan
  notice.ts, dom.ts, main.ts
data/                       SQLite file (git-ignored)
```

Conventions: one class per file, full type hints, zero PyCharm warnings.
