from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .db import init_db, session
from .scoring import DEFAULT_SCORING, ScoringConfig
from .utils import iso_utc, safe_color, slugify, utc_now

PLAYER_COLORS = (
    "#b8f34a",
    "#5ce1e6",
    "#ffcf5a",
    "#ff7a90",
    "#a78bfa",
    "#fb923c",
    "#4ade80",
    "#f472b6",
)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def list_players(path: str | Path, active_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM players"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY active DESC, name COLLATE NOCASE"
    with session(path) as conn:
        return [dict(row) for row in conn.execute(query).fetchall()]


def get_player(path: str | Path, player_id: int) -> dict[str, Any] | None:
    with session(path) as conn:
        return _row_to_dict(
            conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        )


def create_player(
    path: str | Path, name: str, color: str | None = None
) -> dict[str, Any]:
    name = " ".join(name.strip().split())
    if not (2 <= len(name) <= 40):
        raise ValueError("Oyuncu adı 2-40 karakter arasında olmalı.")

    now = iso_utc(utc_now())
    with session(path) as conn:
        existing = conn.execute(
            "SELECT id FROM players WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if existing:
            raise ValueError("Bu isimde bir oyuncu zaten var.")

        base_slug = slugify(name)
        slug = base_slug
        suffix = 2
        while conn.execute("SELECT 1 FROM players WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        count = conn.execute("SELECT COUNT(*) AS c FROM players").fetchone()["c"]
        chosen_color = safe_color(color, PLAYER_COLORS[count % len(PLAYER_COLORS)])
        cursor = conn.execute(
            """
            INSERT INTO players (name, slug, color, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (name, slug, chosen_color, now),
        )
        player_id = int(cursor.lastrowid)
        return dict(
            conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        )


def update_player(
    path: str | Path,
    player_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        name = " ".join(name.strip().split())
        if not (2 <= len(name) <= 40):
            raise ValueError("Oyuncu adı 2-40 karakter arasında olmalı.")
        sets.append("name = ?")
        params.append(name)
    if color is not None:
        sets.append("color = ?")
        params.append(safe_color(color))
    if active is not None:
        sets.append("active = ?")
        params.append(1 if active else 0)

    if not sets:
        raise ValueError("Güncellenecek alan yok.")

    with session(path) as conn:
        if name is not None:
            duplicate = conn.execute(
                "SELECT id FROM players WHERE name = ? COLLATE NOCASE AND id != ?",
                (name, player_id),
            ).fetchone()
            if duplicate:
                raise ValueError("Bu isimde bir oyuncu zaten var.")
        params.append(player_id)
        conn.execute(f"UPDATE players SET {', '.join(sets)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
        if not row:
            raise ValueError("Oyuncu bulunamadı.")
        return dict(row)


def upsert_competition(
    path: str | Path,
    *,
    code: str,
    name: str,
    country: str | None = None,
    emblem: str | None = None,
    sort_order: int = 100,
) -> None:
    with session(path) as conn:
        conn.execute(
            """
            INSERT INTO competitions (code, name, country, emblem, sort_order)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name = excluded.name,
                country = COALESCE(excluded.country, competitions.country),
                emblem = COALESCE(excluded.emblem, competitions.emblem),
                sort_order = excluded.sort_order
            """,
            (code, name, country, emblem, sort_order),
        )


def delete_competitions_except(path: str | Path, codes: list[str] | tuple[str, ...]) -> int:
    """Remove competitions that are no longer part of the configured source list."""
    unique = sorted({code.strip().upper() for code in codes if code.strip()})
    with session(path) as conn:
        if not unique:
            cursor = conn.execute("DELETE FROM competitions")
        else:
            placeholders = ", ".join("?" for _ in unique)
            cursor = conn.execute(
                f"DELETE FROM competitions WHERE code NOT IN ({placeholders})",
                unique,
            )
        return cursor.rowcount


def list_competitions(path: str | Path) -> list[dict[str, Any]]:
    with session(path) as conn:
        rows = conn.execute(
            "SELECT * FROM competitions ORDER BY sort_order, name"
        ).fetchall()
        return [dict(row) for row in rows]


def row_to_match(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    return {
        "id": item["id"],
        "provider": item["provider"],
        "external_id": item["external_id"],
        "competition_code": item["competition_code"],
        "season": item.get("season"),
        "matchday": item.get("matchday"),
        "stage": item.get("stage"),
        "kickoff": item["kickoff_utc"],
        "status": item["status"],
        "minute": item.get("minute"),
        "home": {
            "name": item["home_name"],
            "short": item.get("home_short") or item["home_name"],
            "tla": item.get("home_tla"),
            "crest": item.get("home_crest"),
        },
        "away": {
            "name": item["away_name"],
            "short": item.get("away_short") or item["away_name"],
            "tla": item.get("away_tla"),
            "crest": item.get("away_crest"),
        },
        "score": {
            "home": item.get("home_score"),
            "away": item.get("away_score"),
        },
        "last_updated": item.get("last_updated"),
    }


def list_matches(path: str | Path) -> list[dict[str, Any]]:
    with session(path) as conn:
        rows = conn.execute("SELECT * FROM matches ORDER BY kickoff_utc").fetchall()
        return [row_to_match(row) for row in rows]


def get_match(path: str | Path, match_id: int) -> dict[str, Any] | None:
    with session(path) as conn:
        row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        return row_to_match(row) if row else None


def upsert_matches(path: str | Path, matches: Iterable[dict[str, Any]]) -> int:
    now = iso_utc(utc_now())
    changed = 0
    with session(path) as conn:
        for match in matches:
            existing = conn.execute(
                """
                SELECT id, status, home_score, away_score, kickoff_utc, last_updated,
                       home_name, away_name
                FROM matches WHERE provider = ? AND external_id = ?
                """,
                (match["provider"], str(match["external_id"])),
            ).fetchone()

            payload = (
                match["competition_code"],
                match.get("season"),
                match.get("matchday"),
                match.get("stage"),
                match["kickoff"],
                match["status"],
                match.get("minute"),
                match["home"]["name"],
                match["home"].get("short"),
                match["home"].get("tla"),
                match["home"].get("crest"),
                match["away"]["name"],
                match["away"].get("short"),
                match["away"].get("tla"),
                match["away"].get("crest"),
                match["score"].get("home"),
                match["score"].get("away"),
                match.get("last_updated"),
            )

            if existing:
                signature = (
                    existing["status"],
                    existing["home_score"],
                    existing["away_score"],
                    existing["kickoff_utc"],
                    existing["last_updated"],
                    existing["home_name"],
                    existing["away_name"],
                )
                incoming_signature = (
                    match["status"],
                    match["score"].get("home"),
                    match["score"].get("away"),
                    match["kickoff"],
                    match.get("last_updated"),
                    match["home"]["name"],
                    match["away"]["name"],
                )
                if signature == incoming_signature:
                    continue
                # Do not let a delayed provider response erase a finished result.
                if existing["status"] in {"FINISHED", "AWARDED"} and match["status"] in {
                    "SCHEDULED",
                    "TIMED",
                }:
                    continue
                conn.execute(
                    """
                    UPDATE matches SET
                        competition_code = ?, season = ?, matchday = ?, stage = ?,
                        kickoff_utc = ?, status = ?, minute = ?,
                        home_name = ?, home_short = ?, home_tla = ?, home_crest = ?,
                        away_name = ?, away_short = ?, away_tla = ?, away_crest = ?,
                        home_score = ?, away_score = ?, last_updated = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*payload, now, existing["id"]),
                )
                changed += 1
            else:
                conn.execute(
                    """
                    INSERT INTO matches (
                        provider, external_id, competition_code, season, matchday, stage,
                        kickoff_utc, status, minute,
                        home_name, home_short, home_tla, home_crest,
                        away_name, away_short, away_tla, away_crest,
                        home_score, away_score, last_updated, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider, external_id) DO NOTHING
                    """,
                    (
                        match["provider"],
                        str(match["external_id"]),
                        *payload,
                        now,
                        now,
                    ),
                )
                changed += 1
    return changed


def delete_demo_matches(path: str | Path) -> None:
    with session(path) as conn:
        demo_rows = conn.execute(
            "SELECT id FROM matches WHERE provider = 'demo'"
        ).fetchall()
        ids = [row["id"] for row in demo_rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM predictions WHERE match_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM matches WHERE id IN ({placeholders})", ids)


def delete_matches_not_in(
    path: str | Path, keys: list[tuple[str, str]] | tuple[tuple[str, str], ...]
) -> int:
    """Delete stored matches (and their predictions) that are not in ``keys``."""
    with session(path) as conn:
        if keys:
            condition = " OR ".join(
                "(provider = ? AND external_id = ?)" for _ in keys
            )
            params = [value for pair in keys for value in pair]
            stale = f"NOT ({condition})"
        else:
            params = []
            stale = "1 = 1"
        conn.execute(
            f"DELETE FROM predictions WHERE match_id IN "
            f"(SELECT id FROM matches WHERE {stale})",
            params,
        )
        cursor = conn.execute(f"DELETE FROM matches WHERE {stale}", params)
        return cursor.rowcount


def list_predictions(
    path: str | Path, match_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    with session(path) as conn:
        if match_ids is None:
            rows = conn.execute(
                "SELECT * FROM predictions ORDER BY match_id, player_id"
            ).fetchall()
        elif not match_ids:
            return []
        else:
            placeholders = ",".join("?" for _ in match_ids)
            rows = conn.execute(
                f"SELECT * FROM predictions WHERE match_id IN ({placeholders}) "
                "ORDER BY match_id, player_id",
                match_ids,
            ).fetchall()
        return [dict(row) for row in rows]


def upsert_prediction(
    path: str | Path,
    *,
    player_id: int,
    match_id: int,
    outcome: str,
    joker: bool,
) -> dict[str, Any]:
    outcome = (outcome or "").upper()
    if outcome not in {"H", "D", "A"}:
        raise ValueError("Tahmin ev sahibi, beraberlik veya deplasman olmalı.")
    now = iso_utc(utc_now())
    with session(path) as conn:
        conn.execute(
            """
            INSERT INTO predictions (
                player_id, match_id, outcome, joker, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, match_id) DO UPDATE SET
                outcome = excluded.outcome,
                joker = excluded.joker,
                updated_at = excluded.updated_at
            """,
            (player_id, match_id, outcome, 1 if joker else 0, now, now),
        )
        row = conn.execute(
            "SELECT * FROM predictions WHERE player_id = ? AND match_id = ?",
            (player_id, match_id),
        ).fetchone()
        return dict(row)


def delete_prediction(path: str | Path, *, player_id: int, match_id: int) -> None:
    with session(path) as conn:
        conn.execute(
            "DELETE FROM predictions WHERE player_id = ? AND match_id = ?",
            (player_id, match_id),
        )


def get_setting(path: str | Path, key: str) -> Any:
    with session(path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return row["value"]


def set_setting(path: str | Path, key: str, value: Any) -> None:
    with session(path) as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )


def get_scoring(path: str | Path) -> ScoringConfig:
    value = get_setting(path, "scoring")
    if value is None:
        set_setting(path, "scoring", DEFAULT_SCORING.to_dict())
        return DEFAULT_SCORING
    return ScoringConfig.from_mapping(value)


def set_scoring(path: str | Path, config: ScoringConfig) -> ScoringConfig:
    set_setting(path, "scoring", config.to_dict())
    return config


def get_sync_state(path: str | Path) -> dict[str, Any]:
    with session(path) as conn:
        row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
        return dict(row) if row else {}


def update_sync_state(
    path: str | Path,
    *,
    provider: str,
    attempted_at: str | None = None,
    success_at: str | None = None,
    error: str | None = None,
    matches_seen: int | None = None,
    changed: int | None = None,
) -> None:
    fields = ["provider = ?"]
    params: list[Any] = [provider]
    if attempted_at is not None:
        fields.append("last_attempt_at = ?")
        params.append(attempted_at)
    if success_at is not None:
        fields.append("last_success_at = ?")
        params.append(success_at)
        fields.append("last_error = NULL")
    if error is not None:
        fields.append("last_error = ?")
        params.append(error[:500])
    if matches_seen is not None:
        fields.append("matches_seen = ?")
        params.append(matches_seen)
    if changed is not None:
        fields.append("changed = ?")
        params.append(changed)
    params.append(1)
    with session(path) as conn:
        conn.execute(f"UPDATE sync_state SET {', '.join(fields)} WHERE id = ?", params)
