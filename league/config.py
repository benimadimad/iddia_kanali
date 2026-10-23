from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_dotenv() -> None:
    """Small .env reader so the project has no runtime dependency for local use."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _database_path() -> Path:
    """SQLite is not writable in Vercel's deployment filesystem.

    A per-instance /tmp copy is only a demo/read-only bootstrap fallback;
    durable writes require DATA_BACKEND=firestore.
    """
    custom = os.getenv("DATABASE_PATH")
    if custom:
        return Path(custom)
    bundled = BASE_DIR / "data" / "league.db"
    if os.getenv("VERCEL") and os.getenv("DATA_BACKEND", "sqlite").lower() != "firestore":
        target = Path(tempfile.gettempdir()) / "tahmin-ligi" / "league.db"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if bundled.exists():
                shutil.copy2(bundled, target)
        return target
    return bundled


@dataclass(frozen=True)
class Config:
    league_name: str = field(
        default_factory=lambda: os.getenv("LEAGUE_NAME", "Tahmin Ligi")
    )
    database_path: Path = field(
        default_factory=_database_path
    )
    data_backend: str = field(
        default_factory=lambda: os.getenv("DATA_BACKEND", "sqlite").strip().lower()
    )
    firebase_project_id: str = field(
        default_factory=lambda: os.getenv("FIREBASE_PROJECT_ID", "").strip()
    )
    firebase_service_account: str = field(
        default_factory=lambda: os.getenv(
            "FIREBASE_SERVICE_ACCOUNT",
            str(BASE_DIR / "secrets" / "firebase-service-account.json"),
        ).strip()
    )
    admin_password: str = field(
        default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin123")
    )
    secret_key: str = field(
        default_factory=lambda: os.getenv(
            "SECRET_KEY", "local-dev-secret-change-this-before-deploying"
        )
    )
    data_provider: str = field(
        default_factory=lambda: os.getenv("DATA_PROVIDER", "auto").lower()
    )
    football_data_token: str = field(
        default_factory=lambda: os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    )
    competitions: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip().upper()
            for item in os.getenv(
                "FOOTBALL_DATA_COMPETITIONS",
                "CL,EL,UECL",
            ).split(",")
            if item.strip()
        )
    )
    timezone: str = field(
        default_factory=lambda: os.getenv("APP_TIMEZONE", "Europe/Istanbul")
    )
    sync_interval_seconds: int = field(
        default_factory=lambda: max(60, _env_int("SYNC_INTERVAL_SECONDS", 180))
    )
    sync_past_days: int = field(
        default_factory=lambda: max(0, _env_int("SYNC_PAST_DAYS", 21))
    )
    sync_future_days: int = field(
        default_factory=lambda: max(1, _env_int("SYNC_FUTURE_DAYS", 21))
    )
    session_cookie_secure: bool = field(
        default_factory=lambda: _env_bool("SESSION_COOKIE_SECURE", False)
    )
    show_demo_banner: bool = field(
        default_factory=lambda: _env_bool("SHOW_DEMO_BANNER", True)
    )

    @property
    def provider(self) -> str:
        if self.data_provider in {"demo", "football-data", "tracked"}:
            return self.data_provider
        # This project follows four Turkish clubs; use the combined source by default.
        return "tracked" if self.football_data_token else "demo"

    @property
    def is_demo(self) -> bool:
        return self.provider == "demo"

    @property
    def season_year(self) -> int:
        """Start year of the current European season (e.g. 2026 for 2026-27)."""
        from .utils import utc_now

        today = utc_now().date()
        return today.year if today.month >= 7 else today.year - 1

    @property
    def source_label(self) -> str:
        if self.is_demo:
            return "Demo fikstür"
        if self.provider == "tracked":
            return "football-data.org + ESPN"
        return "football-data.org"

    def as_flask_config(self) -> dict:
        return {
            "SECRET_KEY": self.secret_key,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": self.session_cookie_secure,
            "MAX_CONTENT_LENGTH": 1_000_000,
        }
