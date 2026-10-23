from __future__ import annotations

import re
import unicodedata

# The site follows only these four clubs and their European competitions.
TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "Fenerbahçe": ("fenerbah",),
    "Galatasaray": ("galatasaray",),
    "Beşiktaş": ("besiktas",),
    "Trabzonspor": ("trabzonspor",),
}

COMPETITION_LABELS: dict[str, str] = {
    "CL": "UEFA Şampiyonlar Ligi",
    "EL": "UEFA Avrupa Ligi",
    "UECL": "UEFA Konferans Ligi",
}

COMPETITION_ORDER: dict[str, int] = {
    "CL": 10,
    "EL": 20,
    "UECL": 30,
}

_TR_MAP = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)


def normalize_name(value: str | None) -> str:
    text = (value or "").translate(_TR_MAP)
    # Fold the remaining accents (Atlético -> Atletico, Be'er -> Be'er, ...).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).casefold().strip()


def canonical_team_name(name: str | None) -> str | None:
    """Return the Turkish display name for a tracked club, if the name matches."""
    normalized = normalize_name(name)
    for canonical, aliases in TEAM_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def is_tracked_team(name: str | None) -> bool:
    return canonical_team_name(name) is not None


def is_tracked_match(home: str | None, away: str | None) -> bool:
    return is_tracked_team(home) or is_tracked_team(away)
