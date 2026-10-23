from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import repository
from ..utils import iso_utc, utc_now

COMPETITIONS: tuple[dict[str, Any], ...] = (
    {
        "code": "PL",
        "name": "Premier League",
        "country": "İngiltere",
        "sort_order": 10,
    },
    {"code": "PD", "name": "LaLiga", "country": "İspanya", "sort_order": 20},
    {"code": "BL1", "name": "Bundesliga", "country": "Almanya", "sort_order": 30},
    {"code": "SA", "name": "Serie A", "country": "İtalya", "sort_order": 40},
    {"code": "FL1", "name": "Ligue 1", "country": "Fransa", "sort_order": 50},
    {"code": "CL", "name": "UEFA Şampiyonlar Ligi", "country": "Avrupa", "sort_order": 60},
    {"code": "EL", "name": "UEFA Avrupa Ligi", "country": "Avrupa", "sort_order": 70},
    {"code": "DED", "name": "Eredivisie", "country": "Hollanda", "sort_order": 80},
    {"code": "PPL", "name": "Primeira Liga", "country": "Portekiz", "sort_order": 90},
    {"code": "TSL", "name": "Süper Lig", "country": "Türkiye", "sort_order": 100},
)

TEAMS: dict[str, dict[str, Any]] = {
    "ars": {"name": "Arsenal", "short": "Arsenal", "tla": "ARS", "crest": "https://crests.football-data.org/57.svg"},
    "che": {"name": "Chelsea", "short": "Chelsea", "tla": "CHE", "crest": "https://crests.football-data.org/61.svg"},
    "liv": {"name": "Liverpool", "short": "Liverpool", "tla": "LIV", "crest": "https://crests.football-data.org/64.svg"},
    "mci": {"name": "Manchester City", "short": "Man City", "tla": "MCI", "crest": "https://crests.football-data.org/65.svg"},
    "mun": {"name": "Manchester United", "short": "Man United", "tla": "MUN", "crest": "https://crests.football-data.org/66.svg"},
    "tot": {"name": "Tottenham", "short": "Tottenham", "tla": "TOT", "crest": "https://crests.football-data.org/73.svg"},
    "new": {"name": "Newcastle United", "short": "Newcastle", "tla": "NEW", "crest": "https://crests.football-data.org/67.svg"},
    "avl": {"name": "Aston Villa", "short": "Aston Villa", "tla": "AVL", "crest": "https://crests.football-data.org/58.svg"},
    "bha": {"name": "Brighton", "short": "Brighton", "tla": "BHA", "crest": "https://crests.football-data.org/397.svg"},
    "whu": {"name": "West Ham United", "short": "West Ham", "tla": "WHU", "crest": "https://crests.football-data.org/563.svg"},
    "rma": {"name": "Real Madrid", "short": "Real Madrid", "tla": "RMA", "crest": "https://crests.football-data.org/86.svg"},
    "bar": {"name": "Barcelona", "short": "Barcelona", "tla": "BAR", "crest": "https://crests.football-data.org/81.svg"},
    "atm": {"name": "Atlético Madrid", "short": "Atlético", "tla": "ATM", "crest": "https://crests.football-data.org/78.svg"},
    "sev": {"name": "Sevilla", "short": "Sevilla", "tla": "SEV", "crest": "https://crests.football-data.org/559.svg"},
    "val": {"name": "Valencia", "short": "Valencia", "tla": "VAL", "crest": "https://crests.football-data.org/95.svg"},
    "vil": {"name": "Villarreal", "short": "Villarreal", "tla": "VIL", "crest": "https://crests.football-data.org/94.svg"},
    "ath": {"name": "Athletic Bilbao", "short": "Athletic", "tla": "ATH", "crest": "https://crests.football-data.org/77.svg"},
    "rso": {"name": "Real Sociedad", "short": "Real Sociedad", "tla": "RSO", "crest": "https://crests.football-data.org/92.svg"},
    "bay": {"name": "Bayern München", "short": "Bayern", "tla": "FCB", "crest": "https://crests.football-data.org/5.svg"},
    "bvb": {"name": "Borussia Dortmund", "short": "Dortmund", "tla": "BVB", "crest": "https://crests.football-data.org/4.svg"},
    "rbl": {"name": "RB Leipzig", "short": "Leipzig", "tla": "RBL", "crest": "https://crests.football-data.org/721.svg"},
    "b04": {"name": "Bayer Leverkusen", "short": "Leverkusen", "tla": "B04", "crest": "https://crests.football-data.org/3.svg"},
    "sge": {"name": "Eintracht Frankfurt", "short": "Frankfurt", "tla": "SGE", "crest": "https://crests.football-data.org/19.svg"},
    "vfb": {"name": "VfB Stuttgart", "short": "Stuttgart", "tla": "VFB", "crest": "https://crests.football-data.org/10.svg"},
    "wob": {"name": "VfL Wolfsburg", "short": "Wolfsburg", "tla": "WOB", "crest": "https://crests.football-data.org/11.svg"},
    "scf": {"name": "SC Freiburg", "short": "Freiburg", "tla": "SCF", "crest": "https://crests.football-data.org/17.svg"},
    "int": {"name": "Inter", "short": "Inter", "tla": "INT", "crest": "https://crests.football-data.org/108.svg"},
    "acm": {"name": "Milan", "short": "Milan", "tla": "MIL", "crest": "https://crests.football-data.org/98.svg"},
    "juv": {"name": "Juventus", "short": "Juventus", "tla": "JUV", "crest": "https://crests.football-data.org/109.svg"},
    "nap": {"name": "Napoli", "short": "Napoli", "tla": "NAP", "crest": "https://crests.football-data.org/113.svg"},
    "rom": {"name": "Roma", "short": "Roma", "tla": "ROM", "crest": "https://crests.football-data.org/100.svg"},
    "laz": {"name": "Lazio", "short": "Lazio", "tla": "LAZ", "crest": "https://crests.football-data.org/110.svg"},
    "ata": {"name": "Atalanta", "short": "Atalanta", "tla": "ATA", "crest": "https://crests.football-data.org/102.svg"},
    "fio": {"name": "Fiorentina", "short": "Fiorentina", "tla": "FIO", "crest": "https://crests.football-data.org/99.svg"},
    "psg": {"name": "Paris Saint-Germain", "short": "PSG", "tla": "PSG", "crest": "https://crests.football-data.org/524.svg"},
    "mar": {"name": "Marseille", "short": "Marseille", "tla": "OM", "crest": "https://crests.football-data.org/516.svg"},
    "lyo": {"name": "Lyon", "short": "Lyon", "tla": "OL", "crest": "https://crests.football-data.org/523.svg"},
    "mon": {"name": "Monaco", "short": "Monaco", "tla": "ASM", "crest": "https://crests.football-data.org/548.svg"},
    "lil": {"name": "Lille", "short": "Lille", "tla": "LOSC", "crest": "https://crests.football-data.org/521.svg"},
    "nic": {"name": "Nice", "short": "Nice", "tla": "NIC", "crest": "https://crests.football-data.org/522.svg"},
    "ren": {"name": "Rennes", "short": "Rennes", "tla": "REN", "crest": "https://crests.football-data.org/529.svg"},
    "len": {"name": "Lens", "short": "Lens", "tla": "RCL", "crest": "https://crests.football-data.org/546.svg"},
    "aja": {"name": "Ajax", "short": "Ajax", "tla": "AJA", "crest": "https://crests.football-data.org/678.svg"},
    "psv": {"name": "PSV", "short": "PSV", "tla": "PSV", "crest": "https://crests.football-data.org/674.svg"},
    "fey": {"name": "Feyenoord", "short": "Feyenoord", "tla": "FEY", "crest": "https://crests.football-data.org/675.svg"},
    "az": {"name": "AZ Alkmaar", "short": "AZ", "tla": "AZ", "crest": "https://crests.football-data.org/682.svg"},
    "twt": {"name": "Twente", "short": "Twente", "tla": "TWE", "crest": "https://crests.football-data.org/666.svg"},
    "utr": {"name": "Utrecht", "short": "Utrecht", "tla": "UTR", "crest": "https://crests.football-data.org/676.svg"},
    "ben": {"name": "Benfica", "short": "Benfica", "tla": "SLB", "crest": "https://crests.football-data.org/1903.svg"},
    "por": {"name": "Porto", "short": "Porto", "tla": "POR", "crest": "https://crests.football-data.org/503.svg"},
    "spo": {"name": "Sporting CP", "short": "Sporting", "tla": "SCP", "crest": "https://crests.football-data.org/498.svg"},
    "bra": {"name": "Braga", "short": "Braga", "tla": "SCB", "crest": "https://crests.football-data.org/5613.svg"},
    "gal": {"name": "Galatasaray", "short": "Galatasaray", "tla": "GAL", "crest": "https://crests.football-data.org/610.svg"},
    "fen": {"name": "Fenerbahçe", "short": "Fenerbahçe", "tla": "FEN", "crest": "https://crests.football-data.org/612.svg"},
    "bes": {"name": "Beşiktaş", "short": "Beşiktaş", "tla": "BJK", "crest": "https://crests.football-data.org/611.svg"},
    "tra": {"name": "Trabzonspor", "short": "Trabzonspor", "tla": "TRA", "crest": "https://crests.football-data.org/614.svg"},
}

