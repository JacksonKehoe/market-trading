# market-trading — Paper Trading Bot

A modular, paper-trading-only stock trading platform for validating
strategies with virtual money before any real capital is ever risked.

> **This system never connects to a brokerage and never places real
> trades.** All execution happens against an in-memory/simulated
> `PaperBroker`. Live-broker support is an explicit non-goal of this
> version — the architecture is designed so it can be added later without
> touching strategy, portfolio, risk, or reporting code.

## Status

Phase 1 — architecture and project skeleton. See [Development Phases](#development-phases).

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
| `app/data` | `MarketDataProvider` interface plus (Phase 3) a `yfinance`-backed implementation and a local cache, so strategies never call a data vendor directly. | `models` |
| `app/indicators` | Pure functions (SMA/EMA, RSI, MACD) operating on `pandas` Series — no classes, no state. | nothing |
| `app/strategies` | `Strategy` interface: takes a symbol + OHLCV `DataFrame`, returns exactly one `Signal` (BUY/SELL/HOLD). Strategies know nothing about the database, the broker, or the portfolio. | `models`, `indicators` |
| `app/portfolio` | (Phase 2) In-memory portfolio state: cash, positions, realized/unrealized P/L. No DB access — persistence is a separate concern. | `models` |
| `app/risk` | `RiskLimits` (config) now; `RiskManager` (Phase 2) evaluates proposed orders against those limits before they reach a broker. | `models`, `config` |
| `app/execution` | `BrokerInterface` — the seam future live brokers plug into. `PaperBroker` (Phase 2) is the only implementation for now: an in-memory simulator, no network, no credentials. An `ExecutionEngine` (Phase 2) will chain strategy → risk check → broker. | `models`, `risk`, `portfolio` |
| `app/database` | SQLAlchemy engine/session bootstrap (`engine.py`) now; ORM models and repositories arrive in Phase 2 to persist trades/positions/snapshots, translating to/from `app/models/domain.py`. | `models`, `config` |
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
  is config; the forthcoming `RiskManager` evaluates orders against it.
  Splitting them lets risk rules be unit-tested against fabricated
  portfolios without a broker in the loop.

## Project layout

```
app/
├── config/       settings.py            — .env → typed Settings
├── models/       enums.py, domain.py    — shared dataclasses & enums
├── utils/        logging_config.py      — 5 rotating log files
├── data/         base.py                — MarketDataProvider interface
├── indicators/                          — SMA/EMA/RSI/MACD (Phase 4)
├── strategies/   base.py                — Strategy interface
├── portfolio/                           — portfolio state (Phase 2)
├── risk/         rules.py               — RiskLimits config
├── execution/    broker_base.py         — BrokerInterface + PaperBroker (Phase 2)
├── database/     engine.py              — SQLAlchemy engine/session
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

1. **Architecture & skeleton** *(this phase)* — project structure, domain
   models, config, logging, core interfaces (`Strategy`,
   `MarketDataProvider`, `BrokerInterface`), database bootstrap.
2. **Paper trading engine** — `PaperBroker`, `Portfolio`, `RiskManager`,
   `ExecutionEngine`, ORM persistence for trades/positions.
3. **Market data** — `yfinance` provider + on-disk cache, watchlist loading.
4. **Strategies & indicators** — SMA/EMA/RSI/MACD, Moving Average
   Crossover / RSI / MACD strategies.
5. **Backtesting & reporting** — `run_backtest.py`, performance metrics
   (Sharpe, CAGR, drawdown, ...), equity curve + benchmark charts.
6. **Scheduler, email reports, dashboard** — morning/evening jobs, HTML
   email reports, local dashboard.

Each phase ships runnable and tested before the next begins.
