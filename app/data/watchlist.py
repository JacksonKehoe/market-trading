"""Watchlist loading.

The watchlist is configured via `Settings.watchlist` (the `WATCHLIST` env
var). This module is the single place that resolves it into the final
symbol list, so it can grow later (e.g. merging in a file- or
database-backed list) without every caller needing to know where the
symbols came from.
"""

from __future__ import annotations

from app.config.settings import Settings


def load_watchlist(settings: Settings) -> list[str]:
    """Return the configured watchlist symbols, deduplicated and uppercased."""
    seen: dict[str, None] = {}
    for symbol in settings.watchlist:
        normalized = symbol.strip().upper()
        if normalized:
            seen.setdefault(normalized, None)
    return list(seen)
