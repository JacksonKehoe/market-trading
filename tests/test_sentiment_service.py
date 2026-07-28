import time
from datetime import UTC, datetime

from app.models.domain import SentimentScore
from app.models.enums import SentimentLabel
from app.sentiment.service import SentimentService


class _CountingProvider:
    def __init__(self, headlines: list[str]) -> None:
        self._headlines = headlines
        self.calls = 0

    def get_headlines(self, symbol: str, limit: int = 10) -> list[str]:
        self.calls += 1
        return self._headlines


class _FixedAnalyzer:
    def __init__(self, label: SentimentLabel = SentimentLabel.NEUTRAL) -> None:
        self.label = label
        self.calls = 0

    def analyze(self, symbol: str, headlines: list[str]) -> SentimentScore:
        self.calls += 1
        return SentimentScore(
            symbol=symbol, label=self.label, score=0.0, headline_count=len(headlines), timestamp=datetime.now(UTC)
        )


class _FailingProvider:
    def get_headlines(self, symbol: str, limit: int = 10) -> list[str]:
        raise ConnectionError("network down")


def test_get_sentiment_returns_analyzer_result() -> None:
    provider = _CountingProvider(["headline one"])
    analyzer = _FixedAnalyzer(SentimentLabel.BULLISH)
    service = SentimentService(provider, analyzer)

    result = service.get_sentiment("AAPL")

    assert result is not None
    assert result.label == SentimentLabel.BULLISH
    assert result.symbol == "AAPL"


def test_get_sentiment_is_cached_within_ttl() -> None:
    provider = _CountingProvider(["headline one"])
    analyzer = _FixedAnalyzer()
    service = SentimentService(provider, analyzer, cache_ttl_seconds=60)

    service.get_sentiment("AAPL")
    service.get_sentiment("AAPL")

    assert provider.calls == 1
    assert analyzer.calls == 1


def test_get_sentiment_refetches_after_ttl_expires() -> None:
    provider = _CountingProvider(["headline one"])
    analyzer = _FixedAnalyzer()
    service = SentimentService(provider, analyzer, cache_ttl_seconds=0.01)

    service.get_sentiment("AAPL")
    time.sleep(0.02)
    service.get_sentiment("AAPL")

    assert provider.calls == 2


def test_cache_is_independent_per_symbol() -> None:
    provider = _CountingProvider(["headline one"])
    analyzer = _FixedAnalyzer()
    service = SentimentService(provider, analyzer, cache_ttl_seconds=60)

    service.get_sentiment("AAPL")
    service.get_sentiment("MSFT")

    assert provider.calls == 2


def test_get_sentiment_returns_none_when_provider_fails() -> None:
    service = SentimentService(_FailingProvider(), _FixedAnalyzer())

    result = service.get_sentiment("AAPL")

    assert result is None


def test_headline_limit_is_passed_to_provider() -> None:
    captured_limits = []

    class _CapturingProvider:
        def get_headlines(self, symbol: str, limit: int = 10) -> list[str]:
            captured_limits.append(limit)
            return []

    service = SentimentService(_CapturingProvider(), _FixedAnalyzer(), headline_limit=5)
    service.get_sentiment("AAPL")

    assert captured_limits == [5]
