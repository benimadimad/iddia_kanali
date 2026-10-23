from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ScoringConfig:
    """The rule set is intentionally data-driven: it is expected to change."""

    status: str = "final"
    label: str = "Doğru sonuç 1 puan"
    exact_score: int = 0
    correct_outcome: int = 1
    goal_difference_bonus: int = 0
    joker_multiplier: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Any) -> "ScoringConfig":
        if not isinstance(value, dict):
            return cls()
        defaults = cls()
        cleaned: dict[str, Any] = {}
        for key in ("status", "label"):
            raw = value.get(key, getattr(defaults, key))
            cleaned[key] = str(raw)[:80]
        for key in (
            "exact_score",
            "correct_outcome",
            "goal_difference_bonus",
            "joker_multiplier",
        ):
            try:
                number = int(value.get(key, getattr(defaults, key)))
            except (TypeError, ValueError):
                number = getattr(defaults, key)
            cleaned[key] = max(0, min(100, number))
        if cleaned["status"] not in {"provisional", "final"}:
            cleaned["status"] = "provisional"
        return cls(**cleaned)


DEFAULT_SCORING = ScoringConfig()


def outcome(home: int, away: int) -> str:
    if home > away:
        return "H"
    if home < away:
        return "A"
    return "D"


OUTCOME_LABELS = {"H": "Ev sahibi kazanır", "D": "Beraberlik", "A": "Deplasman kazanır"}


def score_outcome(
    prediction_outcome: str,
    actual_home: int,
    actual_away: int,
    config: ScoringConfig,
    joker: bool = False,
) -> dict[str, Any]:
    """Score a win/draw/loss prediction against the real result."""
    predicted = (prediction_outcome or "").upper()
    correct = predicted == outcome(actual_home, actual_away)
    base = config.correct_outcome if correct else 0
    multiplier = config.joker_multiplier if joker else 1

    return {
        "points": base * multiplier,
        "base_points": base,
        "multiplier": multiplier,
        "exact": False,
        "correct_outcome": correct,
        "correct_goal_difference": False,
    }


def score_prediction(
    prediction_home: int,
    prediction_away: int,
    actual_home: int,
    actual_away: int,
    config: ScoringConfig,
    joker: bool = False,
) -> dict[str, Any]:
    exact = prediction_home == actual_home and prediction_away == actual_away
    correct_outcome = outcome(prediction_home, prediction_away) == outcome(
        actual_home, actual_away
    )
    correct_goal_difference = (
        prediction_home - prediction_away == actual_home - actual_away
    )

    if exact:
        base = config.exact_score
    else:
        base = config.correct_outcome if correct_outcome else 0
        if correct_goal_difference and correct_outcome:
            base += config.goal_difference_bonus

    multiplier = config.joker_multiplier if joker else 1
    points = base * multiplier

    return {
        "points": points,
        "base_points": base,
        "multiplier": multiplier,
        "exact": exact,
        "correct_outcome": correct_outcome,
        "correct_goal_difference": correct_goal_difference,
    }
