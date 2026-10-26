"""The board's tools, served over MCP at /mcp: the read-only ones here and the ones that change the board
(board_actions.py). The chat window's agent uses them, and so can any MCP client (Claude Code:
`claude mcp add --transport http job-board http://127.0.0.1:8000/mcp/`)."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from job_board.enums.status import Status
from job_board.models.company import Company
from job_board.models.posting import Posting
from job_board.storage.company_repository import CompanyRepository
from job_board.storage.posting_filter import PostingFilter
from job_board.storage.posting_repository import PostingRepository
from job_board.storage.profile_repository import ProfileRepository
from job_board.tools.board_actions import BoardActions, PostingId
from job_board.tools.compact_json import compact_json

MOUNT_PATH = "/mcp"
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
CHANGES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)  # updates, never deletes
# Only requests addressed to this machine, and none from a web page (browsers send an Origin header; MCP clients
# such as the chat agent and Claude Code do not), so no site can reach the tools, by DNS rebinding or otherwise.
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
NO_ORIGINS: list[str] = []
MAX_ROWS = 50
BEST_NEW = 5
POSTING_TEXT_CHARS = 2500
CV_CHARS = 4000
SCANNED = "scanned"
INSTRUCTIONS = (
    "Tools over a personal job board: read the postings with their LLM fit score, the profile and the companies; "
    "move or close a posting, add to its note, start a scan."
)


class BoardTools:
    """search_postings, get_posting, get_profile, board_summary and list_companies over the repositories, plus the
    actions' tools on the same server. Each answer is compact JSON (a posting row is id, title, company, status, fit,
    location), so a small local model's context holds many; get_posting gives one posting in full. Nothing here
    changes the board."""

    def __init__(
        self, postings: PostingRepository, companies: CompanyRepository, profiles: ProfileRepository, actions: BoardActions
    ) -> None:
        self._postings = postings
        self._companies = companies
        self._profiles = profiles
        self._actions = actions

    def server(self) -> FastMCP:
        """A FastMCP server with every tool (the actions' marked as changing the board), stateless, its endpoint at the
        root of wherever it is mounted."""
        server = FastMCP(
            "job-board",
            instructions=INSTRUCTIONS,
            stateless_http=True,
            json_response=True,
            streamable_http_path="/",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True, allowed_hosts=LOCAL_HOSTS, allowed_origins=NO_ORIGINS
            ),
        )
        for tool in (self.search_postings, self.get_posting, self.get_profile, self.board_summary, self.list_companies):
            server.add_tool(tool, annotations=READ_ONLY, structured_output=False)
        for action in self._actions.tools():
            server.add_tool(action, annotations=CHANGES, structured_output=False)
        return server

    def search_postings(
        self,
        text: Annotated[str, Field(description="Words in the title or the description; empty for any")] = "",
        company: Annotated[str, Field(description="Part of the company name; empty for any")] = "",
        status: Annotated[str, Field(description="new, applied, interview or closed; empty for any")] = "",
        min_fit: Annotated[int, Field(description="Lowest fit score, 0-10; 0 also includes unscored postings", ge=0, le=10)] = 0,
        location: Annotated[str, Field(description="Part of the location, e.g. Tel Aviv; empty for any")] = "",
        limit: Annotated[int, Field(description="How many postings to return", ge=1, le=MAX_ROWS)] = 20,
    ) -> str:
        """Find postings on the board (not the Archive), best fit first. Each has id, title, company, status, fit (0-10,
        null when not scored) and location."""
        wanted = Status(status.strip().lower()) if status.strip() else None
        found = self._postings.search(PostingFilter(text=text.strip(), in_text=True, location=location.strip()))
        name = company.strip().casefold()
        matches = [
            posting
            for posting in found
            if (not name or name in posting.company.casefold())
            and (wanted is None or posting.status is wanted)
            and (min_fit == 0 or (posting.fit is not None and posting.fit >= min_fit))
        ]
        best = self._by_fit(matches)[:limit]
        return compact_json({"count": len(matches), "postings": [self._row(posting) for posting in best]})

    def get_posting(self, posting_id: PostingId) -> str:
        """One posting in full: the fit score with its reason and the requirements the candidate lacks (gaps), the
        status and outcome, the note, the link and the description."""
        posting = self._postings.get(posting_id)
        if posting is None:
            raise ValueError(f"there is no posting #{posting_id}")
        return compact_json(
            {
                **self._row(posting),
                "outcome": posting.outcome,
                "fit_reason": posting.fit_reason,
                "gaps": posting.fit_gaps,
                "remote": posting.is_remote,
                "note": posting.note,
                "added": posting.created_at.date().isoformat(),
                "url": posting.url,
                "description": posting.text[:POSTING_TEXT_CHARS],
            }
        )

    def get_profile(self) -> str:
        """The candidate: wanted and excluded job titles, location, whether fully remote jobs are welcome, what they are
        looking for (targets) and their CV."""
        profile = self._profiles.get()
        if profile is None:
            return compact_json({"profile": None, "note": "no profile has been saved yet"})
        return compact_json(
            {
                "wanted_titles": profile.include_keywords,
                "excluded_titles": profile.exclude_keywords,
                "location": profile.location,
                "fully_remote_ok": profile.allow_fully_remote,
                "targets": profile.targets,
                "cv": profile.cv_text[:CV_CHARS],
            }
        )

    def board_summary(self) -> str:
        """How many postings each board column holds, how many are in the Archive, and the best-fitting New ones."""
        new = [posting for posting in self._postings.search(PostingFilter()) if posting.status is Status.NEW]
        return compact_json(
            {
                "columns": {status.value: total for status, total in self._postings.facets().totals.items()},
                "archived": len(self._postings.search(PostingFilter(archived=True))),
                "best_new": [self._row(posting) for posting in self._by_fit(new)[:BEST_NEW]],
            }
        )

    def list_companies(
        self,
        only_problems: Annotated[
            bool, Field(description="true: only the companies whose jobs are not being read (any state but scanned)")
        ] = False,
    ) -> str:
        """The companies whose job boards are read, each with its board's platform and its state: "scanned", "scanning
        off" (switched off in the Companies view), "no board found" (Discover found no job board to read) or
        "error: <why the last read failed>"."""
        companies = [
            {"name": company.name, "platform": company.platform, "state": self._state(company)}
            for company in self._companies.list_all()
        ]
        if only_problems:
            companies = [company for company in companies if company["state"] != SCANNED]
        return compact_json({"count": len(companies), "companies": companies})

    @staticmethod
    def _state(company: Company) -> str:
        """Whether a company's jobs are being read, in words."""
        if company.last_error:
            return f"error: {company.last_error}"
        if not company.verified:
            return "no board found"
        return SCANNED if company.enabled else "scanning off"

    @staticmethod
    def _by_fit(postings: list[Posting]) -> list[Posting]:
        """Highest fit first, unscored last; ties keep their order (newest first)."""
        return sorted(postings, key=lambda posting: -1 if posting.fit is None else posting.fit, reverse=True)

    @staticmethod
    def _row(posting: Posting) -> dict[str, object]:
        """The short form of a posting."""
        return {
            "id": posting.id,
            "title": posting.title,
            "company": posting.company,
            "status": posting.status,
            "fit": posting.fit,
            "location": posting.location,
        }
