"""Enumerations shared across every layer of the application.

Keeping these in one dependency-free module lets any layer (strategies,
execution, reporting, ...) speak the same vocabulary without importing
each other.
"""

from __future__ import annotations

from enum import Enum


class SignalType(str, Enum):
    """The only three outputs a strategy is allowed to produce."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SentimentLabel(str, Enum):
    """Coarse sentiment classification for a symbol's recent news headlines."""

    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
