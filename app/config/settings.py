"""Centralized application configuration.

All configuration is read from environment variables (populated from a
.env file via python-dotenv). Every other module receives a `Settings`
instance through a function argument or constructor rather than reading
`os.environ` itself — this keeps modules testable (tests can construct a
`Settings` object directly with whatever values they need) and keeps
configuration parsing in exactly one place.

Use `get_settings()` to obtain the process-wide singleton.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _split_watchlist(raw: str) -> list[str]:
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def _split_strategies(raw: str) -> list[str]:
    return [name.strip().lower() for name in raw.split(",") if name.strip()]


def _bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable, typed view over the application's environment variables."""

    # Paper trading account
    initial_capital: float = 100_000.0
    watchlist: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "SPY"])

    # Persistence / filesystem locations
    database_path: Path = PROJECT_ROOT / "database" / "trading_bot.db"
    logs_dir: Path = PROJECT_ROOT / "logs"
    reports_dir: Path = PROJECT_ROOT / "reports"
    cache_dir: Path = PROJECT_ROOT / "database" / "cache"
    latest_price_cache_ttl_seconds: float = 60.0

    # Email (all optional — reports are only emailed if these are set)
    email_username: str = ""
    email_password: str = ""
    email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    # Scheduler
    morning_report_time: str = "08:00"
    evening_report_time: str = "17:30"
    hourly_scan_enabled: bool = False

    # Risk defaults (can be overridden per-strategy later)
    max_position_size_pct: float = 0.10
    max_portfolio_allocation_pct: float = 1.0
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    daily_loss_limit_pct: float = 0.03
    max_open_positions: int = 10

    # Simulated trading costs
    commission_per_trade: float = 0.0

    # Live/scheduled paper trading
    strategies: list[str] = field(default_factory=lambda: ["sma", "rsi", "macd"])
    """Which Strategies the scheduler/dashboard run, by name (see app.strategies.factory).

    Each one gets its own independent simulated account (same starting
    capital, same watchlist) so their results are directly comparable --
    not one account split across strategies.
    """

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_username and self.email_password and self.email_to)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings from `.env` (once) and return the cached singleton.

    `lru_cache` gives us a process-wide singleton without a manual global,
    while `Settings.__init__` still works standalone for tests that want a
    throwaway instance with custom values.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    return Settings(
        initial_capital=float(os.getenv("INITIAL_CAPITAL", "100000")),
        watchlist=_split_watchlist(os.getenv("WATCHLIST", "AAPL,MSFT,SPY")),
        database_path=Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "database" / "trading_bot.db"))),
        logs_dir=Path(os.getenv("LOGS_DIR", str(PROJECT_ROOT / "logs"))),
        reports_dir=Path(os.getenv("REPORTS_DIR", str(PROJECT_ROOT / "reports"))),
        cache_dir=Path(os.getenv("CACHE_DIR", str(PROJECT_ROOT / "database" / "cache"))),
        latest_price_cache_ttl_seconds=float(os.getenv("LATEST_PRICE_CACHE_TTL_SECONDS", "60.0")),
        email_username=os.getenv("EMAIL_USERNAME", ""),
        email_password=os.getenv("EMAIL_PASSWORD", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        morning_report_time=os.getenv("MORNING_REPORT_TIME", "09:00"),
        evening_report_time=os.getenv("EVENING_REPORT_TIME", "17:30"),
        hourly_scan_enabled=_bool(os.getenv("HOURLY_SCAN_ENABLED", "false")),
        max_position_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", "0.10")),
        max_portfolio_allocation_pct=float(os.getenv("MAX_PORTFOLIO_ALLOCATION_PCT", "1.0")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.05")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.10")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.03")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "10")),
        commission_per_trade=float(os.getenv("COMMISSION_PER_TRADE", "0.0")),
        strategies=_split_strategies(os.getenv("STRATEGIES", os.getenv("STRATEGY", "sma,rsi,macd"))),
    )
