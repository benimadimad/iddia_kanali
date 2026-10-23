from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..config import Config
from ..targets import COMPETITION_LABELS, COMPETITION_ORDER
from ..utils import utc_now
from . import ProviderError, ProviderResult

API_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"

# ESPN competition slugs for the three UEFA club competitions we follow.
COMPETITION_SLUGS = {
    "CL": "uefa.champions",
    "EL": "uefa.europa",
    "UECL": "uefa.europa.conf",
}

LIVE_STATUS_NAMES = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD"}
INACTIVE_STATUS_NAMES = {
    "STATUS_POSTPONED": "POSTPONED",
    "STATUS_CANCELED": "CANCELLED",
    "STATUS_CANCELLED": "CANCELLED",
    "STATUS_SUSPENDED": "SUSPENDED",
}


class EspnProvider:
    """Fixtures and scores from ESPN's public soccer API.

    football-data.org's free tier does not expose the Europa League or the
    Conference League, so those competitions are read from ESPN. Only the
    tracked clubs are kept later by the combined provider.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

    def fetch(self, codes: tuple[str, ...] | list[str]) -> ProviderResult:
        matches: list[dict[str, Any]] = []
        competitions: list[dict[str, Any]] = []
        seen: set[str] = set()

        for code in codes:
            slug = COMPETITION_SLUGS.get(code)
            if not slug:
                continue
            competition_added = False
            for year in (self.config.season_year, self.config.season_year + 1):
                payload = self._request(slug, year)
                for event in payload.get("events", []):
                    parsed = self._normalize_event(
                        event, code, slug, self.config.season_year
                    )
                    if not parsed or parsed["external_id"] in seen:
                        continue
                    seen.add(parsed["external_id"])
                    matches.append(parsed)
                    if not competition_added:
                        competitions.append(self._competition(code, payload))
                        competition_added = True

        matches.sort(key=lambda item: item["kickoff"])
        return ProviderResult(matches=matches, competitions=competitions)

    def _request(self, slug: str, year: int) -> dict[str, Any]:
        url = API_URL.format(slug=slug) + f"?dates={year}&limit=500"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "TahminLigi/1.0",
            },
        )
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise ProviderError(
                    f"ESPN veri kaynağı HTTP {exc.code} hatası döndürdü."
                ) from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ProviderError(
                    "ESPN veri kaynağına ulaşılamadı. İnternet bağlantısını kontrol edin."
                ) from exc
        raise ProviderError(f"ESPN veri kaynağı yanıt vermedi: {last_error}")

    def _competition(self, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        logo = None
        leagues = payload.get("leagues") or []
        if leagues:
            logos = leagues[0].get("logos") or []
            if logos:
                logo = logos[0].get("href")
        return {
            "code": code,
            "name": COMPETITION_LABELS.get(code, code),
            "country": "Avrupa",
            "emblem": logo,
            "sort_order": COMPETITION_ORDER.get(code, 100),
        }

    @staticmethod
    def _normalize_event(
        event: dict[str, Any], code: str, slug: str, season_year: int
    ) -> dict[str, Any] | None:
        season = event.get("season") or {}
        if season.get("year") != season_year:
            return None

        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            return None
        home_team = home.get("team") or {}
        away_team = away.get("team") or {}

        status = competition.get("status") or {}
        status_type = status.get("type") or {}
        state = str(status_type.get("state") or "pre").lower()
        status_name = str(status_type.get("name") or "")

        status_value = "SCHEDULED"
        if status_name in INACTIVE_STATUS_NAMES:
            status_value = INACTIVE_STATUS_NAMES[status_name]
        elif state == "post":
            status_value = "FINISHED"
        elif state == "in":
            if "HALFTIME" in status_name or "END_PERIOD" in status_name:
                status_value = "PAUSED"
            else:
                status_value = "IN_PLAY"
        elif competition.get("timeValid", True):
            status_value = "TIMED"

        minute = None
        if status_value in {"IN_PLAY", "PAUSED"}:
            clock = str(status.get("displayClock") or "")
            digits = "".join(ch for ch in clock.split("'")[0] if ch.isdigit())
            if digits:
                minute = min(130, int(digits))

        home_score = _score(home)
        away_score = _score(away)
        if status_value in {"SCHEDULED", "TIMED", "POSTPONED", "CANCELLED", "SUSPENDED"}:
            home_score = None
            away_score = None

        return {
            "provider": "espn",
            "external_id": str(event.get("id")),
            "competition_code": code,
            "season": season_year,
            "matchday": (event.get("week") or {}).get("number"),
            "stage": str(season.get("slug") or "").upper() or None,
            "kickoff": event.get("date"),
            "status": status_value,
            "minute": minute,
            "home": {
                "name": home_team.get("displayName"),
                "short": home_team.get("shortDisplayName") or home_team.get("displayName"),
                "tla": home_team.get("abbreviation"),
                "crest": home_team.get("logo"),
            },
            "away": {
                "name": away_team.get("displayName"),
                "short": away_team.get("shortDisplayName") or away_team.get("displayName"),
                "tla": away_team.get("abbreviation"),
                "crest": away_team.get("logo"),
            },
            "score": {
                "home": home_score,
                "away": away_score,
            },
            "last_updated": utc_now().isoformat(),
        }


def _score(competitor: dict[str, Any]) -> int | None:
    raw = competitor.get("score")
    if isinstance(raw, dict):
        raw = raw.get("displayValue", raw.get("value"))
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
