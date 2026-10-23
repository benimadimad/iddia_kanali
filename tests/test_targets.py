from __future__ import annotations

import unittest
from datetime import datetime, timezone

from league.config import Config
from league.providers.espn import EspnProvider
from league.targets import (
    COMPETITION_LABELS,
    is_tracked_match,
    is_tracked_team,
    normalize_name,
)


class TrackedTeamTests(unittest.TestCase):
    def test_known_clubs_are_matched(self) -> None:
        for name in (
            "Fenerbahçe SK",
            "Fenerbahce",
            "Galatasaray SK",
            "Beşiktaş",
            "Besiktas",
            "Trabzonspor",
        ):
            self.assertTrue(is_tracked_team(name), name)

    def test_other_clubs_are_ignored(self) -> None:
        for name in ("Arsenal FC", "FC Barcelona", "Trabzon Karadenizspor"):
            self.assertFalse(is_tracked_team(name), name)

    def test_match_is_tracked_when_one_side_is_tracked(self) -> None:
        self.assertTrue(is_tracked_match("Fenerbahçe SK", "Liverpool FC"))
        self.assertTrue(is_tracked_match("Celtic", "Beşiktaş"))
        self.assertFalse(is_tracked_match("Celtic", "Bayer Leverkusen"))

    def test_normalize_name_removes_turkish_characters(self) -> None:
        self.assertEqual(normalize_name("  Beşiktaş  "), "besiktas")
        self.assertEqual(normalize_name("FENERBAHÇE"), "fenerbahce")


class ConfigTests(unittest.TestCase):
    def test_competition_labels_cover_three_cups(self) -> None:
        self.assertEqual(set(COMPETITION_LABELS), {"CL", "EL", "UECL"})

    def test_season_year_is_start_year(self) -> None:
        config = Config()
        year = config.season_year
        today = datetime.now(timezone.utc).date()
        self.assertEqual(year, today.year if today.month >= 7 else today.year - 1)


class EspnNormalizationTests(unittest.TestCase):
    def _event(self, state: str, score: str = "0") -> dict:
        return {
            "id": "123",
            "date": "2026-11-05T17:45Z",
            "season": {"year": 2026, "slug": "league-phase"},
            "competitions": [
                {
                    "status": {
                        "displayClock": "0'",
                        "type": {"state": state, "name": f"STATUS_{state.upper()}"},
                    },
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": score,
                            "team": {
                                "displayName": "Trabzonspor",
                                "shortDisplayName": "Trabzonspor",
                                "abbreviation": "TRA",
                                "logo": "https://a.espncdn.com/trabzon.png",
                            },
                        },
                        {
                            "homeAway": "away",
                            "score": score,
                            "team": {
                                "displayName": "SC Freiburg",
                                "shortDisplayName": "Freiburg",
                                "abbreviation": "SCF",
                                "logo": "https://a.espncdn.com/freiburg.png",
                            },
                        },
                    ],
                }
            ],
        }

    def test_scheduled_match_has_no_score(self) -> None:
        parsed = EspnProvider._normalize_event(
            self._event("pre"), "UECL", "uefa.europa.conf", 2026
        )
        assert parsed is not None
        self.assertEqual(parsed["status"], "TIMED")
        self.assertEqual(parsed["score"], {"home": None, "away": None})

    def test_finished_match_has_score(self) -> None:
        parsed = EspnProvider._normalize_event(
            self._event("post", "3"), "UECL", "uefa.europa.conf", 2026
        )
        assert parsed is not None
        self.assertEqual(parsed["status"], "FINISHED")
        self.assertEqual(parsed["score"], {"home": 3, "away": 3})

    def test_other_season_is_ignored(self) -> None:
        event = self._event("pre")
        event["season"]["year"] = 2025
        self.assertIsNone(
            EspnProvider._normalize_event(event, "UECL", "uefa.europa.conf", 2026)
        )


if __name__ == "__main__":
    unittest.main()
