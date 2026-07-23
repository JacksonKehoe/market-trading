from app.config.settings import Settings
from app.data.watchlist import load_watchlist


def test_load_watchlist_uppercases_and_strips() -> None:
    settings = Settings(watchlist=[" aapl", "msft "])
    assert load_watchlist(settings) == ["AAPL", "MSFT"]


def test_load_watchlist_deduplicates_preserving_order() -> None:
    settings = Settings(watchlist=["AAPL", "MSFT", "aapl"])
    assert load_watchlist(settings) == ["AAPL", "MSFT"]


def test_load_watchlist_drops_blank_entries() -> None:
    settings = Settings(watchlist=["AAPL", "  ", "MSFT"])
    assert load_watchlist(settings) == ["AAPL", "MSFT"]
