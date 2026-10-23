from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import repository
from .config import Config
from .scoring import ScoringConfig, score_outcome
from .targets import canonical_team_name
from .utils import initials, iso_utc, local_day, parse_iso, utc_now

LIVE_STATUSES = {
    "IN_PLAY",
    "PAUSED",
    "EXTRA_TIME",
    "PENALTY_SHOOTOUT",
}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
INACTIVE_STATUSES = {"POSTPONED", "CANCELLED", "SUSPENDED"}

TEAM_CODES = {
    "Fenerbahçe": "FB",
    "Galatasaray": "GS",
    "Beşiktaş": "BJK",
    "Trabzonspor": "TS",
}


def _status_group(status: str) -> str:
    if status in FINISHED_STATUSES:
        return "finished"
    if status in LIVE_STATUSES:
        return "live"
    if status in INACTIVE_STATUSES:
        return "inactive"
    return "upcoming"


def _is_started(match: dict[str, Any], now: datetime) -> bool:
    kickoff = parse_iso(match["kickoff"])
    return bool(
        match["status"] in LIVE_STATUSES
        or match["status"] in FINISHED_STATUSES
        or (kickoff and kickoff <= now)
    )


def _is_revealed(match: dict[str, Any], now: datetime) -> bool:
    if match["status"] in INACTIVE_STATUSES:
        return False
    return _is_started(match, now)


def _is_finished(match: dict[str, Any]) -> bool:
    return (
        match["status"] in FINISHED_STATUSES
        and match["score"]["home"] is not None
        and match["score"]["away"] is not None
    )


def _player_public(player: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": player["id"],
        "name": player["name"],
        "slug": player["slug"],
        "color": player["color"],
        "bonus_points": int(player.get("bonus_points") or 0),
        "initials": initials(player["name"]),
    }


