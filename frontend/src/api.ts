import type {
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
  RunSummary,
} from "./domain";
import { toSearchParams } from "./filter-url";

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

/** Answers when the run is done (it can take minutes); 409 when another run is in progress. */
export async function runScan(): Promise<RunSummary> {
  return (await request<RunSummary>("POST", "/api/scan")).data;
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
