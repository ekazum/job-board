import { type ChatStreamEvent, readEvents } from "../chat/chat-stream";
import { toSearchParams } from "../views/filter-url";
import type {
  ChatHistory,
  ChatRequest,
  Company,
  CompanyCreate,
  CompanyPatch,
  LlmSettingsView,
  LlmTestResult,
  Posting,
  PostingCreate,
  PostingFacets,
  PostingPatch,
  PostingQuery,
  Profile,
  ProfilePatch,
  PurgeResult,
  RescoreStatus,
  RunSummary,
  ScanStatus,
  SweepResult,
} from "./domain";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Postings matching the filter (filtered on the server); all of them without one. */
export async function getPostings(query: PostingQuery = {}): Promise<Posting[]> {
  const search = toSearchParams(query).toString();
  return (await request<Posting[]>("GET", search ? `/api/postings?${search}` : "/api/postings")).data;
}

/** Companies and sources for the filter bar, and each column's unfiltered total. */
export async function getPostingFacets(): Promise<PostingFacets> {
  return (await request<PostingFacets>("GET", "/api/postings/facets")).data;
}

/** POST a pasted posting. `created` is false when the same job (by canonical URL) was already on the board. */
export async function createPosting(body: PostingCreate): Promise<{ posting: Posting; created: boolean }> {
  const { status, data } = await request<Posting>("POST", "/api/postings", body);
  return { posting: data, created: status === 201 };
}

export async function patchPosting(id: number, patch: PostingPatch): Promise<Posting> {
  return (await request<Posting>("PATCH", `/api/postings/${id}`, patch)).data;
}

/** Delete for good the postings the profile's keywords or location archived. */
export async function purgeRejects(): Promise<PurgeResult> {
  return (await request<PurgeResult>("DELETE", "/api/postings/rejects")).data;
}

export async function getCompanies(): Promise<Company[]> {
  return (await request<Company[]>("GET", "/api/companies")).data;
}

/** POST a company. `created` is false when a company with that name (any case) already exists. */
export async function createCompany(body: CompanyCreate): Promise<{ company: Company; created: boolean }> {
  const { status, data } = await request<Company>("POST", "/api/companies", body);
  return { company: data, created: status === 201 };
}

export async function patchCompany(id: number, patch: CompanyPatch): Promise<Company> {
  return (await request<Company>("PATCH", `/api/companies/${id}`, patch)).data;
}

/** Answers when the run is done (it can take minutes); 409 when another run is in progress. */
export async function runDiscover(): Promise<RunSummary> {
  return (await request<RunSummary>("POST", "/api/discover")).data;
}

/** Starts a scan in the background (202); 409 when a discover or scan run is in progress. */
export async function startScan(): Promise<ScanStatus> {
  return (await request<ScanStatus>("POST", "/api/scan")).data;
}

/** Progress of the current or last scan. */
export async function getScanStatus(): Promise<ScanStatus> {
  return (await request<ScanStatus>("GET", "/api/scan/status")).data;
}

export async function getLlmSettings(): Promise<LlmSettingsView> {
  return (await request<LlmSettingsView>("GET", "/api/settings/llm")).data;
}

/** Writes llm.provider into config.yaml; the next request already uses it. */
export async function setLlmProvider(provider: string): Promise<LlmSettingsView> {
  return (await request<LlmSettingsView>("PUT", "/api/settings/llm/provider", { provider })).data;
}

/** One tiny scoring request; failures come back in the result (ok=false), not as an HTTP error. */
export async function testLlm(): Promise<LlmTestResult> {
  return (await request<LlmTestResult>("POST", "/api/settings/llm/test")).data;
}

/** The candidate profile (blank, with no location, before the first upload or edit). */
export async function getProfile(): Promise<Profile> {
  return (await request<Profile>("GET", "/api/profile")).data;
}

/** Upload a .pdf, .docx, .md or .txt CV (max 5 MB); the server extracts its text into the profile. */
export async function uploadProfile(file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/profile", { method: "POST", body: form });
  if (!response.ok) {
    throw new ApiError(response.status, await describeFailure(response));
  }
  return (await response.json()) as Profile;
}

export async function patchProfile(patch: ProfilePatch): Promise<Profile> {
  return (await request<Profile>("PATCH", "/api/profile", patch)).data;
}

/** Apply the profile's job-title keywords and location to the stored postings without scoring; 409 while Re-score all runs. */
export async function applyFilters(): Promise<SweepResult> {
  return (await request<SweepResult>("POST", "/api/rescore/filters")).data;
}

/** Apply the keywords and the location, then start Re-score all in the background; 409 while one is running. */
export async function startRescore(): Promise<RescoreStatus> {
  return (await request<RescoreStatus>("POST", "/api/rescore")).data;
}

export async function getRescoreStatus(): Promise<RescoreStatus> {
  return (await request<RescoreStatus>("GET", "/api/rescore/status")).data;
}

/** Apply the location rule to one posting and score it unless that archived it. */
export async function rescorePosting(id: number): Promise<Posting> {
  return (await request<Posting>("POST", `/api/rescore/${id}`)).data;
}

export async function getPosting(id: number): Promise<Posting> {
  return (await request<Posting>("GET", `/api/postings/${id}`)).data;
}

/** Ask the chat agent; each event of the answer goes to onEvent as it arrives, until the stream ends or signal aborts. */
export async function streamChat(
  message: string,
  threadId: string | null,
  onEvent: (event: ChatStreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const body: ChatRequest = { message, thread_id: threadId };
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new ApiError(response.status, await describeFailure(response));
  }
  for await (const event of readEvents(response.body)) {
    onEvent(event);
  }
}

export async function getChatHistory(threadId: string): Promise<ChatHistory> {
  return (await request<ChatHistory>("GET", `/api/chat/${encodeURIComponent(threadId)}`)).data;
}

export async function deleteChat(threadId: string): Promise<void> {
  const response = await fetch(`/api/chat/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(response.status, await describeFailure(response));
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<{ status: number; data: T }> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await describeFailure(response));
  }
  return { status: response.status, data: (await response.json()) as T };
}

/** FastAPI sends {detail: string} for HTTPException and {detail: [{msg, loc}]} for validation errors. */
async function describeFailure(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json();
    if (typeof payload === "object" && payload !== null && "detail" in payload) {
      const { detail } = payload;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail)) {
        return detail.map(describeValidationItem).join("; ");
      }
    }
  } catch {
    // Body was not JSON; fall through to the status line.
  }
  return `${response.status} ${response.statusText}`.trim();
}

function describeValidationItem(item: unknown): string {
  if (typeof item === "object" && item !== null && "msg" in item) {
    const field = "loc" in item && Array.isArray(item.loc) ? item.loc.at(-1) : undefined;
    return field === undefined ? String(item.msg) : `${String(field)}: ${String(item.msg)}`;
  }
  return String(item);
}
