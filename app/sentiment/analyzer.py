"""Scores headline text for sentiment — free and local, no LLM/API calls.

Uses VADER (Valence Aware Dictionary and sEntiment Reasoner), a
rule-based lexicon scorer tuned for short, informal text like headlines
and social media. It's not as nuanced as an LLM judge, but it's free,
runs locally with no API key or network call, and is fast enough to
score a whole watchlist on every scan.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.models.domain import SentimentScore
from app.models.enums import SentimentLabel

_BULLISH_THRESHOLD = 0.05
_BEARISH_THRESHOLD = -0.05
"""VADER's own documented convention: compound >= 0.05 is positive, <= -0.05 is negative."""


class SentimentAnalyzer(ABC):
    @abstractmethod
    def analyze(self, symbol: str, headlines: list[str]) -> SentimentScore:
        raise NotImplementedError


class VaderSentimentAnalyzer(SentimentAnalyzer):
    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        self._analyzer = SentimentIntensityAnalyzer()

    def analyze(self, symbol: str, headlines: list[str]) -> SentimentScore:
        if not headlines:
            return SentimentScore(
                symbol=symbol,
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                headline_count=0,
                timestamp=datetime.now(UTC),
            )

        compound_scores = [self._analyzer.polarity_scores(headline)["compound"] for headline in headlines]
        average = sum(compound_scores) / len(compound_scores)

        if average >= _BULLISH_THRESHOLD:
            label = SentimentLabel.BULLISH
        elif average <= _BEARISH_THRESHOLD:
            label = SentimentLabel.BEARISH
        else:
            label = SentimentLabel.NEUTRAL

        return SentimentScore(
            symbol=symbol,
            label=label,
            score=average,
            headline_count=len(headlines),
            timestamp=datetime.now(UTC),
        )
