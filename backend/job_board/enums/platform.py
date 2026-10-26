"""Company careers platform enum."""

from enum import StrEnum


class Platform(StrEnum):
    """Applicant-tracking system behind a company's careers page.

    GOOGLE, MICROSOFT, APPLE, AMAZON and META are single-company careers sites with their own JSON search APIs;
    EIGHTFOLD is any other careers site run on Eightfold (the system behind Microsoft's); HIBOB a careers site on HiBob.
    NONE means discovery ran and found no supported platform (a proprietary portal);
    a NULL platform in the database means discovery has not run yet.
    """

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    COMEET = "comeet"
    WORKDAY = "workday"
    EIGHTFOLD = "eightfold"
    HIBOB = "hibob"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    APPLE = "apple"
    AMAZON = "amazon"
    META = "meta"
    NONE = "none"
