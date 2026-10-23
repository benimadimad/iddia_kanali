from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..targets import (
    COMPETITION_LABELS,
    COMPETITION_ORDER,
    canonical_team_name,
    is_tracked_match,
)
from . import ProviderError, ProviderResult
from .espn import EspnProvider
from .football_data import FootballDataProvider

log = logging.getLogger(__name__)

# The four clubs followed by this league and the competitions they play in.
TRACKED_COMPETITIONS = ("CL", "EL", "UECL")


def _canonical_team(team: dict[str, Any]) -> dict[str, Any]:
    """Show the followed clubs with their proper Turkish names."""
    canonical = canonical_team_name(team.get("name"))
    if not canonical:
        return team
    return {**team, "name": canonical, "short": canonical}


class TrackedProvider:
    """Combines football-data.org and ESPN, keeping only the four tracked clubs."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def fetch(self, date_from: str, date_to: str) -> ProviderResult:
        results: list[ProviderResult] = []
        errors: list[str] = []
        complete = True

        # Champions League: prefer football-data.org (the configured API token).
        try:
            champions = FootballDataProvider(self.config).fetch_season("CL")
            if not any(
                is_tracked_match(match["home"]["name"], match["away"]["name"])
                for match in champions.matches
            ):
                raise ProviderError(
                    "football-data.org takip edilen takımlar için maç döndürmedi."
                )
            results.append(champions)
        except ProviderError as exc:
            log.warning("Champions League fallback to ESPN: %s", exc)
            errors.append(str(exc))
            try:
                results.append(EspnProvider(self.config).fetch(("CL",)))
            except ProviderError as fallback_exc:
                complete = False
                errors.append(str(fallback_exc))

        # Europa League and Conference League are not on the free football-data tier.
        try:
            results.append(EspnProvider(self.config).fetch(("EL", "UECL")))
        except ProviderError as exc:
            complete = False
            errors.append(str(exc))

        if not results:
            raise ProviderError("; ".join(errors) or "Veri kaynağına ulaşılamadı.")

        matches: list[dict[str, Any]] = []
        competitions: dict[str, dict[str, Any]] = {}
        seen: set[tuple[str, str]] = set()

        for result in results:
            for competition in result.competitions:
                code = competition.get("code")
                if code in TRACKED_COMPETITIONS and code not in competitions:
                    competitions[code] = {
                        **competition,
                        "name": COMPETITION_LABELS.get(
                            code, competition.get("name") or code
                        ),
                        "sort_order": COMPETITION_ORDER.get(
                            code, competition.get("sort_order", 100)
                        ),
                    }

            for match in result.matches:
                if match.get("competition_code") not in TRACKED_COMPETITIONS:
                    continue
                if not is_tracked_match(match["home"]["name"], match["away"]["name"]):
                    continue
                key = (match["provider"], str(match["external_id"]))
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    {
                        **match,
                        "home": _canonical_team(match["home"]),
                        "away": _canonical_team(match["away"]),
                    }
                )
                competitions.setdefault(
                    match["competition_code"],
                    {
                        "code": match["competition_code"],
                        "name": COMPETITION_LABELS.get(
                            match["competition_code"], match["competition_code"]
                        ),
                        "country": "Avrupa",
                        "emblem": None,
                        "sort_order": COMPETITION_ORDER.get(
                            match["competition_code"], 100
                        ),
                    },
                )

        if not matches:
            raise ProviderError(
                "Takip edilen takımlar için maç bulunamadı. " + " ".join(errors)
            )

        matches.sort(key=lambda item: item["kickoff"])
        return ProviderResult(
            matches=matches,
            competitions=sorted(
                competitions.values(), key=lambda item: item["sort_order"]
            ),
            complete=complete,
        )
