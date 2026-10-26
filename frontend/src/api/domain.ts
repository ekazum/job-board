import type { components, operations } from "./types";

type Schemas = components["schemas"];

export type Posting = Schemas["Posting"];
export type PostingCreate = Schemas["PostingCreate"];
export type PostingPatch = Schemas["PostingPatch"];
export type Status = Schemas["Status"];
export type Outcome = Schemas["Outcome"];
export type Company = Schemas["Company"];
export type CompanyCreate = Schemas["CompanyCreate"];
export type CompanyPatch = Schemas["CompanyPatch"];
export type Platform = Schemas["Platform"];
export type RunSummary = Schemas["RunSummary"];
export type LlmSettingsView = Schemas["LlmSettingsView"];
export type LlmTestResult = Schemas["LlmTestResult"];
export type PostingFacets = Schemas["PostingFacets"];
export type Profile = Schemas["Profile"];
export type ProfilePatch = Schemas["ProfilePatch"];
export type PurgeResult = Schemas["PurgeResult"];
export type SweepResult = Schemas["SweepResult"];
export type RescoreStatus = Schemas["RescoreStatus"];
export type ScanStatus = Schemas["ScanStatus"];
export type Source = Schemas["Source"];
/** The filter bar's state: exactly the query parameters of GET /api/postings. */
export type PostingQuery = NonNullable<operations["list_postings"]["parameters"]["query"]>;

// Record<Status, …> makes the compiler flag a status added on the backend but not labelled here.
export const STATUS_LABELS: Record<Status, string> = {
  new: "New",
  applied: "Applied",
  interview: "Interview",
  closed: "Closed",
};

export const OUTCOME_LABELS: Record<Outcome, string> = {
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  offer: "Offer",
  not_relevant: "Not relevant",
};

export const PLATFORM_LABELS: Record<Platform, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  comeet: "Comeet",
  workday: "Workday",
  eightfold: "Eightfold",
  hibob: "HiBob",
  google: "Google careers",
  microsoft: "Microsoft careers",
  apple: "Apple careers",
  amazon: "Amazon careers",
  meta: "Meta careers",
  none: "None found",
};

// Column order follows the label order above.
export const STATUSES = Object.keys(STATUS_LABELS) as Status[];
export const OUTCOMES = Object.keys(OUTCOME_LABELS) as Outcome[];

export type ProfileRule = "keywords" | "location";

/**
 * Which of the profile's rules closed this posting: the job-title keywords (fit_reason "keywords: …") or the location
 * (fit_reason "location: …"); null for any other posting. Such a posting sits in the Archive.
 */
export function ruleReject(posting: Posting): ProfileRule | null {
  if (posting.status !== "closed" || posting.outcome !== "not_relevant") {
    return null;
  }
  const reason = posting.fit_reason ?? "";
  if (reason.startsWith("keywords: ")) {
    return "keywords";
  }
  return reason.startsWith("location: ") ? "location" : null;
}

/** One of the profile's rules put this posting in the Archive, so the board does not show it. */
export function isArchived(posting: Posting): boolean {
  return ruleReject(posting) !== null;
}

export function parseStatus(value: string | undefined): Status | null {
  return STATUSES.find((status) => status === value) ?? null;
}

export function parseOutcome(value: string | undefined): Outcome | null {
  return OUTCOMES.find((outcome) => outcome === value) ?? null;
}

/** Best fit first, unscored postings last, then newest first: the order of the New column. */
export function byFit(a: Posting, b: Posting): number {
  const fitA = a.fit ?? -1;
  const fitB = b.fit ?? -1;
  return fitB - fitA || byNewest(a, b);
}

/** Newest first, matching the backend's ORDER BY created_at DESC, id DESC. */
export function byNewest(a: Posting, b: Posting): number {
  return b.created_at.localeCompare(a.created_at) || b.id - a.id;
}

/** Alphabetical, case-insensitive, matching the backend's companies order closely enough for display. */
export function byName(a: Company, b: Company): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function isWebUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}
