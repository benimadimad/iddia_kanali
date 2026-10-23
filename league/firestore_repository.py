"""Firestore implementation of the storage API.

Enabled with ``DATA_BACKEND=firestore``. Credentials come from a service
account JSON file (default ``secrets/firebase-service-account.json``), a raw
JSON string or a base64 encoded JSON string in ``FIREBASE_SERVICE_ACCOUNT``.

Document layout
---------------
players/{id}
competitions/{code}
matches/{id}
match_keys/{provider}:{externalId}   -> { match_id }
predictions/{playerId}_{matchId}
settings/{key}
sync_state/current
meta/counters                        -> { player, match }
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .scoring import DEFAULT_SCORING, ScoringConfig
from .sqlite_repository import PLAYER_COLORS, row_to_match
from .utils import iso_utc, safe_color, slugify, utc_now

log = logging.getLogger(__name__)

_BATCH_SIZE = 400
_IN_QUERY_SIZE = 30


def _chunks(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _match_key(provider: str, external_id: str | int) -> str:
    # Firestore document IDs cannot contain slashes.
    return f"{provider}:{str(external_id).replace('/', '_')}"


def _load_service_account(value: str) -> dict[str, Any]:
    raw = (value or "").strip()
    if not raw:
        raise RuntimeError(
            "Firebase service account bulunamadı. FIREBASE_SERVICE_ACCOUNT ayarlayın."
        )

    # Environment variable JSON and base64 values can be thousands of chars.
    # Trying them as filenames first can raise OSError: File name too long.
    if raw.startswith("{"):
        return json.loads(raw)

    if len(raw) < 240 and "\n" not in raw:
        path = Path(raw)
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            pass

    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - surface a clear configuration error
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT bir dosya yolu, JSON veya base64 JSON olmalı."
        ) from exc

    return json.loads(decoded)


class FirestoreRepository:
    """Same API as :mod:`league.sqlite_repository`, backed by Firestore."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self._db: Any = None
        self._ready = False

    # ------------------------------------------------------------------ client

    def _client(self) -> Any:
        if self._db is not None:
            return self._db

        try:
            from google.cloud import firestore
            from google.oauth2 import service_account
        except ImportError as exc:  # pragma: no cover - depends on deployment
            raise RuntimeError(
                "Firestore için 'google-cloud-firestore' paketi gerekli."
            ) from exc

        info = _load_service_account(self.config.firebase_service_account)
        credentials = service_account.Credentials.from_service_account_info(info)
        project = self.config.firebase_project_id or info.get("project_id")
        self._db = firestore.Client(project=project, credentials=credentials)
        log.info("Firestore bağlantısı kuruldu (project=%s).", project)
        return self._db

    @property
    def db(self) -> Any:
        return self._client()

    # ----------------------------------------------------------------- helpers

    def _collection(self, name: str) -> Any:
        return self.db.collection(name)

    def _document(self, collection: str, doc_id: str) -> Any:
        return self.db.collection(collection).document(str(doc_id))

    def _delete_refs(self, refs: Sequence[Any]) -> int:
        deleted = 0
        for chunk in _chunks(refs, _BATCH_SIZE):
            if not chunk:
                continue
            batch = self.db.batch()
            for ref in chunk:
                batch.delete(ref)
            batch.commit()
            deleted += len(chunk)
        return deleted

    def _next_id(self, key: str) -> int:
        ref = self.db.collection("meta").document("counters")
        transaction = self.db.transaction()
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        value = int(data.get(key) or 0) + 1
        transaction.set(ref, {key: value}, merge=True)
        transaction.commit()
        return value

    def _ensure_counters(self) -> None:
        ref = self.db.collection("meta").document("counters")
        snapshot = ref.get()
        if snapshot.exists:
            return

        player_max = 0
        for doc in self.db.collection("players").stream():
            player_max = max(player_max, int((doc.to_dict() or {}).get("id") or 0))
        match_max = 0
        for doc in self.db.collection("matches").stream():
            match_max = max(match_max, int((doc.to_dict() or {}).get("id") or 0))
        ref.set({"player": player_max, "match": match_max}, merge=True)

    def _next_player_id(self) -> int:
        return self._next_id("player")

    def _next_match_id(self) -> int:
        return self._next_id("match")

    def _delete_predictions_for_matches(self, match_ids: Sequence[int]) -> None:
        refs: list[Any] = []
        for chunk in _chunks([int(mid) for mid in match_ids], _IN_QUERY_SIZE):
            if not chunk:
                continue
            query = self.db.collection("predictions").where("match_id", "in", list(chunk))
            refs.extend(doc.reference for doc in query.stream())
        self._delete_refs(refs)

    # ------------------------------------------------------------------ schema

    def init_db(self, path: Any = None) -> None:
        if self._ready:
            return
        self._ensure_counters()
        self._ready = True

    # ----------------------------------------------------------------- players

    def list_players(
        self, path: Any = None, active_only: bool = False
    ) -> list[dict[str, Any]]:
        players: list[dict[str, Any]] = []
        for doc in self._collection("players").stream():
            item = doc.to_dict() or {}
            item["id"] = int(item.get("id") or doc.id)
            if active_only and not int(item.get("active", 1)):
                continue
            players.append(item)
        players.sort(key=lambda item: (-int(item.get("active", 1)), item["name"].casefold()))
        return players

    def get_player(self, path: Any = None, player_id: int = 0) -> dict[str, Any] | None:
        snapshot = self._document("players", player_id).get()
        if not snapshot.exists:
            return None
        item = snapshot.to_dict() or {}
        item["id"] = int(item.get("id") or player_id)
        return item

    def create_player(
        self, path: Any = None, name: str = "", color: str | None = None
    ) -> dict[str, Any]:
        name = " ".join(name.strip().split())
        if not (2 <= len(name) <= 40):
            raise ValueError("Oyuncu adı 2-40 karakter arasında olmalı.")

        players = self.list_players()
        if any(item["name"].casefold() == name.casefold() for item in players):
            raise ValueError("Bu isimde bir oyuncu zaten var.")

        base_slug = slugify(name)
        slug = base_slug
        suffix = 2
        used = {item.get("slug") for item in players}
        while slug in used:
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        chosen_color = safe_color(
            color, PLAYER_COLORS[len(players) % len(PLAYER_COLORS)]
        )
        now = iso_utc(utc_now())
        player_id = self._next_player_id()
        payload = {
            "id": player_id,
            "name": name,
            "slug": slug,
            "color": chosen_color,
            "active": 1,
            "bonus_points": 0,
            "created_at": now,
        }
        self._document("players", player_id).set(payload)
        return payload

    def update_player(
        self,
        path: Any = None,
        player_id: int = 0,
        *,
        name: str | None = None,
        color: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        current = self.get_player(None, player_id)
        if not current:
            raise ValueError("Oyuncu bulunamadı.")

        payload: dict[str, Any] = {}
        if name is not None:
            name = " ".join(name.strip().split())
            if not (2 <= len(name) <= 40):
                raise ValueError("Oyuncu adı 2-40 karakter arasında olmalı.")
            if any(
                item["id"] != player_id and item["name"].casefold() == name.casefold()
                for item in self.list_players()
            ):
                raise ValueError("Bu isimde bir oyuncu zaten var.")
            payload["name"] = name
        if color is not None:
            payload["color"] = safe_color(color)
        if active is not None:
            payload["active"] = 1 if active else 0

        if not payload:
            raise ValueError("Güncellenecek alan yok.")

        self._document("players", player_id).set(payload, merge=True)
        updated = self.get_player(None, player_id)
        assert updated is not None
        return updated

    # ------------------------------------------------------------ competitions

    def upsert_competition(
        self,
        path: Any = None,
        *,
        code: str,
        name: str,
        country: str | None = None,
        emblem: str | None = None,
        sort_order: int = 100,
    ) -> None:
        ref = self._document("competitions", code)
        existing = ref.get()
        payload: dict[str, Any] = {"code": code, "name": name, "sort_order": sort_order}
        current = existing.to_dict() if existing.exists else {}
        if country is not None or not current:
            payload["country"] = country
        if emblem is not None or not current:
            payload["emblem"] = emblem
        ref.set(payload, merge=True)

    def delete_competitions_except(
        self, path: Any = None, codes: list[str] | tuple[str, ...] = ()
    ) -> int:
        keep = {str(code).strip().upper() for code in codes if str(code).strip()}
        refs = [
            doc.reference
            for doc in self._collection("competitions").stream()
            if str((doc.to_dict() or {}).get("code") or doc.id).upper() not in keep
        ]
        return self._delete_refs(refs)

    def list_competitions(self, path: Any = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for doc in self._collection("competitions").stream():
            item = doc.to_dict() or {}
            item["code"] = item.get("code") or doc.id
            items.append(item)
        items.sort(key=lambda item: (int(item.get("sort_order") or 100), item.get("name") or ""))
        return items

    # ---------------------------------------------------------------- matches

    @staticmethod
    def _flat_match(match: dict[str, Any], match_id: int, now: str) -> dict[str, Any]:
        return {
            "id": match_id,
            "provider": match["provider"],
            "external_id": str(match["external_id"]),
            "competition_code": match["competition_code"],
            "season": match.get("season"),
            "matchday": match.get("matchday"),
            "stage": match.get("stage"),
            "kickoff_utc": match["kickoff"],
            "status": match["status"],
            "minute": match.get("minute"),
            "home_name": match["home"]["name"],
            "home_short": match["home"].get("short"),
            "home_tla": match["home"].get("tla"),
            "home_crest": match["home"].get("crest"),
            "away_name": match["away"]["name"],
            "away_short": match["away"].get("short"),
            "away_tla": match["away"].get("tla"),
            "away_crest": match["away"].get("crest"),
            "home_score": match["score"].get("home"),
            "away_score": match["score"].get("away"),
            "last_updated": match.get("last_updated"),
            "updated_at": now,
        }

    @staticmethod
    def _match_signature(match: dict[str, Any]) -> tuple[Any, ...]:
        return (
            match.get("status"),
            match.get("home_score"),
            match.get("away_score"),
            match.get("kickoff_utc"),
            match.get("last_updated"),
            match.get("home_name"),
            match.get("away_name"),
        )

    def upsert_matches(self, path: Any = None, matches: Iterable[dict[str, Any]] = ()) -> int:
        now = iso_utc(utc_now())
        changed = 0
        for match in matches:
            external_id = str(match["external_id"])
            key = _match_key(match["provider"], external_id)
            mapping_ref = self._document("match_keys", key)
            mapping = mapping_ref.get()

            if mapping.exists:
                match_id = int((mapping.to_dict() or {}).get("match_id") or 0)
                ref = self._document("matches", match_id)
                snapshot = ref.get()
                if not snapshot.exists:
                    # Mapping without a match: repair it below.
                    mapping_ref.delete()
                    mapping = None

            if not mapping or not mapping.exists:
                match_id = self._next_match_id()
                payload = self._flat_match(match, match_id, now)
                payload["created_at"] = now
                batch = self.db.batch()
                batch.set(self._document("matches", match_id), payload)
                batch.set(
                    mapping_ref,
                    {
                        "provider": match["provider"],
                        "external_id": external_id,
                        "match_id": match_id,
                    },
                )
                batch.commit()
                changed += 1
                continue

            existing = snapshot.to_dict() or {}
            incoming = self._flat_match(match, match_id, now)
            if self._match_signature(existing) == self._match_signature(incoming):
                continue
            if existing.get("status") in {"FINISHED", "AWARDED"} and incoming.get(
                "status"
            ) in {"SCHEDULED", "TIMED"}:
                continue

            # Keep the original creation timestamp.
            incoming.pop("created_at", None)
            ref.set(incoming, merge=True)
            changed += 1
        return changed

    def list_matches(self, path: Any = None) -> list[dict[str, Any]]:
        rows = [doc.to_dict() or {} for doc in self._collection("matches").stream()]
        rows.sort(key=lambda item: item.get("kickoff_utc") or "")
        return [row_to_match(row) for row in rows]

    def get_match(self, path: Any = None, match_id: int = 0) -> dict[str, Any] | None:
        snapshot = self._document("matches", match_id).get()
        if not snapshot.exists:
            return None
        return row_to_match(snapshot.to_dict() or {})

    def delete_demo_matches(self, path: Any = None) -> None:
        docs = [
            doc
            for doc in self._collection("matches").stream()
            if (doc.to_dict() or {}).get("provider") == "demo"
        ]
        if not docs:
            return
        ids = [int((doc.to_dict() or {}).get("id") or doc.id) for doc in docs]
        self._delete_predictions_for_matches(ids)
        keys = [
            _match_key("demo", str((doc.to_dict() or {}).get("external_id") or ""))
            for doc in docs
        ]
        self._delete_refs([doc.reference for doc in docs])
        self._delete_refs([self._document("match_keys", key) for key in keys])

    def delete_matches_not_in(
        self, path: Any = None, keys: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()
    ) -> int:
        allowed = {f"{provider}:{str(external).replace('/', '_')}" for provider, external in keys}
        stale = []
        for doc in self._collection("matches").stream():
            item = doc.to_dict() or {}
            key = _match_key(str(item.get("provider")), str(item.get("external_id")))
            if key not in allowed:
                stale.append((doc, item))

        if not stale:
            return 0

        ids = [int(item.get("id") or doc.id) for doc, item in stale]
        self._delete_predictions_for_matches(ids)
        self._delete_refs([doc.reference for doc, _ in stale])
        self._delete_refs([self._document("match_keys", _match_key(
            str(item.get("provider")), str(item.get("external_id"))
        )) for _, item in stale])
        return len(stale)

    # ------------------------------------------------------------- predictions

    @staticmethod
    def _prediction_id(player_id: int, match_id: int) -> str:
        return f"{int(player_id)}_{int(match_id)}"

    def list_predictions(
        self, path: Any = None, match_ids: list[int] | None = None
    ) -> list[dict[str, Any]]:
        allowed = {int(mid) for mid in match_ids} if match_ids is not None else None
        items: list[dict[str, Any]] = []
        for doc in self._collection("predictions").stream():
            item = doc.to_dict() or {}
            item["player_id"] = int(item.get("player_id") or 0)
            item["match_id"] = int(item.get("match_id") or 0)
            if allowed is not None and item["match_id"] not in allowed:
                continue
            items.append(item)
        items.sort(key=lambda item: (item["match_id"], item["player_id"]))
        return items

    def upsert_prediction(
        self,
        path: Any = None,
        *,
        player_id: int,
        match_id: int,
        outcome: str,
        joker: bool,
    ) -> dict[str, Any]:
        outcome = (outcome or "").upper()
        if outcome not in {"H", "D", "A"}:
            raise ValueError("Tahmin ev sahibi, beraberlik veya deplasman olmalı.")

        ref = self._document("predictions", self._prediction_id(player_id, match_id))
        snapshot = ref.get()
        now = iso_utc(utc_now())
        created_at = (snapshot.to_dict() or {}).get("created_at") if snapshot.exists else now
        payload = {
            "player_id": int(player_id),
            "match_id": int(match_id),
            "outcome": outcome,
            "joker": bool(joker),
            "created_at": created_at or now,
            "updated_at": now,
        }
        ref.set(payload)
        return payload

    def delete_prediction(
        self, path: Any = None, *, player_id: int, match_id: int
    ) -> None:
        self._document("predictions", self._prediction_id(player_id, match_id)).delete()

    # ---------------------------------------------------------------- settings

    def get_setting(self, path: Any = None, key: str = "") -> Any:
        snapshot = self._document("settings", key).get()
        if not snapshot.exists:
            return None
        value = (snapshot.to_dict() or {}).get("value")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def set_setting(self, path: Any = None, key: str = "", value: Any = None) -> None:
        self._document("settings", key).set({"key": key, "value": value})

    def get_scoring(self, path: Any = None) -> ScoringConfig:
        value = self.get_setting(None, "scoring")
        if value is None:
            self.set_setting(None, "scoring", DEFAULT_SCORING.to_dict())
            return DEFAULT_SCORING
        return ScoringConfig.from_mapping(value)

    def set_scoring(self, path: Any = None, config: ScoringConfig = DEFAULT_SCORING) -> ScoringConfig:
        self.set_setting(None, "scoring", config.to_dict())
        return config

    # -------------------------------------------------------------- sync state

    def get_sync_state(self, path: Any = None) -> dict[str, Any]:
        snapshot = self._document("sync_state", "current").get()
        return snapshot.to_dict() or {}

    def update_sync_state(
        self,
        path: Any = None,
        *,
        provider: str,
        attempted_at: str | None = None,
        success_at: str | None = None,
        error: str | None = None,
        matches_seen: int | None = None,
        changed: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {"provider": provider}
        if attempted_at is not None:
            payload["last_attempt_at"] = attempted_at
        if success_at is not None:
            payload["last_success_at"] = success_at
            payload["last_error"] = None
        if error is not None:
            payload["last_error"] = error
        if matches_seen is not None:
            payload["matches_seen"] = int(matches_seen)
        if changed is not None:
            payload["changed"] = int(changed)
        self._document("sync_state", "current").set(payload, merge=True)
