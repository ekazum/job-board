"""What a pasted posting's link says about its company: its job board or its website."""

from collections.abc import Sequence
from urllib.parse import urlsplit

from job_board.boards.board_link_finder import BoardLinkFinder
from job_board.boards.board_ref import BoardRef
from job_board.config.company_seed import CompanySeed
from job_board.utils.domains import domain_stem, registrable_domain, same_company


class PostingCompanyFinder:
    """Turns a company named by pasted postings into a company to discover, from the postings' links.

    A link is used only when it is the company's own, so a job found on LinkedIn or through a recruiter does not hand
    the company someone else's board:
    1. a link to a job board (Comeet, Greenhouse, Lever, Ashby, Workday, HiBob) whose name matches the company name
       gives that board as the careers URL ("https://www.comeet.com/jobs/acme/A1.234/engineer/B5.678" ->
       "https://www.comeet.com/jobs/acme/A1.234");
    2. a link to a site whose domain matches the company name gives the domain, and the site as the careers URL when
       it is a subdomain ("https://jobs.acme.co.il/job/1" -> acme.co.il and "https://jobs.acme.co.il/").
    Names match as in discovery (Discover's guessed-board check): one contains the other, ignoring case and
    punctuation. The first link that says something wins; with none the company has neither, until one is typed in.
    """

    def __init__(self, link_finder: BoardLinkFinder | None = None) -> None:
        self._link_finder = link_finder or BoardLinkFinder()

    def find(self, company: str, urls: Sequence[str]) -> tuple[CompanySeed, BoardRef | None]:
        """The company with what its links give, and the board one of them names."""
        for url in urls:
            linked = self._link_finder.find_in_url(url)
            if linked is not None and same_company(company, self._board_name(linked[0])):
                board, board_url = linked
                return CompanySeed(name=company, domain=None, careers_url=board_url), board
            host = (urlsplit(url).hostname or "").lower()
            if "." in host and same_company(company, domain_stem(host)):
                domain = registrable_domain(host)
                site = None if host in (domain, f"www.{domain}") else f"https://{host}/"
                return CompanySeed(name=company, domain=domain, careers_url=site), None
        return CompanySeed(name=company, domain=None), None

    @staticmethod
    def _board_name(board: BoardRef) -> str:
        """The company part of a board's slug: "acme" for "acme", "acme/A1.234" (Comeet), "acme/External" (Workday)."""
        return board.slug.split("/")[0]
