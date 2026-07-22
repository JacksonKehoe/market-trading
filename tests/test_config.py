from pathlib import Path

from app.config.settings import Settings, _split_watchlist


def test_default_settings_construct_without_env() -> None:
    settings = Settings()
    assert settings.initial_capital == 100_000.0
    assert "AAPL" in settings.watchlist
    assert settings.database_url.startswith("sqlite:///")


def test_split_watchlist_normalizes_symbols() -> None:
    assert _split_watchlist(" aapl, msft ,, spy") == ["AAPL", "MSFT", "SPY"]


def test_email_enabled_requires_all_three_fields() -> None:
    assert not Settings(email_username="me@example.com").email_enabled
    assert Settings(
        email_username="me@example.com",
        email_password="secret",
        email_to="dest@example.com",
    ).email_enabled


def test_paths_are_path_objects() -> None:
    settings = Settings()
    assert isinstance(settings.database_path, Path)
    assert isinstance(settings.logs_dir, Path)
