"""Storage facade.

The application talks to this module instead of a concrete database. By default
it uses SQLite (``sqlite_repository``). When ``DATA_BACKEND=firestore`` the
bootstrap configures a Firestore backend and every call is delegated there.

Both backends share the same function signatures and return plain dictionaries,
so services, routes and tools stay database agnostic.
"""

from __future__ import annotations

from typing import Any

from . import sqlite_repository

_backend: Any = None


def configure(backend: Any = None) -> None:
    """Select the active backend. ``None`` restores the SQLite default."""
    global _backend
    _backend = backend


def configure_from_config(config: Any) -> None:
    """Pick the backend declared by the application configuration."""
    if getattr(config, "data_backend", "sqlite") == "firestore":
        from .firestore_repository import FirestoreRepository

        configure(FirestoreRepository(config))
    else:
        configure(None)


def current_backend() -> Any:
    return _backend


def __getattr__(name: str) -> Any:
    # Module level fallback keeps the public API identical for both backends.
    if _backend is not None:
        return getattr(_backend, name)
    return getattr(sqlite_repository, name)
