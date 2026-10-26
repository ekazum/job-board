"""Spelling-insensitive place names, shared by LocationResolver and LocationRule."""

import re
import unicodedata

APOSTROPHES = re.compile(r"['‘’ʼ`´׳]")
SEPARATORS = re.compile(r"[\W_]+")
# Words that may stand next to a place without naming one ("Remote (anywhere)", "Israel, Multiple Locations").
NOT_PLACES = frozenset(
    "remote fully 100 anywhere everywhere worldwide global globally work from home based first friendly only flexible "
    "distributed position role job location locations multiple hybrid office onsite or and in the of a any ok possible "
    "option optional".split()
)
# Other spellings of a place, as they read after the earlier steps of normalize().
ALIASES: dict[str, tuple[str, ...]] = {
    "tel aviv": (
        "tel aviv yafo",
        "tel aviv jaffa",
        "tel aviv yaffo",
        "telaviv",
        "tlv",
        "תל אביב יפו",
        "תל אביב",
        "ת א",  # ת"א
    ),
    "petah tikva": (
        "petach tikva",
        "petach tikvah",
        "petah tikvah",
        "petah tiqva",
        "petach tiqva",
        "petah tiqwa",
        "petakh tikva",
        "פתח תקווה",
        "פתח תקוה",
    ),
    "herzliya": ("herzlia", "herzelia", "herzeliya", "hertzliya", "hertzlia", "hertzelia", "herzliyya", "הרצליה"),
    "raanana": ("ra anana", "ranana", "רעננה"),
    "jerusalem": ("yerushalayim", "ירושלים"),
    "haifa": ("חיפה",),
    "israel": ("ישראל",),
    "beer sheva": ("beersheba", "beer sheba", "beersheva"),
    "rishon lezion": ("rishon le zion", "rishon letsiyyon", "rishon letsiyon"),
    "kfar saba": ("kfar sava", "kefar sava", "kefar saba"),
    "netanya": ("natanya", "netania"),
    "rehovot": ("rechovot",),
    "hod hasharon": ("hod ha sharon",),
    "bnei brak": ("bene beraq", "bnei braq"),
    "yokneam": ("yoqneam illit", "yokneam illit", "yoqneam"),
    "lod": ("ben gurion airport", "נמל התעופה בן גוריון", "נתב ג", "לוד"),  # the airport, Natbag (נתב"ג), is at Lod
    "remote": ("work from home", "wfh"),
}
ALIAS_PATTERNS = tuple(
    (canonical, re.compile(r"\b(?:" + "|".join(re.escape(variant) for variant in sorted(variants, key=len, reverse=True)) + r")\b"))
    for canonical, variants in ALIASES.items()
)


class PlaceNames:
    """Brings different spellings of a place to one form, so they compare equal or as substrings."""

    @staticmethod
    def normalize(value: str) -> str:
        """Lower case without accents or apostrophes, punctuation as single spaces, and known spellings of a place
        replaced by one ("Tel-Aviv-Yafo" -> "tel aviv", "Ra'anana" -> "raanana", "Petach Tikva" -> "petah tikva")."""
        words = PlaceNames.plain(value)
        for canonical, pattern in ALIAS_PATTERNS:
            words = pattern.sub(canonical, words)
        return words

    @staticmethod
    def plain(value: str) -> str:
        """normalize() without the known spellings: lower case, no accents or apostrophes, punctuation as spaces."""
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        letters = "".join(character for character in decomposed if not unicodedata.combining(character))
        return SEPARATORS.sub(" ", APOSTROPHES.sub("", letters)).strip()

    @staticmethod
    def place_words(value: str) -> str:
        """The normalized words of value that may name a place ("Remote - US" -> "us"; "Remote" -> "")."""
        return " ".join(word for word in PlaceNames.normalize(value).split() if word not in NOT_PLACES)
