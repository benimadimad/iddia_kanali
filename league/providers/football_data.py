from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Iterator

from ..config import Config
from ..targets import COMPETITION_LABELS, COMPETITION_ORDER
from ..utils import utc_now
from . import ProviderError, ProviderResult

API_URL = "https://api.football-data.org/v4/matches"
# The free tier rejects date ranges longer than 10 days, so requests are split.
MAX_WINDOW_DAYS = 10

LIVE_STATUSES = {
    "IN_PLAY",
    "PAUSED",
    "EXTRA_TIME",
    "PENALTY_SHOOTOUT",
}


class FootballDataProvider:
    def __init__(self, config: Config) -> None:
        self.config = config

    def fetch(self, date_from: str, date_to: str) -> ProviderResult:
        if not self.config.football_data_token:
            raise ProviderError("FOOTBALL_DATA_TOKEN tanımlı değil.")

        windows = list(self._date_windows(date_from, date_to))
        if not windows:
            raise ProviderError("Geçersiz tarih aralığı.")

        competition_map: dict[str, dict[str, Any]] = {}
        matches_by_id: dict[str, dict[str, Any]] = {}
        for index, (start, end) in enumerate(windows):
            if index:
                # Stay well inside the free tier limit (10 requests/minute).
                time.sleep(1)
            payload = self._request(start.isoformat(), end.isoformat())
            matches = payload.get("matches")
            if not isinstance(matches, list):
                raise ProviderError("Veri kaynağı beklenmeyen bir yanıt döndürdü.")

            for item in matches:
                parsed = self._normalize_match(item)
                if not parsed:
                    continue
                matches_by_id[parsed["external_id"]] = parsed
                competition = item.get("competition") or {}
                code = parsed["competition_code"]
                if code and code not in competition_map:
                    competition_map[code] = {
                        "code": code,
                        "name": competition.get("name") or code,
                        "country": (item.get("area") or {}).get("name"),
                        "emblem": competition.get("emblem"),
                        "sort_order": self._competition_order(code),
                    }

        normalized = sorted(
            matches_by_id.values(), key=lambda match: match["kickoff"]
        )
        return ProviderResult(
            matches=normalized,
            competitions=list(competition_map.values()),
        )

    def fetch_season(self, code: str) -> ProviderResult:
        """Fetch every match of the current season for one competition."""
        if not self.config.football_data_token:
            raise ProviderError("FOOTBALL_DATA_TOKEN tanımlı değil.")

        payload = self._request_url(
            f"https://api.football-data.org/v4/competitions/{code}/matches"
            f"?season={self.config.season_year}"
        )
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ProviderError("Veri kaynağı beklenmeyen bir yanıt döndürdü.")

        normalized: list[dict[str, Any]] = []
        competition_meta: dict[str, Any] | None = None
        for item in matches:
            parsed = self._normalize_match(item)
            if not parsed:
                continue
            normalized.append(parsed)
            if competition_meta is None:
                competition = item.get("competition") or {}
                competition_meta = {
                    "code": code,
                    "name": COMPETITION_LABELS.get(code, competition.get("name") or code),
                    "country": "Avrupa",
                    "emblem": competition.get("emblem"),
                    "sort_order": COMPETITION_ORDER.get(code, 100),
                }

        normalized.sort(key=lambda match: match["kickoff"])
        return ProviderResult(
            matches=normalized,
            competitions=[competition_meta] if competition_meta else [],
        )

    @staticmethod
    def _date_windows(date_from: str, date_to: str) -> Iterator[tuple[date, date]]:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        if end < start:
            return
        cursor = start
        while cursor <= end:
            window_end = min(end, cursor + timedelta(days=MAX_WINDOW_DAYS - 1))
            yield cursor, window_end
            cursor = window_end + timedelta(days=1)

    def _request(self, date_from: str, date_to: str) -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {
                "competitions": ",".join(self.config.competitions),
                "dateFrom": date_from,
                "dateTo": date_to,
            }
        )
        return self._request_url(f"{API_URL}?{params}")

    def _request_url(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "X-Auth-Token": self.config.football_data_token,
                "Accept": "application/json",
                "User-Agent": "TahminLigi/1.0",
            },
        )

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429 and attempt < 2:
                    retry_after = exc.headers.get("X-RequestCounter-Reset", "8")
                    try:
                        wait = min(20, max(2, int(retry_after)))
                    except ValueError:
                        wait = 8
                    time.sleep(wait)
                    continue
                if exc.code in {401, 403}:
                    raise ProviderError(
                        "football-data.org anahtarı geçersiz veya bu liglere erişim yok."
                    ) from exc
                detail = ""
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    detail = body.get("message") or ""
                except Exception:
                    pass
                message = f"Veri kaynağı HTTP {exc.code} hatası döndürdü."
                if detail:
                    message = f"{message} ({detail})"
                raise ProviderError(message) from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ProviderError(
                    "Veri kaynağına ulaşılamadı. İnternet bağlantısını kontrol edin."
                ) from exc

        raise ProviderError(f"Veri kaynağı yanıt vermedi: {last_error}")

    def _competition_order(self, code: str) -> int:
        try:
            return (self.config.competitions.index(code) + 1) * 10
        except ValueError:
            return 999

    @staticmethod
    def _normalize_match(item: dict[str, Any]) -> dict[str, Any] | None:
        home_team = item.get("homeTeam") or {}
        away_team = item.get("awayTeam") or {}
        competition = item.get("competition") or {}
        if not home_team.get("name") or not away_team.get("name"):
            return None

        score = item.get("score") or {}
        full_time = score.get("fullTime") or {}
        status = str(item.get("status") or "SCHEDULED").upper()
        home_score = full_time.get("home")
        away_score = full_time.get("away")

        # Some competitions expose the live score only in the regular time block.
        if status in LIVE_STATUSES and home_score is None:
            regular = score.get("regularTime") or {}
            home_score = regular.get("home")
            away_score = regular.get("away")

        if status == "AWARDED" and home_score is None and away_score is None:
            home_score = 0
            away_score = 0

        return {
            "provider": "football-data",
            "external_id": str(item.get("id")),
            "competition_code": competition.get("code") or "",
            "season": (item.get("season") or {}).get("startDate", "")[:4] or None,
            "matchday": item.get("matchday"),
            "stage": item.get("stage"),
            "kickoff": item.get("utcDate") or f"{date.today().isoformat()}T00:00:00Z",
            "status": status,
            "minute": item.get("minute"),
            "home": {
                "name": home_team.get("name"),
                "short": home_team.get("shortName") or home_team.get("name"),
                "tla": home_team.get("tla"),
                "crest": home_team.get("crest"),
            },
            "away": {
                "name": away_team.get("name"),
                "short": away_team.get("shortName") or away_team.get("name"),
                "tla": away_team.get("tla"),
                "crest": away_team.get("crest"),
            },
            "score": {"home": home_score, "away": away_score},
            "last_updated": item.get("lastUpdated") or utc_now().isoformat(),
        }
