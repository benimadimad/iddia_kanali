from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any

from . import repository
from .config import Config
from .providers import ProviderError, fetch_provider_data
from .service import LeagueService
from .utils import iso_utc, local_day, utc_now

log = logging.getLogger(__name__)


class SyncService:
    """Single-process synchronizer.

    The app deliberately uses one worker. If you scale to multiple web workers,
    move the scheduler to a separate cron job so only one process calls the API.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._lock = threading.Lock()

    def sync(self) -> dict[str, Any]:
        if self.config.is_demo:
            from .providers.demo import seed_demo

            seed_demo(self.config.database_path)
            state = repository.get_sync_state(self.config.database_path)
            return {
                "ok": True,
                "provider": "demo",
                "demo": True,
                "last_success_at": state.get("last_success_at"),
                "matches_seen": state.get("matches_seen", 0),
            }

        if not self._lock.acquire(blocking=False):
            return {"ok": False, "busy": True, "message": "Senkronizasyon zaten çalışıyor."}

        started = utc_now()
        repository.update_sync_state(
            self.config.database_path,
            provider=self.config.provider,
            attempted_at=iso_utc(started),
        )
        try:
            today = started.astimezone().date()
            date_from = (today - timedelta(days=self.config.sync_past_days)).isoformat()
            date_to = (today + timedelta(days=self.config.sync_future_days)).isoformat()
            result = fetch_provider_data(self.config, date_from, date_to)

            for competition in result.competitions:
                repository.upsert_competition(self.config.database_path, **competition)
            changed = repository.upsert_matches(
                self.config.database_path, result.matches
            )
            if result.complete:
                repository.delete_competitions_except(
                    self.config.database_path, self.config.competitions
                )
                repository.delete_matches_not_in(
                    self.config.database_path,
                    [
                        (match["provider"], str(match["external_id"]))
                        for match in result.matches
                    ],
                )
            else:
                log.warning(
                    "Partial sync: keeping previously stored matches until all sources recover."
                )
            finished_at = utc_now()
            repository.update_sync_state(
                self.config.database_path,
                provider=self.config.provider,
                success_at=iso_utc(finished_at),
                matches_seen=len(result.matches),
                changed=changed,
            )
            log.info(
                "Sync complete: %s matches, %s changed in %.1fs",
                len(result.matches),
                changed,
                (finished_at - started).total_seconds(),
            )
            return {
                "ok": True,
                "provider": self.config.provider,
                "matches_seen": len(result.matches),
                "changed": changed,
                "duration_seconds": round((finished_at - started).total_seconds(), 1),
            }
        except Exception as exc:  # Keep the existing data visible on API failure.
            message = str(exc) if isinstance(exc, ProviderError) else "Beklenmeyen veri hatası."
            log.exception("Sync failed")
            repository.update_sync_state(
                self.config.database_path,
                provider=self.config.provider,
                error=message,
                changed=0,
            )
            return {"ok": False, "error": message}
        finally:
            self._lock.release()

    def state(self) -> dict[str, Any]:
        state = repository.get_sync_state(self.config.database_path)
        return {
            "provider": state.get("provider"),
            "last_attempt_at": state.get("last_attempt_at"),
            "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error"),
            "matches_seen": state.get("matches_seen", 0),
        }


class SyncScheduler:
    def __init__(self, service: SyncService, interval_seconds: int) -> None:
        self.service = service
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="league-sync", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        # Give the web server a moment to bind, then do an initial sync.
        if self._stop.wait(2):
            return
        while not self._stop.is_set():
            try:
                self.service.sync()
            except Exception:
                log.exception("Unhandled scheduler error")
            if self._stop.wait(self.interval_seconds):
                break


def bootstrap(config: Config) -> tuple[LeagueService, SyncService, SyncScheduler]:
    repository.configure_from_config(config)
    repository.init_db(config.database_path)
    service = LeagueService(config)
    service.ensure_ready()

    if config.is_demo:
        now = iso_utc(utc_now())
        state = repository.get_sync_state(config.database_path)
        if not state.get("last_success_at"):
            repository.update_sync_state(
                config.database_path,
                provider="demo",
                attempted_at=now,
                success_at=now,
                matches_seen=len(repository.list_matches(config.database_path)),
            )

    sync_service = SyncService(config)
    scheduler = SyncScheduler(sync_service, config.sync_interval_seconds)
    return service, sync_service, scheduler
