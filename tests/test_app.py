from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DISABLE_SCHEDULER", "1")

from app import create_app  # noqa: E402
from league import repository  # noqa: E402
from league.config import Config  # noqa: E402
from league.db import session  # noqa: E402
from league.scoring import score_outcome  # noqa: E402


class AppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config = Config(
            database_path=Path(self._tmp.name) / "test.db",
            admin_password="test-password",
            secret_key="test-secret-key",
            data_provider="demo",
            football_data_token="",
            competitions=("PL", "PD", "BL1", "SA", "FL1", "CL", "DED", "PPL"),
            timezone="Europe/Istanbul",
            sync_interval_seconds=60,
        )
        self.app = create_app(self.config, start_scheduler=False)
        self.client = self.app.test_client()
        self.service = self.app.extensions["get_league_service"]()

    def login(self) -> str:
        response = self.client.post(
            "/admin/login", data={"password": self.config.admin_password}
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            return session["csrf"]


class PublicApiTests(AppTestCase):
    def test_league_payload_is_public_and_not_cached(self) -> None:
        response = self.client.get("/api/league")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        payload = response.get_json()
        self.assertTrue(payload["meta"]["demo"])
        self.assertGreater(payload["meta"]["counts"]["matches"], 0)
        self.assertIn("standings", payload)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["demo"])
        self.assertGreater(payload["matches"], 0)

    def test_unknown_api_route_returns_json_404(self) -> None:
        response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["ok"])

    def test_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])


    def test_standings_break_down_correct_by_team(self) -> None:
        payload = self.client.get("/api/league").get_json()
        self.assertTrue(payload["standings"])
        for row in payload["standings"]:
            self.assertEqual(
                set(row["team_correct"]), {"FB", "GS", "BJK", "TS"}
            )
            self.assertLessEqual(
                sum(row["team_correct"].values()), row["correct_outcomes"]
            )


class PredictionVisibilityTests(AppTestCase):
    def test_future_predictions_are_revealed(self) -> None:
        payload = self.client.get("/api/league").get_json()
        upcoming = [
            match
            for match in payload["matches"]
            if not match["is_started"] and match["status_group"] == "upcoming"
        ]
        self.assertTrue(upcoming)
        for match in upcoming:
            self.assertTrue(match["predictions_visible"])
            for entry in match["predictions"]:
                self.assertIsNone(entry["points"])
                self.assertIsNone(entry["correct_outcome"])

    def test_started_predictions_are_revealed_and_scored(self) -> None:
        payload = self.client.get("/api/league").get_json()
        finished = [match for match in payload["matches"] if match["is_finished"]]
        self.assertTrue(finished)
        match = finished[0]
        self.assertTrue(match["predictions_visible"])
        self.assertTrue(match["predictions"])
        scoring = payload["meta"]["scoring"]
        from league.scoring import ScoringConfig

        config = ScoringConfig.from_mapping(scoring)
        for entry in match["predictions"]:
            expected = score_outcome(
                entry["outcome"],
                match["score"]["home"],
                match["score"]["away"],
                config,
                bool(entry["joker"]),
            )
            self.assertEqual(entry["points"], expected["points"])


class BonusPointsTests(AppTestCase):
    def test_bonus_points_are_added_to_total(self) -> None:
        before = self.client.get("/api/league").get_json()["standings"][0]
        with session(self.config.database_path) as conn:
            conn.execute(
                "UPDATE players SET bonus_points = ? WHERE id = ?",
                (2, before["id"]),
            )
        after = next(
            row
            for row in self.client.get("/api/league").get_json()["standings"]
            if row["id"] == before["id"]
        )
        self.assertEqual(after["bonus_points"], 2)
        self.assertEqual(after["points"], before["points"] + 2)


class AdminTests(AppTestCase):
    def test_admin_requires_login(self) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.headers["Location"])

        response = self.client.get("/admin/api/bootstrap")
        self.assertEqual(response.status_code, 401)

    def test_wrong_password_is_rejected(self) -> None:
        response = self.client.post("/admin/login", data={"password": "nope"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("Şifre hatalı", response.get_data(as_text=True))

    def test_mutations_require_csrf_token(self) -> None:
        self.login()
        response = self.client.post("/admin/api/sync")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["ok"])

    def test_sync_with_csrf_token_succeeds_in_demo_mode(self) -> None:
        csrf = self.login()
        response = self.client.post(
            "/admin/api/sync", headers={"X-CSRF-Token": csrf}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_prediction_can_be_saved_before_kickoff(self) -> None:
        csrf = self.login()
        payload = self.client.get("/api/league").get_json()
        match = next(
            match
            for match in payload["matches"]
            if not match["is_started"] and match["status_group"] == "upcoming"
        )
        player = payload["players"][0]

        response = self.client.put(
            "/admin/api/predictions",
            headers={"X-CSRF-Token": csrf},
            json={
                "player_id": player["id"],
                "items": [{"match_id": match["id"], "outcome": "H", "joker": True}],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

        prediction = next(
            item
            for item in repository.list_predictions(
                self.config.database_path, [match["id"]]
            )
            if item["player_id"] == player["id"]
        )
        self.assertEqual(prediction["outcome"], "H")
        self.assertEqual(prediction["joker"], 1)

    def test_prediction_for_finished_match_is_rejected(self) -> None:
        csrf = self.login()
        payload = self.client.get("/api/league").get_json()
        match = next(match for match in payload["matches"] if match["is_finished"])
        player = payload["players"][0]

        response = self.client.put(
            "/admin/api/predictions",
            headers={"X-CSRF-Token": csrf},
            json={
                "player_id": player["id"],
                "items": [{"match_id": match["id"], "outcome": "H"}],
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_scoring_can_be_updated(self) -> None:
        csrf = self.login()
        response = self.client.put(
            "/admin/api/scoring",
            headers={"X-CSRF-Token": csrf},
            json={"exact_score": 7, "status": "final", "label": "Kesin"},
        )
        self.assertEqual(response.status_code, 200)
        scoring = response.get_json()["scoring"]
        self.assertEqual(scoring["exact_score"], 7)
        self.assertEqual(scoring["status"], "final")
        self.assertEqual(scoring["label"], "Kesin")


if __name__ == "__main__":
    unittest.main()
