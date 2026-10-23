from __future__ import annotations

import logging
import os
import secrets
from functools import wraps
from typing import Any, Callable

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from league import repository
from league.config import Config
from league.scoring import ScoringConfig
from league.service import FINISHED_STATUSES, INACTIVE_STATUSES, LIVE_STATUSES, LeagueService
from league.sync import SyncScheduler, SyncService, bootstrap
from league.utils import parse_iso, utc_now

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _admin_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not session.get("admin"):
            if request.path.startswith("/admin/api/"):
                return jsonify({"ok": False, "error": "Oturum gerekli."}), 401
            return redirect(url_for("admin_login", next=request.path))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not token or not secrets.compare_digest(token, session.get("csrf", "")):
                return jsonify({"ok": False, "error": "CSRF doğrulaması başarısız."}), 403
        return view(*args, **kwargs)

    return wrapped


def _is_locked(match: dict[str, Any]) -> bool:
    kickoff = parse_iso(match.get("kickoff"))
    if match.get("status") in LIVE_STATUSES | FINISHED_STATUSES | INACTIVE_STATUSES:
        return True
    return bool(kickoff and kickoff <= utc_now())


def create_app(
    config: Config | None = None, *, start_scheduler: bool | None = None
) -> Flask:
    config = config or Config()
    app = Flask(__name__, static_folder="public/static", static_url_path="/static")
    app.config.update(config.as_flask_config())

    # Lazy initialization to avoid crashing on cold start
    _extensions = {}

    def get_service():
        if "league_service" not in _extensions:
            _extensions["league_service"], _extensions["league_sync"], _extensions["league_scheduler"] = bootstrap(config)
            _extensions["league_config"] = config
        return _extensions["league_service"]

    def get_sync():
        if "league_sync" not in _extensions:
            get_service()
        return _extensions["league_sync"]

    def get_scheduler():
        if "league_scheduler" not in _extensions:
            get_service()
        return _extensions["league_scheduler"]

    app.extensions["league_config"] = config
    app.extensions["get_league_service"] = get_service
    app.extensions["get_league_sync"] = get_sync
    app.extensions["get_league_scheduler"] = get_scheduler

    if start_scheduler is None:
        start_scheduler = os.getenv("DISABLE_SCHEDULER", "0") not in {"1", "true", "yes"}
        if os.getenv("VERCEL"):
            # Serverless functions must not keep background threads.
            start_scheduler = False
    if start_scheduler:
        sched = app.extensions["get_league_scheduler"]()
        sched.start()

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: blob: https://crests.football-data.org https://a.espncdn.com; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            league_name=config.league_name,
            demo=config.is_demo,
        )

    @app.get("/api/test")
    def api_test():
        return jsonify({"ok": True, "message": "Flask works, Vercel OK"})

    @app.get("/api/league")
    def api_league():
        try:
            service = app.extensions["get_league_service"]()
            return jsonify(service.public_payload())
        except Exception:
            log.exception("League endpoint failed")
            return jsonify({"ok": False, "error": "Sunucu hatası."}), 500

    @app.get("/api/health")
    def api_health():
        try:
            service = app.extensions["get_league_service"]()
            payload = service.public_payload()
            return jsonify(
                {
                    "ok": True,
                    "demo": payload["meta"]["demo"],
                    "matches": payload["meta"]["counts"]["matches"],
                "live": payload["meta"]["counts"]["live"],
                "last_sync": payload["meta"]["sync"]["last_success_at"],
                "generated_at": payload["meta"]["generated_at"],
            }
        )
        except Exception:
            log.exception("Health endpoint failed")
            return jsonify({"ok": False, "error": "Sunucu hatası."}), 500

    @app.get("/admin/login")
    def admin_login():
        if session.get("admin"):
            return redirect(url_for("admin_page"))
        return render_template("admin_login.html", league_name=config.league_name, error=None)

    @app.post("/admin/login")
    def admin_login_post():
        password = request.form.get("password", "")
        if secrets.compare_digest(password, config.admin_password):
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_urlsafe(32)
            return redirect(url_for("admin_page"))
        return (
            render_template(
                "admin_login.html",
                league_name=config.league_name,
                error="Şifre hatalı.",
            ),
            401,
        )

    @app.post("/admin/logout")
    @_admin_required
    def admin_logout():
        session.clear()
        return redirect(url_for("index"))

    @app.get("/admin")
    @_admin_required
    def admin_page():
        return render_template(
            "admin.html",
            league_name=config.league_name,
            csrf_token=session.get("csrf", ""),
            demo=config.is_demo,
        )

    @app.get("/admin/api/bootstrap")
    @_admin_required
    def admin_bootstrap():
        service = app.extensions["get_league_service"]()
        payload = service.admin_payload()
        payload["csrf_token"] = session.get("csrf", "")
        return jsonify(payload)

    @app.post("/admin/api/sync")
    @_admin_required
    def admin_sync():
        sync_service = app.extensions["get_league_sync"]()
        result = sync_service.sync()
        status = 200 if result.get("ok") else 409
        return jsonify(result), status

    @app.put("/admin/api/predictions")
    @_admin_required
    def admin_save_predictions():
        body = request.get_json(silent=True) or {}
        try:
            player_id = int(body.get("player_id"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Oyuncu seçilmedi."}), 400

        player = repository.get_player(config.database_path, player_id)
        if not player:
            return jsonify({"ok": False, "error": "Oyuncu bulunamadı."}), 404

        items = body.get("items")
        if not isinstance(items, list) or not items:
            return jsonify({"ok": False, "error": "Kaydedilecek tahmin yok."}), 400
        if len(items) > 100:
            return jsonify({"ok": False, "error": "Tek seferde en fazla 100 tahmin."}), 400

        validated: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                return jsonify({"ok": False, "error": "Geçersiz tahmin satırı."}), 400
            try:
                match_id = int(item.get("match_id"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "Geçersiz maç."}), 400
            if match_id in seen:
                return jsonify({"ok": False, "error": "Aynı maç birden fazla gönderildi."}), 400
            seen.add(match_id)

            match = repository.get_match(config.database_path, match_id)
            if not match:
                return jsonify({"ok": False, "error": "Maç bulunamadı."}), 404
            if _is_locked(match):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "Başlamış veya bitmiş bir maça tahmin kaydedilemez.",
                        }
                    ),
                    409,
                )

            raw_outcome = item.get("outcome")
            outcome = str(raw_outcome).strip().upper() if raw_outcome else ""
            if not outcome:
                validated.append({"match_id": match_id, "delete": True})
                continue
            if outcome not in {"H", "D", "A"}:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "Tahmin ev sahibi, beraberlik veya deplasman olmalı.",
                        }
                    ),
                    400,
                )
            validated.append(
                {
                    "match_id": match_id,
                    "outcome": outcome,
                    "joker": bool(item.get("joker")),
                    "delete": False,
                }
            )

        for item in validated:
            if item["delete"]:
                repository.delete_prediction(
                    config.database_path,
                    player_id=player_id,
                    match_id=item["match_id"],
                )
            else:
                repository.upsert_prediction(
                    config.database_path,
                    player_id=player_id,
                    match_id=item["match_id"],
                    outcome=item["outcome"],
                    joker=item["joker"],
                )
        return jsonify({"ok": True, "saved": len(validated), "player": player["name"]})

    @app.post("/admin/api/players")
    @_admin_required
    def admin_create_player():
        body = request.get_json(silent=True) or {}
        try:
            player = repository.create_player(
                config.database_path,
                str(body.get("name", "")),
                body.get("color"),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "player": player}), 201

    @app.patch("/admin/api/players/<int:player_id>")
    @_admin_required
    def admin_update_player(player_id: int):
        body = request.get_json(silent=True) or {}
        active = body.get("active")
        try:
            player = repository.update_player(
                config.database_path,
                player_id,
                name=body.get("name"),
                color=body.get("color"),
                active=bool(active) if active is not None else None,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "player": player})

    @app.put("/admin/api/scoring")
    @_admin_required
    def admin_save_scoring():
        body = request.get_json(silent=True) or {}
        current = repository.get_scoring(config.database_path).to_dict()
        current.update(body)
        scoring = repository.set_scoring(
            config.database_path, ScoringConfig.from_mapping(current)
        )
        return jsonify({"ok": True, "scoring": scoring.to_dict()})

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/api/cron/sync")
    def api_cron_sync():
        secret = os.getenv("CRON_SECRET", "")
        header = request.headers.get("Authorization", "")
        provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not secret or not secrets.compare_digest(provided, secret):
            return jsonify({"ok": False, "error": "Yetkisiz."}), 401
        sync_service = app.extensions["get_league_sync"]()
        result = sync_service.sync()
        return jsonify(result), 200 if result.get("ok") else 503

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({"ok": False, "error": "Bulunamadı."}), 404
        return render_template("404.html", league_name=config.league_name), 404

    return app


# Vercel detects this WSGI app from app.py automatically.
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=False)
