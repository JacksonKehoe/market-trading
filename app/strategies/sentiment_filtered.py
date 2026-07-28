"""A `Strategy` decorator: wraps any base strategy and vetoes BUY signals on bearish news sentiment.

SELL/HOLD signals pass through unchanged -- sentiment is used as a
confirmation filter on new entries only, not to block risk-driven exits
(those already go through `RiskManager.check_exits`, independent of
signals entirely).

This is a decorator, not a new strategy class per base strategy, so any
existing `Strategy` can be sentiment-filtered without modification.
"""

from __future__ import annotations

import pandas as pd

from app.models.domain import Signal
from app.models.enums import SentimentLabel, SignalType
from app.sentiment.service import SentimentService
from app.strategies.base import Strategy


class SentimentFilteredStrategy(Strategy):
    def __init__(self, base_strategy: Strategy, sentiment_service: SentimentService) -> None:
        self._base = base_strategy
        self._sentiment_service = sentiment_service

    @property
    def name(self) -> str:
        return f"{self._base.name}_sentiment"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        signal = self._base.generate_signal(symbol, data)

        if signal.signal_type != SignalType.BUY:
            return self._retag(signal)

        sentiment = self._sentiment_service.get_sentiment(symbol)
        if sentiment is not None and sentiment.label == SentimentLabel.BEARISH:
            reason = f"{signal.reason} -- vetoed by bearish news sentiment ({sentiment.score:.2f})"
            return self._hold(symbol, signal.timestamp, signal.price, reason)

        return self._retag(signal)

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
