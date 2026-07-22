"""Risk limit configuration.

`RiskLimits` is pure data — it holds the configurable guardrails described
in the spec. The `RiskManager` that *enforces* these rules against orders
belongs to the execution phase (Phase 2), since enforcement needs the
current portfolio state to evaluate against. Keeping the limits themselves
in a standalone dataclass lets them be constructed from `Settings`, from a
backtest config, or from a unit test fixture equally easily.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Configurable guardrails enforced by the execution engine."""

    max_position_size_pct: float
    """Max fraction of total equity a single position may represent."""

    max_portfolio_allocation_pct: float
    """Max fraction of total equity allowed to be invested at once."""

    stop_loss_pct: float | None
    """Fractional loss (from entry) at which a position is auto-closed."""

    take_profit_pct: float | None
    """Fractional gain (from entry) at which a position is auto-closed."""

    daily_loss_limit_pct: float | None
    """Max fraction of equity the account may lose in a single day before trading halts."""

    max_open_positions: int
    """Max number of distinct symbols held concurrently."""

    @classmethod
    def from_settings(cls, settings: Settings) -> "RiskLimits":
        return cls(
            max_position_size_pct=settings.max_position_size_pct,
            max_portfolio_allocation_pct=settings.max_portfolio_allocation_pct,
            stop_loss_pct=settings.stop_loss_pct,
            take_profit_pct=settings.take_profit_pct,
            daily_loss_limit_pct=settings.daily_loss_limit_pct,
            max_open_positions=settings.max_open_positions,
        )
