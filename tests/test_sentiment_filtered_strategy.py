from datetime import UTC, datetime

from app.models.domain import SentimentScore
from app.models.enums import SentimentLabel, SignalType
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.sentiment_filtered import SentimentFilteredStrategy
from tests.conftest import make_price_frame


class _FixedSentimentService:
    def __init__(self, label: SentimentLabel | None) -> None:
        self._label = label

    def get_sentiment(self, symbol: str) -> SentimentScore | None:
        if self._label is None:
            return None
        return SentimentScore(symbol=symbol, label=self._label, score=0.0, headline_count=3, timestamp=datetime.now(UTC))


def _crossing_data():
    """fast=2/slow=3 SMA crosses up on the very last bar -- see test_scheduler_jobs.py for the same pattern."""
    return make_price_frame([5.0, 4.0, 3.0, 2.0, 10.0])


def _near_crossing_data():
    """fast=3/slow=6: a dip followed by a partial recovery that closes most of the
    gap without actually crossing -- see test_strategy_moving_average_crossover.py
    for the same pattern verified directly against `near_bullish_crossover`."""
    return make_price_frame([10.0, 10.0, 10.0, 9.0, 9.0, 9.0, 10.15])


def test_buy_signal_passes_through_on_bullish_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BULLISH))

    signal = strategy.generate_signal("AAPL", _crossing_data())

    assert signal.signal_type == SignalType.BUY
    assert signal.strategy_name == strategy.name


def test_buy_signal_passes_through_on_neutral_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.NEUTRAL))

    signal = strategy.generate_signal("AAPL", _crossing_data())

    assert signal.signal_type == SignalType.BUY


def test_buy_signal_is_vetoed_to_hold_on_bearish_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BEARISH))

    signal = strategy.generate_signal("AAPL", _crossing_data())

    assert signal.signal_type == SignalType.HOLD
    assert "bearish" in signal.reason.lower()
    assert signal.strategy_name == strategy.name


def test_buy_signal_passes_through_when_sentiment_unavailable() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(None))

    signal = strategy.generate_signal("AAPL", _crossing_data())

    assert signal.signal_type == SignalType.BUY


def test_hold_signal_passes_through_unaffected_by_bearish_sentiment() -> None:
    # Flat/insufficient-history data -> base strategy HOLDs; sentiment should never be consulted for non-BUY signals.
    base = MovingAverageCrossoverStrategy(fast_window=20, slow_window=50)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BEARISH))

    signal = strategy.generate_signal("AAPL", make_price_frame([100.0, 101.0, 102.0]))

    assert signal.signal_type == SignalType.HOLD
    assert "bearish" not in signal.reason.lower()
    assert signal.strategy_name == strategy.name


def test_sell_signal_passes_through_unaffected_by_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BEARISH))

    # Mirror of the crossing-up data: crosses down on the last bar -> SELL.
    signal = strategy.generate_signal("AAPL", make_price_frame([2.0, 3.0, 4.0, 5.0, 0.5]))

    assert signal.signal_type == SignalType.SELL
    assert signal.strategy_name == strategy.name


def test_name_combines_base_strategy_name() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=10, slow_window=30)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(None))

    assert strategy.name == "sma_crossover_10_30_sentiment"


def test_hold_is_pulled_forward_to_buy_on_near_crossover_with_bullish_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BULLISH))

    signal = strategy.generate_signal("AAPL", _near_crossing_data())

    assert signal.signal_type == SignalType.BUY
    assert signal.strategy_name == strategy.name
    assert "bullish" in signal.reason.lower()


def test_hold_is_not_pulled_forward_on_near_crossover_with_neutral_sentiment() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.NEUTRAL))

    signal = strategy.generate_signal("AAPL", _near_crossing_data())

    assert signal.signal_type == SignalType.HOLD


def test_hold_is_not_pulled_forward_on_near_crossover_when_sentiment_unavailable() -> None:
    base = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(None))

    signal = strategy.generate_signal("AAPL", _near_crossing_data())

    assert signal.signal_type == SignalType.HOLD


def test_hold_is_not_pulled_forward_when_gap_still_wide_even_with_bullish_sentiment() -> None:
    # Same dip, much smaller recovery -- near_bullish_crossover is False, so no upgrade.
    base = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BULLISH))
    data = make_price_frame([10.0, 10.0, 10.0, 9.0, 9.0, 9.0, 9.3])

    signal = strategy.generate_signal("AAPL", data)

    assert signal.signal_type == SignalType.HOLD


def test_bullish_sentiment_does_not_affect_a_strategy_without_near_crossover_support() -> None:
    """Base strategies other than MovingAverageCrossoverStrategy don't define
    "close to a buy", so the reverse logic must never fire for them."""
    from app.strategies.rsi_strategy import RsiStrategy

    base = RsiStrategy()
    strategy = SentimentFilteredStrategy(base, _FixedSentimentService(SentimentLabel.BULLISH))

    signal = strategy.generate_signal("AAPL", make_price_frame([100.0, 101.0, 102.0]))

    assert signal.signal_type == SignalType.HOLD
