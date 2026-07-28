"""A `Strategy` decorator: wraps any base strategy and vetoes BUY signals on bearish news sentiment.

SELL signals pass through unchanged -- sentiment is used as a
confirmation filter on new entries only, not to block risk-driven exits
(those already go through `RiskManager.check_exits`, independent of
signals entirely).

This is a decorator, not a new strategy class per base strategy, so any
existing `Strategy` can be sentiment-filtered without modification --
except the reverse case below, which needs `MovingAverageCrossoverStrategy`
specifically since "close to a buy" only has a well-defined meaning for a
crossover (the fast/slow SMA gap narrowing), not for every strategy.
"""

from __future__ import annotations

import pandas as pd

from app.models.domain import Signal
from app.models.enums import SentimentLabel, SignalType
from app.sentiment.service import SentimentService
from app.strategies.base import Strategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy


class SentimentFilteredStrategy(Strategy):
    def __init__(self, base_strategy: Strategy, sentiment_service: SentimentService) -> None:
        self._base = base_strategy
        self._sentiment_service = sentiment_service

    @property
    def name(self) -> str:
        return f"{self._base.name}_sentiment"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        signal = self._base.generate_signal(symbol, data)

        if signal.signal_type == SignalType.BUY:
            sentiment = self._sentiment_service.get_sentiment(symbol)
            if sentiment is not None and sentiment.label == SentimentLabel.BEARISH:
                reason = f"{signal.reason} -- vetoed by bearish news sentiment ({sentiment.score:.2f})"
                return self._hold(symbol, signal.timestamp, signal.price, reason)
            return self._retag(signal)

        if signal.signal_type == SignalType.HOLD and isinstance(self._base, MovingAverageCrossoverStrategy):
            early_buy = self._maybe_early_buy(symbol, data, signal)
            if early_buy is not None:
                return early_buy

        return self._retag(signal)

    def _maybe_early_buy(self, symbol: str, data: pd.DataFrame, hold_signal: Signal) -> Signal | None:
        """On strongly bullish news, pull a BUY forward a bar early if the SMA
        crossover looks imminent rather than waiting for it to actually confirm --
        the mirror image of the bearish veto above."""
        base: MovingAverageCrossoverStrategy = self._base  # type: ignore[assignment]
        if not base.near_bullish_crossover(data):
            return None

        sentiment = self._sentiment_service.get_sentiment(symbol)
        if sentiment is None or sentiment.label != SentimentLabel.BULLISH:
            return None

        reason = (
            f"{base.fast_window}-SMA nearly crossed above {base.slow_window}-SMA -- "
            f"pulled forward by bullish news sentiment ({sentiment.score:.2f})"
        )
        return Signal(symbol, SignalType.BUY, hold_signal.timestamp, hold_signal.price, self.name, reason)

    def _retag(self, signal: Signal) -> Signal:
        """Re-tag with our combined name so persistence/reports attribute the trade to
        this decorated strategy (a distinct, independently-tracked paper account),
        not to the wrapped base strategy's own name."""
        if signal.strategy_name == self.name:
            return signal
        return Signal(
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            timestamp=signal.timestamp,
            price=signal.price,
            strategy_name=self.name,
            reason=signal.reason,
        )