DEMO_PLAYERS = (
    ("Ogün", "#b8f34a"),
    ("Mert", "#5ce1e6"),
    ("Deniz", "#ffcf5a"),
    ("Ece", "#ff7a90"),
    ("Burak", "#a78bfa"),
    ("Selin", "#fb923c"),
)

# (day offset, local hour, minute, competition, home key, away key, status, home score, away score, minute)
FINISHED_FIXTURES = (
    (-8, 21, 0, "PL", "ars", "che", 2, 1),
    (-7, 22, 0, "PD", "rma", "sev", 3, 0),
    (-6, 19, 30, "BL1", "bay", "bvb", 1, 1),
    (-5, 21, 45, "SA", "int", "rom", 2, 0),
    (-4, 22, 0, "FL1", "psg", "lyo", 4, 1),
    (-3, 20, 0, "PL", "mci", "liv", 2, 2),
    (-2, 22, 0, "PD", "bar", "atm", 1, 0),
    (-1, 20, 0, "TSL", "gal", "fen", 2, 1),
    (-9, 20, 45, "SA", "juv", "nap", 0, 0),
    (-10, 21, 0, "DED", "aja", "psv", 1, 2),
    (-11, 22, 0, "PPL", "ben", "por", 2, 1),
    (-12, 22, 0, "CL", "bay", "rma", 2, 3),
)

