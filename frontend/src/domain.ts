import type { components } from "./types";

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
export type DiscoverResult = Schemas["DiscoverResult"];
export type ScanResult = Schemas["ScanResult"];
export type RunIssue = Schemas["RunIssue"];

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
  none: "None found",
};

// Column order follows the label order above.
export const STATUSES = Object.keys(STATUS_LABELS) as Status[];
export const OUTCOMES = Object.keys(OUTCOME_LABELS) as Outcome[];

export function parseStatus(value: string | undefined): Status | null {
  return STATUSES.find((status) => status === value) ?? null;
}

export function parseOutcome(value: string | undefined): Outcome | null {
  return OUTCOMES.find((outcome) => outcome === value) ?? null;
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
