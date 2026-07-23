# market-trading — Paper Trading Bot

A modular, paper-trading-only stock trading platform for validating
strategies with virtual money before any real capital is ever risked.

> **This system never connects to a brokerage and never places real
> trades.** All execution happens against an in-memory/simulated
> `PaperBroker`. Live-broker support is an explicit non-goal of this
> version — the architecture is designed so it can be added later without
> touching strategy, portfolio, risk, or reporting code.

## Status

Phase 3 — market data. See [Development Phases](#development-phases).

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env         # optional — sensible defaults work with no .env at all
pytest
```

## Architecture

The system is layered so that each concern only depends on the layers
below it, and no module reaches sideways into another module's internals:

```
config, models, utils        (no internal dependencies — the shared vocabulary)
        │
        ├── data              (market data: fetch + cache)
        ├── indicators         (pure pandas/numpy functions)
        │
strategies                    (indicators + models → Signal; no I/O)
        │
portfolio, risk                (in-memory state + rule evaluation)
        │
execution                     (broker interface + PaperBroker; enforces risk, updates portfolio)
        │
database                      (SQLAlchemy persistence; converts to/from models/domain.py)
        │
reporting, email, dashboard    (read from database + portfolio; produce output)
        │
scheduler                     (top-level orchestration; wires everything together)
```

| Module | Responsibility | Depends on |
|---|---|---|
| `app/models` | Framework-free dataclasses (`Bar`, `Signal`, `Order`, `Fill`, `Position`, `Account`) and enums (`SignalType`, `OrderSide`, `OrderStatus`, `OrderType`) shared by every layer. | nothing |
| `app/config` | Loads `.env` into a single typed, immutable `Settings` object via `get_settings()`. Every other module receives settings by argument rather than reading `os.environ` itself. | nothing |
| `app/utils` | Cross-cutting helpers — currently `logging_config.py`, which wires up five rotating log files (`app`, `trades`, `errors`, `scheduler`, `market_data`). | nothing |
| `app/data` | `MarketDataProvider` interface; `YFinanceProvider` (free, no API key, US equities + ETFs); `CachedMarketDataProvider`, a decorator adding an on-disk Parquet history cache and a short-TTL in-memory latest-price cache around any provider; `load_watchlist` resolves `Settings.watchlist` into a deduplicated symbol list; `build_market_data_provider` wires the concrete (cached, yfinance-backed) stack for real use. Strategies never call a data vendor directly. | `models`, `config` |
| `app/indicators` | Pure functions (SMA/EMA, RSI, MACD) operating on `pandas` Series — no classes, no state. | nothing |
| `app/strategies` | `Strategy` interface: takes a symbol + OHLCV `DataFrame`, returns exactly one `Signal` (BUY/SELL/HOLD). Strategies know nothing about the database, the broker, or the portfolio. | `models`, `indicators` |
| `app/portfolio` | `Portfolio` — the in-memory ledger `PaperBroker` uses to simulate an account: applies fills, tracks cash/positions/realized P/L, computes equity and unrealized P/L against a price map. No DB access — persistence is a separate concern. | `models` |
| `app/risk` | `RiskLimits` (config) + `RiskManager`, which sizes and approves/rejects BUY/SELL signals against those limits, and generates forced-exit orders via `check_exits` (stop-loss/take-profit). Operates on plain `Account`/`Position` data, not a concrete broker, so it's reusable unchanged for live trading later. | `models`, `risk.rules` |
| `app/execution` | `BrokerInterface` — the seam future live brokers plug into. `PaperBroker` is the only implementation: an in-memory simulator (via `Portfolio`), no network, no credentials. `ExecutionEngine` chains signal → risk check → broker fill → optional persistence, and separately runs `RiskManager.check_exits` each cycle for stop-loss/take-profit. `TradeRepository` (a `Protocol`) is the persistence port it writes through. | `models`, `risk`, `portfolio`, `data` |
| `app/database` | SQLAlchemy engine/session bootstrap (`engine.py`); `orm_models.py` (`TradeRecord`, `PositionRecord`, `AccountSnapshotRecord`); `SqlTradeRepository`, which satisfies `execution.TradeRepository` structurally and converts to/from `app/models/domain.py`. | `models`, `config` |
| `app/reporting` | (later phase) Performance analytics (Sharpe, drawdown, CAGR, win rate, ...), backtesting, and Plotly chart generation. | `models`, `database` |
| `app/email` | (later phase) Jinja2 HTML report templates + SMTP sending, entirely optional (disabled unless `EMAIL_*` env vars are set). | `reporting` |
| `app/scheduler` | (later phase) APScheduler jobs (morning/evening/hourly) that orchestrate data refresh → strategy scan → risk-checked paper trades → report generation → optional email. | everything above |
| `app/dashboard` | (later phase) Lightweight local read-only view of portfolio/trades/signals. | `database`, `reporting` |

### Key design decisions

- **`BrokerInterface` is the extension point for live trading.** Every
  order in the system flows through this interface. `PaperBroker` is the
  only concrete implementation today; adding Alpaca/IBKR/Robinhood later
  means writing one new class, not restructuring the app.
- **Strategies are pure.** `Strategy.generate_signal(symbol, data) -> Signal`
  has no side effects, which makes strategies trivially unit-testable and
  reusable unchanged across backtesting and (paper or live) trading.
- **Domain dataclasses (`app/models`) are separate from SQLAlchemy ORM
  models.** Business logic in `portfolio`/`risk`/`execution` never imports
  SQLAlchemy; persistence is an adapter at the edge, not a dependency of
  the core logic.
- **Configuration is dependency-injected, not globally imported.**
  `get_settings()` provides a cached singleton for real usage, but every
  function/class accepts a `Settings` instance so tests can construct one
  directly with custom values — no environment-variable monkeypatching.
- **Risk enforcement is a separate module from execution.** `RiskLimits`
  is config; `RiskManager` evaluates orders against it. Splitting them
  lets risk rules be unit-tested against fabricated `Account`/`Position`
  data without a broker in the loop.
- **`RiskManager` depends on `Account`/`Position` data, not on `Portfolio`
  or `BrokerInterface` directly.** `ExecutionEngine` pulls that data out
  of `broker.get_account()`/`get_positions()` and passes it in. This
  avoids a circular dependency between `risk` and `execution`, and means
  the exact same risk logic runs against `PaperBroker` today or a live
  broker later without modification.
- **Persistence is a `Protocol`, not a concrete import.** `ExecutionEngine`
  depends on `execution.TradeRepository` (a structural `Protocol`
  defined in the execution layer, its consumer). `database.SqlTradeRepository`
  satisfies it by matching method signatures — no inheritance, and
  `ExecutionEngine` never imports SQLAlchemy. Passing `repository=None`
  runs the engine in memory only (useful for tests/backtesting).
- **`PaperBroker` fills orders immediately at the data provider's last
  price with no slippage model.** That's a deliberate simplification for
  this version — it keeps fills deterministic and easy to test. A
  slippage/latency model could be added inside `PaperBroker.submit_order`
  later without changing `BrokerInterface` or anything above it.
- **Caching wraps the provider rather than living inside it.**
  `CachedMarketDataProvider(provider, cache_dir, ttl)` decorates any
  `MarketDataProvider`, so `YFinanceProvider` stays free of caching
  concerns and the same cache works for any future data source. Only
  *completed* historical ranges (fully in the past) are cached to disk —
  a range including "today" is always fetched fresh, since today's bar
  is still forming. `yfinance` itself is injected into `YFinanceProvider`
  (defaulting to the real package), so its tests run with zero network
  access.
- **`build_market_data_provider(settings)` is the one place that decides
  the concrete data stack.** Everything above it — strategies, the
  execution engine, the backtester — depends only on `MarketDataProvider`.
  Swapping or adding a data vendor means changing this one function.

## Project layout

```
app/
├── config/       settings.py            — .env → typed Settings
├── models/       enums.py, domain.py    — shared dataclasses & enums
├── utils/        logging_config.py      — 5 rotating log files
├── data/         base.py, yfinance_provider.py, cache.py, watchlist.py, factory.py
│                                        — MarketDataProvider, YFinanceProvider,
│                                          CachedMarketDataProvider, load_watchlist
├── indicators/                          — SMA/EMA/RSI/MACD (Phase 4)
├── strategies/   base.py                — Strategy interface
├── portfolio/    portfolio.py           — Portfolio ledger (cash/positions/P&L)
├── risk/         rules.py, risk_manager.py — RiskLimits + RiskManager
├── execution/    broker_base.py, paper_broker.py, engine.py, repository.py
│                                        — BrokerInterface, PaperBroker, ExecutionEngine
├── database/     engine.py, orm_models.py, repository.py
│                                        — SQLAlchemy engine/session + SqlTradeRepository
├── reporting/                           — analytics, backtesting, charts
├── email/                               — Jinja2 templates + SMTP sender
├── scheduler/                           — APScheduler jobs
└── dashboard/                           — local read-only dashboard
database/         SQLite file + on-disk market-data cache (gitignored)
logs/             app.log, trades.log, errors.log, scheduler.log, market_data.log (gitignored)
reports/          generated HTML/chart output (gitignored)
tests/            pytest suite
```

## Configuration

All configuration lives in `.env` (see `.env.example` for the full list
with defaults: `INITIAL_CAPITAL`, `WATCHLIST`, `DATABASE_PATH`,
`EMAIL_USERNAME`/`EMAIL_PASSWORD`/`EMAIL_TO`, `MORNING_REPORT_TIME`,
`EVENING_REPORT_TIME`, risk-limit percentages, etc.). Every value has a
working default, so the app runs with no `.env` file at all.

## Development phases

1. **Architecture & skeleton** — project structure, domain
   models, config, logging, core interfaces (`Strategy`,
   `MarketDataProvider`, `BrokerInterface`), database bootstrap.
2. **Paper trading engine** — `PaperBroker`, `Portfolio`,
   `RiskManager`, `ExecutionEngine`, ORM persistence for trades/positions.
3. **Market data** *(this phase)* — `yfinance` provider + on-disk cache, watchlist loading.
4. **Strategies & indicators** — SMA/EMA/RSI/MACD, Moving Average
   Crossover / RSI / MACD strategies.
5. **Backtesting & reporting** — `run_backtest.py`, performance metrics
   (Sharpe, CAGR, drawdown, ...), equity curve + benchmark charts.
6. **Scheduler, email reports, dashboard** — morning/evening jobs, HTML
   email reports, local dashboard.

Each phase ships runnable and tested before the next begins.
