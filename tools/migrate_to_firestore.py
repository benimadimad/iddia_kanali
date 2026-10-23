"""Copy the local SQLite league database into Firestore.

Usage (from the project root):

    py tools/migrate_to_firestore.py --dry-run
    py tools/migrate_to_firestore.py
    py tools/migrate_to_firestore.py --verify

The script is idempotent: running it again updates existing documents instead of
creating duplicates. Credentials are read from FIREBASE_SERVICE_ACCOUNT
(default: secrets/firebase-service-account.json) and FIREBASE_PROJECT_ID.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from league import repository  # noqa: E402
from league.config import Config  # noqa: E402
from league.firestore_repository import FirestoreRepository, _match_key  # noqa: E402
from league.service import LeagueService  # noqa: E402

BATCH_SIZE = 400


def chunks(items: Sequence[Any], size: int = BATCH_SIZE) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def read_sqlite(path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return {
            "players": [dict(row) for row in conn.execute("SELECT * FROM players")],
            "competitions": [
                dict(row) for row in conn.execute("SELECT * FROM competitions")
            ],
            "matches": [dict(row) for row in conn.execute("SELECT * FROM matches")],
            "predictions": [
                dict(row) for row in conn.execute("SELECT * FROM predictions")
            ],
            "settings": [dict(row) for row in conn.execute("SELECT * FROM settings")],
            "sync_state": [
                dict(row) for row in conn.execute("SELECT * FROM sync_state WHERE id = 1")
            ],
        }
    finally:
        conn.close()


def write_batches(repo: FirestoreRepository, collection: str, docs: list[tuple[str, dict[str, Any]]]) -> None:
    for chunk in chunks(docs):
        batch = repo.db.batch()
        for doc_id, payload in chunk:
            batch.set(repo.db.collection(collection).document(str(doc_id)), payload)
        batch.commit()


def migrate(repo: FirestoreRepository, data: dict[str, list[dict[str, Any]]], dry_run: bool) -> None:
    player_docs = [(str(item["id"]), item) for item in data["players"]]
    competition_docs = [(str(item["code"]), item) for item in data["competitions"]]
    match_docs = [(str(item["id"]), item) for item in data["matches"]]
    prediction_docs = [
        (f"{int(item['player_id'])}_{int(item['match_id'])}", item)
        for item in data["predictions"]
    ]
    setting_docs = []
    for item in data["settings"]:
        try:
            value = json.loads(item["value"])
        except (TypeError, json.JSONDecodeError):
            value = item["value"]
        setting_docs.append((str(item["key"]), {"key": item["key"], "value": value}))

    sync_docs = []
    if data["sync_state"]:
        state = dict(data["sync_state"][0])
        state.pop("id", None)
        sync_docs.append(("current", state))

    mapping_docs = [
        (
            _match_key(str(item["provider"]), str(item["external_id"])),
            {
                "provider": str(item["provider"]),
                "external_id": str(item["external_id"]),
                "match_id": int(item["id"]),
            },
        )
        for item in data["matches"]
    ]

    counts = {
        "players": len(player_docs),
        "competitions": len(competition_docs),
        "matches": len(match_docs),
        "predictions": len(prediction_docs),
        "settings": len(setting_docs),
        "sync_state": len(sync_docs),
        "match_keys": len(mapping_docs),
    }
    print("Aktarılacak kayıtlar:", ", ".join(f"{key}={value}" for key, value in counts.items()))

    if dry_run:
        print("--dry-run: hiçbir şey yazılmadı.")
        return

    write_batches(repo, "players", player_docs)
    write_batches(repo, "competitions", competition_docs)
    write_batches(repo, "matches", match_docs)
    write_batches(repo, "match_keys", mapping_docs)
    write_batches(repo, "predictions", prediction_docs)
    write_batches(repo, "settings", setting_docs)
    write_batches(repo, "sync_state", sync_docs)

    max_player = max((int(item["id"]) for item in data["players"]), default=0)
    max_match = max((int(item["id"]) for item in data["matches"]), default=0)
    counters_ref = repo.db.collection("meta").document("counters")
    current = counters_ref.get().to_dict() or {}
    counters_ref.set(
        {
            "player": max(int(current.get("player") or 0), max_player),
            "match": max(int(current.get("match") or 0), max_match),
        },
        merge=True,
    )
    print("Aktarım tamamlandı.")


def verify(repo: FirestoreRepository, data: dict[str, list[dict[str, Any]]], source: Path) -> int:
    errors: list[str] = []

    expected = {
        "players": len(data["players"]),
        "competitions": len(data["competitions"]),
        "matches": len(data["matches"]),
        "predictions": len(data["predictions"]),
    }
    actual = {
        "players": len(repo.list_players()),
        "competitions": len(repo.list_competitions()),
        "matches": len(repo.list_matches()),
        "predictions": len(repo.list_predictions()),
    }
    for key, value in expected.items():
        status = "OK" if actual[key] == value else "HATA"
        print(f"{key}: sqlite={value} firestore={actual[key]} [{status}]")
        if actual[key] != value:
            errors.append(f"{key} sayısı uyuşmuyor")

    # Compare derived standings produced by the same service code.
    sqlite_config = Config(database_path=source)
    repository.configure(None)
    sqlite_payload = LeagueService(sqlite_config).public_payload()

    repository.configure(repo)
    firestore_payload = LeagueService(sqlite_config).public_payload()

    sqlite_rows = [(row["name"], row["points"]) for row in sqlite_payload["standings"]]
    firestore_rows = [(row["name"], row["points"]) for row in firestore_payload["standings"]]
    print("SQLite puan tablosu:   ", sqlite_rows)
    print("Firestore puan tablosu:", firestore_rows)
    if sqlite_rows != firestore_rows:
        errors.append("puan tablosu uyuşmuyor")

    for player in sqlite_payload["players"]:
        count_sqlite = sum(
            1 for match in sqlite_payload["matches"] for entry in match["predictions"]
            if entry["player_id"] == player["id"]
        )
        count_firestore = sum(
            1 for match in firestore_payload["matches"] for entry in match["predictions"]
            if entry["player_id"] == player["id"]
        )
        if count_sqlite != count_firestore:
            errors.append(f"{player['name']} tahmin sayısı uyuşmuyor")

    if errors:
        print("DOĞRULAMA BAŞARISIZ:")
        for error in errors:
            print(" -", error)
        return 1

    print("Doğrulama başarılı. Tüm kayıtlar ve puan tablosu aynı.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite verisini Firestore'a aktar.")
    parser.add_argument("--source", default=None, help="SQLite dosyası (varsayılan: data/league.db)")
    parser.add_argument("--dry-run", action="store_true", help="Sadece sayıları göster, yazma.")
    parser.add_argument("--verify", action="store_true", help="Aktarım yapmadan sadece doğrula.")
    args = parser.parse_args()

    config = Config()
    if config.data_backend != "firestore":
        print("DATA_BACKEND=firestore olmalı. Örnek:")
        print('  $env:DATA_BACKEND="firestore"; py tools/migrate_to_firestore.py')
        return 2

    source = Path(args.source) if args.source else config.database_path
    if not source.exists():
        print(f"Kaynak veritabanı bulunamadı: {source}")
        return 2

    data = read_sqlite(source)
    repo = FirestoreRepository(config)

    if args.verify:
        return verify(repo, data, source)

    migrate(repo, data, args.dry_run)
    if not args.dry_run:
        return verify(repo, data, source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