UPCOMING_FIXTURES = (
    (1, 18, 0, "PL", "tot", "new"),
    (1, 21, 0, "FL1", "mar", "mon"),
    (2, 20, 0, "CL", "rma", "mci"),
    (2, 22, 0, "PD", "ath", "rso"),
    (3, 18, 30, "PL", "che", "mun"),
    (3, 21, 30, "BL1", "bvb", "bay"),
    (4, 20, 0, "EL", "rom", "b04"),
    (4, 22, 0, "TSL", "fen", "bes"),
    (5, 19, 0, "SA", "rom", "laz"),
    (6, 20, 30, "CL", "psg", "bay"),
    (7, 18, 0, "DED", "psv", "aja"),
)


def _local_kickoff(now: datetime, day_offset: int, hour: int, minute: int) -> str:
    local_now = now.astimezone(ZoneInfo("Europe/Istanbul"))
    target_date = local_now.date() + timedelta(days=day_offset)
    target = datetime.combine(
        target_date, time(hour=hour, minute=minute), tzinfo=ZoneInfo("Europe/Istanbul")
    )
    return iso_utc(target)


def _match_payload(
    *,
    index: int,
    kickoff: str,
    competition: str,
    home_key: str,
    away_key: str,
    status: str,
    home_score: int | None,
    away_score: int | None,
    minute: int | None = None,
) -> dict[str, Any]:
    home = TEAMS[home_key]
    away = TEAMS[away_key]
    return {
        "provider": "demo",
        "external_id": f"demo-{index}",
        "competition_code": competition,
        "season": 2026,
        "matchday": 8 + (index % 5),
        "stage": "REGULAR_SEASON",
        "kickoff": kickoff,
        "status": status,
        "minute": minute,
        "home": home,
        "away": away,
        "score": {"home": home_score, "away": away_score},
        "last_updated": iso_utc(utc_now()),
    }


