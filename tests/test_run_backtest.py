from pathlib import Path

import pytest

import run_backtest
from app.config.settings import Settings
from tests.conftest import FakeHistoricalMarketDataProvider, make_price_frame


@pytest.fixture
def fake_provider() -> FakeHistoricalMarketDataProvider:
    data = make_price_frame([100.0 + i for i in range(40)], start="2026-01-01")
    return FakeHistoricalMarketDataProvider({"AAPL": data})


def test_main_runs_backtest_and_writes_report(tmp_path: Path, monkeypatch, capsys, fake_provider) -> None:
    monkeypatch.setattr(run_backtest, "build_market_data_provider", lambda settings: fake_provider)
    settings = Settings(reports_dir=tmp_path, logs_dir=tmp_path / "logs", watchlist=["AAPL"])

    exit_code = run_backtest.main(
        [
            "--symbols", "AAPL",
            "--strategy", "sma",
            "--start", "2026-01-01",
            "--end", "2026-02-09",
            "--benchmark", "",
        ],
        settings=settings,
    )

    assert exit_code == 0
    reports = list(tmp_path.glob("backtest_*.html"))
    assert len(reports) == 1

    captured = capsys.readouterr()
    assert "Backtest:" in captured.out
    assert "Report saved to:" in captured.out


def test_main_defaults_symbols_to_watchlist_when_not_specified(
    tmp_path: Path, monkeypatch, fake_provider
) -> None:
    monkeypatch.setattr(run_backtest, "build_market_data_provider", lambda settings: fake_provider)
    settings = Settings(reports_dir=tmp_path, logs_dir=tmp_path / "logs", watchlist=["AAPL"])

    exit_code = run_backtest.main(
        ["--start", "2026-01-01", "--end", "2026-02-09", "--benchmark", ""], settings=settings
    )

    assert exit_code == 0
    assert list(tmp_path.glob("backtest_*.html"))


def test_main_returns_error_code_for_empty_symbols(tmp_path: Path, monkeypatch, fake_provider) -> None:
    monkeypatch.setattr(run_backtest, "build_market_data_provider", lambda settings: fake_provider)
    settings = Settings(reports_dir=tmp_path, logs_dir=tmp_path / "logs", watchlist=[])

    exit_code = run_backtest.main(["--symbols", "", "--benchmark", ""], settings=settings)

    assert exit_code == 1
