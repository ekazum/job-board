"""Error for a board that could not be read."""


class BoardUnavailableError(Exception):
    """The board could not be read right now: network failure, an HTTP status other than 200/404/410, or a
    malformed body. Distinct from "no such board" (404/410), which sources report by returning None."""