def _build_matches(now: datetime) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    index = 0

    for day, hour, minute, comp, home, away, hs, as_ in FINISHED_FIXTURES:
        matches.append(
            _match_payload(
                index=index,
                kickoff=_local_kickoff(now, day, hour, minute),
                competition=comp,
                home_key=home,
                away_key=away,
                status="FINISHED",
                home_score=hs,
                away_score=as_,
            )
        )
        index += 1

    matches.append(
        _match_payload(
            index=index,
            kickoff=iso_utc(now - timedelta(minutes=62)),
            competition="SA",
            home_key="acm",
            away_key="juv",
            status="IN_PLAY",
            home_score=1,
            away_score=1,
            minute=62,
        )
    )
    index += 1
    matches.append(
        _match_payload(
            index=index,
            kickoff=iso_utc(now - timedelta(minutes=29)),
            competition="BL1",
            home_key="b04",
            away_key="rbl",
            status="IN_PLAY",
            home_score=0,
            away_score=1,
            minute=29,
        )
    )
    index += 1
    matches.append(
        _match_payload(
            index=index,
            kickoff=iso_utc(now + timedelta(minutes=95)),
            competition="DED",
            home_key="fey",
            away_key="az",
            status="TIMED",
            home_score=None,
            away_score=None,
        )
    )
    index += 1
    matches.append(
        _match_payload(
            index=index,
            kickoff=iso_utc(now + timedelta(minutes=190)),
            competition="PPL",
            home_key="spo",
            away_key="bra",
            status="TIMED",
            home_score=None,
            away_score=None,
        )
    )
    index += 1

    for day, hour, minute, comp, home, away in UPCOMING_FIXTURES:
        matches.append(
            _match_payload(
                index=index,
                kickoff=_local_kickoff(now, day, hour, minute),
                competition=comp,
                home_key=home,
                away_key=away,
                status="TIMED",
                home_score=None,
                away_score=None,
            )
        )
        index += 1

    return matches


# Deterministic prediction shapes. They are offsets from the actual score for
# completed games, and offsets from a plausible baseline for future games.
_PATTERNS = (
    (0, 0),
    (1, 0),
    (0, 1),
    (-1, 0),
    (1, 1),
    (-1, -1),
    (2, 0),
    (0, 2),
    (1, 2),
    (2, 1),
    (-2, 0),
    (0, -2),
)

_JOKER_MATCHES = {
    0: {2, 9, 18},
    1: {5, 20},
    2: {7, 16},
    3: {1, 14},
    4: {4, 21},
    5: {10, 15},
}


def _predicted_score(
    player_index: int, match_index: int, actual_home: int | None, actual_away: int | None
) -> tuple[int, int]:
    pattern = _PATTERNS[(player_index * 3 + match_index * 5) % len(_PATTERNS)]
    if actual_home is not None and actual_away is not None:
        base_home, base_away = actual_home, actual_away
    else:
        base_home = 1 + ((match_index * 7) % 3)
        base_away = (match_index * 3) % 2
    prediction_home = max(0, min(7, base_home + pattern[0]))
    prediction_away = max(0, min(7, base_away + pattern[1]))
    return prediction_home, prediction_away


def seed_demo(path: str | Path, force: bool = False) -> None:
    existing_demo = [
        match
        for match in repository.list_matches(path)
        if match["provider"] == "demo"
    ]
    if existing_demo and not force:
        return
    if force:
        repository.delete_demo_matches(path)

    for competition in COMPETITIONS:
        repository.upsert_competition(path, **competition)

    players = repository.list_players(path)
    players_by_name = {player["name"]: player for player in players}
    for name, color in DEMO_PLAYERS:
        if name not in players_by_name:
            players_by_name[name] = repository.create_player(path, name, color)
    players = sorted(players_by_name.values(), key=lambda item: item["id"])

    now = utc_now()
    matches = _build_matches(now)
    repository.upsert_matches(path, matches)

    match_rows = [
        match for match in repository.list_matches(path) if match["provider"] == "demo"
    ]
    match_rows.sort(key=lambda item: int(item["external_id"].split("-")[-1]))
    existing_predictions = {
        (prediction["player_id"], prediction["match_id"])
        for prediction in repository.list_predictions(
            path, [int(match["id"]) for match in match_rows]
        )
    }

    for player_index, player in enumerate(players[: len(DEMO_PLAYERS)]):
        for match_index, match in enumerate(match_rows):
            key = (int(player["id"]), int(match["id"]))
            if key in existing_predictions:
                continue
            home_goals, away_goals = _predicted_score(
                player_index,
                match_index,
                match["score"]["home"],
                match["score"]["away"],
            )
            if home_goals > away_goals:
                prediction_outcome = "H"
            elif home_goals < away_goals:
                prediction_outcome = "A"
            else:
                prediction_outcome = "D"
            repository.upsert_prediction(
                path,
                player_id=key[0],
                match_id=key[1],
                outcome=prediction_outcome,
                joker=match_index in _JOKER_MATCHES.get(player_index, set()),
            )
