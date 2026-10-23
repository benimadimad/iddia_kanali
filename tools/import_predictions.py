"""Import outcome predictions from a JSON file.

Usage:
    py tools/import_predictions.py data/predictions_galatasaray.json

JSON shape::

    {
      "team": "Galatasaray",
      "competition": "CL",
      "predictions": {
        "BATU": {"Barcelona": "OPP", "PSG": "DRAW", "Lille": "GS"},
        ...
      }
    }

Every value is one of:
  * "GS"   -> the followed team wins
  * "OPP"  -> the opponent wins
  * "DRAW" -> draw
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from league import repository  # noqa: E402
from league.config import Config  # noqa: E402
from league.targets import normalize_name  # noqa: E402

OPPONENT_ALIASES = {
    "barcelona": ("barcelona",),
    "psg": ("paris", "psg"),
    "aston villa": ("aston villa",),
    "sporting": ("sporting",),
    "feyenoord": ("feyenoord",),
    "lille": ("lille",),
    "stuttgart": ("stuttgart",),
    "aek": ("aek",),
    "roma": ("roma",),
    "liverpool": ("liverpool",),
    "atletico": ("atleti", "atletico", "atletico madrid"),
    "villarreal": ("villarreal", "villareal"),
    "shakhtar": ("shakhtar", "shaktar"),
    "slavia": ("slavia",),
    "lask": ("lask",),
    "marseille": ("marseille", "marsilya"),
    "hoffenheim": ("hoffenheim",),
    "crystal palace": ("crystal palace",),
    "kups": ("kups",),
    "hearts": ("hearts", "heart", "midlothian"),
    "midtjylland": ("midtjylland",),
    "freiburg": ("freiburg",),
    "celtic": ("celtic",),
    "hapoel": ("hapoel",),
    "leverkusen": ("leverkusen", "bayer", "bayern leverkusen", "bayern"),
    "union": ("union", "gilloise", "usg"),
    "omonia": ("omonia",),
    "red star": ("red star", "crvena", "zvezda", "kizilyildiz", "kizil yildiz"),
    "kizil yildiz": ("kizil",),
    "jablonec": ("jablonec",),
    "cska": ("cska",),
    "fiorentina": ("fiorentina",),
    "braga": ("braga",),
    "ferencvaros": ("ferencvaros",),
}

VALUE_TO_SIDE = {"GS": "team", "OPP": "opponent", "DRAW": "draw", "D": "draw"}


def load_config() -> Config:
    return Config()


def opponent_aliases(opponent: str) -> tuple[str, ...]:
    """Resolve free-text opponent names like "Marsilya", "USG" or "Bayern Leverkusen"."""
    key = normalize_name(opponent)
    direct = OPPONENT_ALIASES.get(key)
    if direct:
        return direct
    for alias_key, aliases in OPPONENT_ALIASES.items():
        if (
            alias_key in key
            or key in alias_key
            or any(alias in key or key in alias for alias in aliases)
        ):
            return aliases
    return (key,)


def find_match(matches, team: str, opponent: str, used: set[int]):
    team_key = normalize_name(team)
    aliases = opponent_aliases(opponent)
    candidates = []
    for match in matches:
        if int(match["id"]) in used:
            continue
        home = normalize_name(match["home"]["name"])
        away = normalize_name(match["away"]["name"])
        if team_key not in home and team_key not in away:
            continue
        other = away if team_key in home else home
        if any(alias in other for alias in aliases):
            candidates.append(match)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item["kickoff"])
    return candidates[0]


def side_to_outcome(match, team: str, value: str) -> str:
    kind = VALUE_TO_SIDE[value]
    if kind == "draw":
        return "D"
    team_key = normalize_name(team)
    team_is_home = team_key in normalize_name(match["home"]["name"])
    team_side = "H" if team_is_home else "A"
    if kind == "team":
        return team_side
    return "A" if team_side == "H" else "H"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    team = payload["team"]
    predictions = payload["predictions"]

    config = load_config()
    repository.configure_from_config(config)
    repository.init_db(config.database_path)
    matches = repository.list_matches(config.database_path)
    players = {normalize_name(player["name"]): player for player in repository.list_players(config.database_path)}

    saved = 0
    for player_name, rows in predictions.items():
        key = normalize_name(player_name)
        player = players.get(key)
        if not player:
            # tolerate "anil abi" vs "anıl abi" style keys
            for candidate_key, candidate in players.items():
                if candidate_key.startswith(key) or key.startswith(candidate_key):
                    player = candidate
                    break
        if not player:
            print(f"! oyuncu bulunamadı: {player_name}")
            continue

        used: set[int] = set()
        for opponent, value in rows.items():
            value = value.upper()
            if value not in VALUE_TO_SIDE:
                print(f"! geçersiz değer: {player_name} / {opponent} = {value}")
                continue
            match = find_match(matches, team, opponent, used)
            if not match:
                print(f"! maç bulunamadı: {team} - {opponent}")
                continue
            used.add(int(match["id"]))
            outcome = side_to_outcome(match, team, value)
            repository.upsert_prediction(
                config.database_path,
                player_id=int(player["id"]),
                match_id=int(match["id"]),
                outcome=outcome,
                joker=False,
            )
            saved += 1
            print(
                f"{player['name']:<12} {opponent:<14} {value:<5} -> "
                f"{match['home']['short']} vs {match['away']['short']} ({outcome})"
            )

    print(f"\n{saved} tahmin kaydedildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
