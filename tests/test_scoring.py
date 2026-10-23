from __future__ import annotations

import unittest

from league.scoring import (
    DEFAULT_SCORING,
    ScoringConfig,
    outcome,
    score_outcome,
    score_prediction,
)


class OutcomeTests(unittest.TestCase):
    def test_outcome(self) -> None:
        self.assertEqual(outcome(2, 1), "H")
        self.assertEqual(outcome(0, 0), "D")
        self.assertEqual(outcome(1, 3), "A")


class OutcomePredictionTests(unittest.TestCase):
    def test_correct_winner_is_one_point(self) -> None:
        result = score_outcome("H", 2, 1, DEFAULT_SCORING)
        self.assertEqual(result["points"], 1)
        self.assertTrue(result["correct_outcome"])

    def test_correct_draw_is_one_point(self) -> None:
        result = score_outcome("D", 1, 1, DEFAULT_SCORING)
        self.assertEqual(result["points"], 1)

    def test_wrong_outcome_is_zero(self) -> None:
        result = score_outcome("A", 2, 1, DEFAULT_SCORING)
        self.assertEqual(result["points"], 0)
        self.assertFalse(result["correct_outcome"])

    def test_joker_doubles_correct_outcome(self) -> None:
        result = score_outcome("H", 2, 1, DEFAULT_SCORING, joker=True)
        self.assertEqual(result["points"], 2)


class ScorePredictionTests(unittest.TestCase):
    # score_prediction is kept for compatibility with the old score-based API.
    legacy = ScoringConfig(exact_score=5, correct_outcome=3, goal_difference_bonus=1)

    def test_exact_score(self) -> None:
        result = score_prediction(2, 1, 2, 1, self.legacy)
        self.assertEqual(result["points"], 5)
        self.assertTrue(result["exact"])

    def test_correct_outcome_only(self) -> None:
        # Predicted 2-0, actual 3-1: same winner, same goal difference.
        result = score_prediction(2, 0, 3, 1, self.legacy)
        self.assertFalse(result["exact"])
        self.assertTrue(result["correct_outcome"])
        self.assertEqual(result["points"], 4)
        self.assertEqual(result["base_points"], 4)

    def test_correct_outcome_with_different_margin(self) -> None:
        result = score_prediction(1, 0, 3, 1, self.legacy)
        self.assertTrue(result["correct_outcome"])
        self.assertFalse(result["correct_goal_difference"])
        self.assertEqual(result["points"], 3)

    def test_wrong_outcome_scores_zero(self) -> None:
        result = score_prediction(0, 1, 2, 0, self.legacy)
        self.assertEqual(result["points"], 0)
        self.assertFalse(result["correct_outcome"])

    def test_joker_multiplies_points(self) -> None:
        result = score_prediction(1, 1, 1, 1, self.legacy, joker=True)
        self.assertEqual(result["base_points"], 5)
        self.assertEqual(result["multiplier"], 2)
        self.assertEqual(result["points"], 10)

    def test_custom_config(self) -> None:
        config = ScoringConfig(
            exact_score=10,
            correct_outcome=2,
            goal_difference_bonus=0,
            joker_multiplier=3,
        )
        result = score_prediction(2, 0, 3, 1, config, joker=True)
        self.assertEqual(result["points"], 6)

    def test_from_mapping_clamps_and_falls_back(self) -> None:
        config = ScoringConfig.from_mapping(
            {
                "status": "unknown",
                "exact_score": "999",
                "correct_outcome": "abc",
                "goal_difference_bonus": -5,
                "joker_multiplier": 2,
            }
        )
        self.assertEqual(config.status, "provisional")
        self.assertEqual(config.exact_score, 100)
        self.assertEqual(config.correct_outcome, DEFAULT_SCORING.correct_outcome)
        self.assertEqual(config.goal_difference_bonus, 0)


if __name__ == "__main__":
    unittest.main()
