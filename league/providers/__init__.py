from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Config


class ProviderError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    matches: list[dict[str, Any]] = field(default_factory=list)
    competitions: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = True


def fetch_provider_data(config: Config, date_from: str, date_to: str) -> ProviderResult:
    if config.provider == "demo":
        return ProviderResult()
    if config.provider == "tracked":
        from .tracked import TrackedProvider

        return TrackedProvider(config).fetch(date_from, date_to)
    from .football_data import FootballDataProvider

    return FootballDataProvider(config).fetch(date_from, date_to)
