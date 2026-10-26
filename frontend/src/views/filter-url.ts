import type { PostingQuery, Source } from "../api/domain";

const STORAGE_KEY = "job-board.filter";
// Record<Source, …> makes the compiler flag a source added on the backend but missing here.
const SOURCE_NAMES: Record<Source, true> = {
  greenhouse: true,
  lever: true,
  ashby: true,
  comeet: true,
  workday: true,
  eightfold: true,
  hibob: true,
  google: true,
  microsoft: true,
  apple: true,
  amazon: true,
  meta: true,
  manual: true,
};
const SOURCES = Object.keys(SOURCE_NAMES) as Source[];

/** The filter as GET /api/postings query parameters (company and source repeated, empty values left out). */
export function toSearchParams(query: PostingQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.q) {
    params.set("q", query.q);
  }
  for (const company of query.company ?? []) {
    params.append("company", company);
  }
  for (const source of query.source ?? []) {
    params.append("source", source);
  }
  if (query.min_fit !== undefined && query.min_fit !== null && query.min_fit > 0) {
    params.set("min_fit", String(query.min_fit));
  }
  if (query.in_text) {
    params.set("in_text", "true");
  }
  if (query.location) {
    params.set("location", query.location);
  }
  if (query.archived) {
    params.set("archived", "true");
  }
  return params;
}

/** The filter read back from a query string; unknown sources and out-of-range fits are dropped. */
export function fromSearchParams(params: URLSearchParams): PostingQuery {
  const minFit = Number(params.get("min_fit"));
  return {
    q: params.get("q") ?? "",
    company: params.getAll("company"),
    source: params.getAll("source").filter((value): value is Source => SOURCES.some((source) => source === value)),
    min_fit: Number.isInteger(minFit) && minFit > 0 && minFit <= 10 ? minFit : null,
    in_text: params.get("in_text") === "true",
    location: params.get("location") ?? "",
  };
}

export function isEmpty(query: PostingQuery): boolean {
  return toSearchParams(query).toString() === "";
}

/** Put the filter into the address bar (keeping the #view), so a reload or a shared link restores it. */
export function writeToUrl(query: PostingQuery): void {
  const search = toSearchParams(query).toString();
  const url = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", url);
}

/** The last filter used in this browser, or an empty one (storage can be unavailable or cleared). */
export function loadRemembered(): PostingQuery {
  try {
    return fromSearchParams(new URLSearchParams(window.localStorage.getItem(STORAGE_KEY) ?? ""));
  } catch {
    return fromSearchParams(new URLSearchParams());
  }
}

export function remember(query: PostingQuery): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, toSearchParams(query).toString());
  } catch {
    // Storage blocked (private window, disabled site data): the URL still carries the filter.
  }
}