class LeagueService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.path: Path = config.database_path

    def ensure_ready(self) -> None:
        repository.init_db(self.path)
        if self.config.is_demo:
            from .providers.demo import seed_demo

            seed_demo(self.path)
            state = repository.get_sync_state(self.path)
            if not state.get("last_success_at"):
                now = iso_utc(utc_now())
                repository.update_sync_state(
                    self.path,
                    provider="demo",
                    attempted_at=now,
                    success_at=now,
                    matches_seen=len(repository.list_matches(self.path)),
                    changed=0,
                )
        else:
            # Make the public page usable before the first API round-trip.
            self._ensure_competitions()

    def _ensure_competitions(self) -> None:
        if repository.list_competitions(self.path):
            return
        for order, code in enumerate(self.config.competitions, start=1):
            repository.upsert_competition(
                self.path,
                code=code,
                name=code,
                sort_order=order * 10,
            )

    def public_payload(self) -> dict[str, Any]:
        now = utc_now()
        players = repository.list_players(self.path, active_only=True)
        players_public = [_player_public(player) for player in players]
        players_by_id = {player["id"]: player for player in players_public}

        matches = repository.list_matches(self.path)
        predictions = repository.list_predictions(self.path)
        connections: dict[tuple[int, int], dict[str, Any]] = {
            (int(item["match_id"]), int(item["player_id"])): item
            for item in predictions
        }

        scoring = repository.get_scoring(self.path)
        competitions = {
            competition["code"]: competition
            for competition in repository.list_competitions(self.path)
        }

        forms = self._build_team_forms(matches)
        public_matches: list[dict[str, Any]] = []
        for match in matches:
            item = self._decorate_match(match, competitions, forms)
            item_predictions = [
                prediction
                for (match_id, _), prediction in connections.items()
                if match_id == match["id"]
            ]
            item["prediction_count"] = len(item_predictions)

            revealed: list[dict[str, Any]] = []
            for prediction in item_predictions:
                player = players_by_id.get(prediction["player_id"])
                if not player:
                    continue
                entry: dict[str, Any] = {
                    "player_id": player["id"],
                    "name": player["name"],
                    "initials": player["initials"],
                    "color": player["color"],
                    "outcome": prediction["outcome"],
                    "label": self._prediction_label(match, prediction["outcome"]),
                    "joker": bool(prediction["joker"]),
                    "points": None,
                    "exact": None,
                    "correct_outcome": None,
                    "multiplier": scoring.joker_multiplier
                    if prediction["joker"]
                    else 1,
                }
                if _is_finished(match):
                    result = score_outcome(
                        prediction["outcome"],
                        int(match["score"]["home"]),
                        int(match["score"]["away"]),
                        scoring,
                        bool(prediction["joker"]),
                    )
                    entry.update(result)
                revealed.append(entry)
            revealed.sort(
                key=lambda entry: (
                    -(entry["points"] or -1),
                    entry["name"].casefold(),
                )
            )
            item["predictions"] = revealed
            item["predictions_visible"] = True

            public_matches.append(item)

        standings = self._standings(
            public_matches,
            players_public,
            scoring,
        )
        finished = [match for match in public_matches if match["is_finished"]]
        live = [match for match in public_matches if match["is_live"]]
        upcoming = [
            match
            for match in public_matches
            if match["status_group"] == "upcoming" and not match["is_started"]
        ]
        next_match = min(
            (match for match in upcoming), key=lambda item: item["kickoff"], default=None
        )
        last_finished = max(
            finished, key=lambda item: item["kickoff"], default=None
        )

        sync_state = repository.get_sync_state(self.path)
        return {
            "meta": {
                "league_name": self.config.league_name,
                "generated_at": iso_utc(now),
                "timezone": self.config.timezone,
                "today": local_day(now, self.config.timezone),
                "demo": self.config.is_demo,
                "source": self.config.source_label,
                "source_url": "https://www.football-data.org/"
                if not self.config.is_demo
                else None,
                "scoring": scoring.to_dict(),
                "sync": {
                    "provider": sync_state.get("provider"),
                    "last_attempt_at": sync_state.get("last_attempt_at"),
                    "last_success_at": sync_state.get("last_success_at"),
                    "error": sync_state.get("last_error"),
                    "matches_seen": sync_state.get("matches_seen", 0),
                },
                "counts": {
                    "players": len(players_public),
                    "matches": len(public_matches),
                    "finished": len(finished),
                    "live": len(live),
                    "upcoming": len(upcoming),
                },
                "leader": standings[0]["name"] if standings else None,
                "last_finished": self._match_stub(last_finished),
                "next_match": self._match_stub(next_match),
            },
            "players": players_public,
            "competitions": list(competitions.values()),
            "matches": public_matches,
            "standings": standings,
        }

    def admin_payload(self) -> dict[str, Any]:
        now = utc_now()
        players = repository.list_players(self.path)
        matches = repository.list_matches(self.path)
        predictions = repository.list_predictions(self.path)
        competitions = repository.list_competitions(self.path)
        scoring = repository.get_scoring(self.path)
        sync_state = repository.get_sync_state(self.path)

        competition_map = {item["code"]: item for item in competitions}
        forms = self._build_team_forms(matches)
        editor_matches: list[dict[str, Any]] = []
        for match in matches:
            item = self._decorate_match(match, competition_map, forms)
            item["locked"] = _is_started(match, now) or match["status"] in INACTIVE_STATUSES
            editor_matches.append(item)

        pred_map: dict[str, dict[str, Any]] = {}
        for prediction in predictions:
            key = f"{prediction['player_id']}:{prediction['match_id']}"
            pred_map[key] = {
                "player_id": prediction["player_id"],
                "match_id": prediction["match_id"],
                "outcome": prediction["outcome"],
                "joker": bool(prediction["joker"]),
            }

        return {
            "meta": {
                "demo": self.config.is_demo,
                "generated_at": iso_utc(now),
                "timezone": self.config.timezone,
                "scoring": scoring.to_dict(),
                "sync": {
                    "provider": sync_state.get("provider"),
                    "last_attempt_at": sync_state.get("last_attempt_at"),
                    "last_success_at": sync_state.get("last_success_at"),
                    "last_error": sync_state.get("last_error"),
                },
                "counts": {
                    "players": len(players),
                    "matches": len(matches),
                    "predictions": len(predictions),
                },
            },
            "players": players,
            "competitions": competitions,
            "matches": editor_matches,
            "predictions": pred_map,
        }

    def _decorate_match(
        self,
        match: dict[str, Any],
        competitions: dict[str, dict[str, Any]],
        forms: dict[str, list[str]],
    ) -> dict[str, Any]:
        item = {
            "id": match["id"],
            "competition_code": match["competition_code"],
            "competition": competitions.get(
                match["competition_code"],
                {
                    "code": match["competition_code"],
                    "name": match["competition_code"],
                    "country": None,
                    "emblem": None,
                },
            ),
            "kickoff": match["kickoff"],
            "status": match["status"],
            "status_group": _status_group(match["status"]),
            "minute": match["minute"],
            "matchday": match["matchday"],
            "stage": match["stage"],
            "home": {
                **match["home"],
                "form": forms.get(match["home"]["name"], [])[-5:],
            },
            "away": {
                **match["away"],
                "form": forms.get(match["away"]["name"], [])[-5:],
            },
            "score": match["score"],
            "is_live": match["status"] in LIVE_STATUSES,
            "is_finished": _is_finished(match),
            "is_started": _is_started(match, utc_now()),
            "last_updated": match["last_updated"],
        }
        return item

    @staticmethod
    def _prediction_label(match: dict[str, Any], predicted: str) -> str:
        predicted = (predicted or "").upper()
        if predicted == "D":
            return "Beraberlik"
        side = "home" if predicted == "H" else "away"
        team = match[side]
        name = team.get("short") or team.get("name") or ""
        return f"{name} yener"

    @staticmethod
    def _match_stub(match: dict[str, Any] | None) -> dict[str, Any] | None:
        if not match:
            return None
        return {
            "id": match["id"],
            "kickoff": match["kickoff"],
            "home": match["home"]["short"],
            "away": match["away"]["short"],
            "score": match["score"],
            "status": match["status"],
        }

    def _build_team_forms(
        self, matches: Iterable[dict[str, Any]]
    ) -> dict[str, list[str]]:
        forms: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            if not _is_finished(match):
                continue
            home_score = int(match["score"]["home"])
            away_score = int(match["score"]["away"])
            if home_score > away_score:
                forms[match["home"]["name"]].append("G")
                forms[match["away"]["name"]].append("M")
            elif home_score < away_score:
                forms[match["home"]["name"]].append("M")
                forms[match["away"]["name"]].append("G")
            else:
                forms[match["home"]["name"]].append("B")
                forms[match["away"]["name"]].append("B")
        return dict(forms)

    def _standings(
        self,
        matches: list[dict[str, Any]],
        players: list[dict[str, Any]],
        scoring: ScoringConfig,
    ) -> list[dict[str, Any]]:
        finished = sorted(
            (match for match in matches if match["is_finished"]),
            key=lambda item: item["kickoff"],
        )
        rows: list[dict[str, Any]] = []
        for player in players:
            total = int(player.get("bonus_points") or 0)
            played = 0
            missed = 0
            exact = 0
            outcomes = 0
            joker_used = 0
            team_correct = {code: 0 for code in TEAM_CODES.values()}
            form: list[int] = []
            last_points: int | None = None

            for match in finished:
                prediction = next(
                    (
                        item
                        for item in match["predictions"]
                        if item["player_id"] == player["id"]
                    ),
                    None,
                )
                if not prediction:
                    # Only the matches a player actually predicted make up their form.
                    missed += 1
                    continue
                points = int(prediction["points"] or 0)
                total += points
                played += 1
                exact += 1 if prediction["exact"] else 0
                outcomes += 1 if prediction["correct_outcome"] else 0
                joker_used += 1 if prediction["joker"] else 0
                if prediction["correct_outcome"]:
                    for side in ("home", "away"):
                        tracked = canonical_team_name(match[side]["name"])
                        if tracked:
                            team_correct[TEAM_CODES[tracked]] += 1
                form.append(points)
                last_points = points

            rows.append(
                {
                    **player,
                    "points": total,
                    "played": played,
                    "missed": missed,
                    "exact": exact,
                    "correct_outcomes": outcomes,
                    "joker_used": joker_used,
                    "team_correct": team_correct,
                    "form": form[-5:],
                    "last_points": last_points,
                    "accuracy": round((outcomes / played) * 100) if played else 0,
                }
            )

        rows.sort(
            key=lambda row: (
                -row["points"],
                -row["exact"],
                -row["correct_outcomes"],
                row["name"].casefold(),
            )
        )
        leader_points = rows[0]["points"] if rows else 0
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
            row["behind"] = leader_points - row["points"]
        return rows
