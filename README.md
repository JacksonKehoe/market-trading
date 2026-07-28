# market-trading — Paper Trading Bot

A modular, paper-trading-only stock trading platform for validating
strategies with virtual money before any real capital is ever risked.

> **This system never connects to a brokerage and never places real
> trades.** All execution happens against an in-memory/simulated
> `PaperBroker`. Live-broker support is an explicit non-goal of this
> version — the architecture is designed so it can be added later without
> touching strategy, portfolio, risk, or reporting code.

## Status

Phase 6 — scheduler, email reports, dashboard. All six planned phases are complete. See [Development Phases](#development-phases).

**Multi-strategy comparison:** the scheduler, email reports, and dashboard
run every strategy listed in `STRATEGIES` (default `sma,rsi,macd`)
simultaneously, each in its own independent simulated account with the
same starting capital and the same watchlist — not one account split
across strategies. This makes their results directly comparable: the
dashboard and both email reports lead with a strategy comparison table
and a combined equity-curve chart (one line per strategy).

**News sentiment (branch: `feature/sentiment-analysis`):** an optional
fourth strategy, `sma_sentiment`, scrapes recent news headlines and
vetoes SMA-crossover BUY signals when sentiment is bearish. Free and
local — scraped from Google News' RSS feed and scored with VADER, no
LLM/API key/cost involved. Opt in by adding `sma_sentiment` to
`STRATEGIES`; it then shows up in the dashboard/reports comparison like
any other strategy with no other changes needed.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env         # optional — sensible defaults work with no .env at all
pytest

python run_backtest.py --symbols AAPL,MSFT --strategy sma --start 2024-01-01 --end 2025-06-01 --benchmark SPY

python run_scheduler.py    # runs morning/evening (+ optional hourly) paper-trading jobs on a schedule
python run_dashboard.py    # local read-only dashboard at http://127.0.0.1:5000
```

- `run_backtest.py` fetches real historical data (via `yfinance`), replays
  the chosen strategy (`sma` / `rsi` / `macd`) through the paper trading
  engine, prints a performance summary, and saves a self-contained HTML
  report to `reports/`.
- `run_scheduler.py` starts a long-running process that scans the
  watchlist and places simulated trades — for *every* strategy in
  `STRATEGIES`, each its own account — at the times configured by
  `MORNING_REPORT_TIME`/`EVENING_REPORT_TIME` (plus an optional hourly
  scan), saving one combined comparison HTML report to `reports/` and
  emailing it if `EMAIL_*` is configured. Each strategy's paper trading
  state (cash/positions) persists in the SQLite database, scoped by
  strategy, and is restored automatically if the process restarts.
- `run_dashboard.py` starts a local Flask server (bound to
  `127.0.0.1` only) showing a live comparison across all configured
  strategies — portfolio value, holdings, strategy signals, risk
  metrics, and recent transactions, read straight from the database. It
  never places a trade.

None of these ever connect to a brokerage or place a real trade.

## Architecture

The system is layered so that each concern only depends on the layers
below it, and no module reaches sideways into another module's internals:

```
config, models, utils        (no internal dependencies — the shared vocabulary)
        │
        ├── data              (market data: fetch + cache)
        ├── indicators         (pure pandas/numpy functions)
        ├── sentiment           (scraped headlines → SentimentScore; free, local)
        │
strategies                    (indicators + models → Signal; no I/O;
                                SentimentFilteredStrategy also uses sentiment)
        │
portfolio, risk                (in-memory state + rule evaluation)
        │
execution                     (broker interface + PaperBroker; enforces risk, updates portfolio)
        │
database                      (SQLAlchemy persistence; converts to/from models/domain.py)
        │
reporting                     (backtester replays strategies through execution;
        │                       + analytics, charts, HTML reports)
        │
email, dashboard               (live account/report data -> HTML; email is
        │                       optional, dashboard is read-only)
        │
scheduler                     (top-level orchestration: builds the live
                                TradingContext, runs jobs on a schedule)
```

`reporting` sits above `execution` for a specific reason: its `Backtester`
doesn't reimplement trading logic, it *replays* historical data through
the real `PaperBroker`/`RiskManager`/`ExecutionEngine` — so it necessarily
depends on everything below it (`data`, `strategies`, `portfolio`, `risk`,
`execution`), not just `models`/`database` as earlier phases anticipated.
`email` and `dashboard` similarly need broad read access to *live* state
(a real `BrokerInterface`, `MarketDataProvider`, `SqlTradeRepository`) to
show current positions and today's signals — but neither imports
`app.scheduler`, which assembles that live state and sits strictly above
both. `app.scheduler.context.TradingContext` is the one place that bundles
broker + engine + repository + strategy + watchlist together; `email`'s
functions take those pieces as plain parameters instead, so the dependency
only points one way.

| Module | Responsibility | Depends on |
|---|---|---|
| `app/models` | Framework-free dataclasses (`Bar`, `Signal`, `Order`, `Fill`, `Position`, `Account`) and enums (`SignalType`, `OrderSide`, `OrderStatus`, `OrderType`) shared by every layer. | nothing |
| `app/config` | Loads `.env` into a single typed, immutable `Settings` object via `get_settings()`. Every other module receives settings by argument rather than reading `os.environ` itself. | nothing |
| `app/utils` | Cross-cutting helpers — currently `logging_config.py`, which wires up five rotating log files (`app`, `trades`, `errors`, `scheduler`, `market_data`). | nothing |
| `app/data` | `MarketDataProvider` interface; `YFinanceProvider` (free, no API key, US equities + ETFs); `CachedMarketDataProvider`, a decorator adding an on-disk Parquet history cache and a short-TTL in-memory latest-price cache around any provider; `load_watchlist` resolves `Settings.watchlist` into a deduplicated symbol list; `build_market_data_provider` wires the concrete (cached, yfinance-backed) stack for real use. Strategies never call a data vendor directly. | `models`, `config` |
| `app/indicators` | Pure functions operating on `pandas` Series — no classes, no state: `sma`/`ema`, `rsi` (Wilder's smoothing), `macd` (returns a `macd`/`signal`/`histogram` DataFrame). `NaN` during warm-up instead of a misleadingly early value. | nothing |
| `app/sentiment` | `NewsProvider` interface; `GoogleNewsRssProvider` scrapes Google News' public RSS search feed for a symbol (real server-rendered XML, not a JS-rendered page — no headless browser needed). `SentimentAnalyzer` interface; `VaderSentimentAnalyzer` scores headlines with VADER, a free local rule-based lexicon scorer (no LLM, no API key, no cost). `SentimentService` wraps both behind a TTL cache (mirrors `CachedMarketDataProvider`'s pattern) and swallows scraping/scoring failures, returning `None` ("unknown") rather than raising. `build_sentiment_service(settings)` wires the concrete stack. | `models`, `config` |
| `app/strategies` | `Strategy` interface: takes a symbol + OHLCV `DataFrame`, returns exactly one `Signal` (BUY/SELL/HOLD), plus a shared `_hold()` helper for the common "not enough history" case. Three base implementations: `MovingAverageCrossoverStrategy`, `RsiStrategy` (oversold/overbought bounce), `MacdStrategy` — all edge-triggered (fire once on the actual cross, not every bar the condition holds). `SentimentFilteredStrategy` is a decorator wrapping any base `Strategy` + a `SentimentService`, downgrading BUY to HOLD when news sentiment is bearish; registered in `factory.py` as `sma_sentiment`. Strategies know nothing about the database, the broker, or the portfolio. | `models`, `indicators`, `sentiment` (only for the decorator) |
| `app/portfolio` | `Portfolio` — the in-memory ledger `PaperBroker` uses to simulate an account: applies fills, tracks cash/positions/realized P/L, computes equity and unrealized P/L against a price map. No DB access — persistence is a separate concern. | `models` |
| `app/risk` | `RiskLimits` (config) + `RiskManager`, which sizes and approves/rejects BUY/SELL signals against those limits, and generates forced-exit orders via `check_exits` (stop-loss/take-profit). Operates on plain `Account`/`Position` data, not a concrete broker, so it's reusable unchanged for live trading later. | `models`, `risk.rules` |
| `app/execution` | `BrokerInterface` — the seam future live brokers plug into. `PaperBroker` is the only implementation: an in-memory simulator (via `Portfolio`), no network, no credentials. `ExecutionEngine` chains signal → risk check → broker fill → optional persistence, and separately runs `RiskManager.check_exits` each cycle for stop-loss/take-profit. `TradeRepository` (a `Protocol`) is the persistence port it writes through. | `models`, `risk`, `portfolio`, `data` |
| `app/database` | SQLAlchemy engine/session bootstrap (`engine.py`); `orm_models.py` (`TradeRecord`, `PositionRecord`, `AccountSnapshotRecord` — positions and snapshots are scoped by `strategy_name`, since each strategy trades its own independent account); `SqlTradeRepository`, which satisfies `execution.TradeRepository` structurally and converts to/from `app/models/domain.py`. | `models`, `config` |
| `app/reporting` | `Backtester` replays a `Strategy` across a watchlist and date range through the *real* `PaperBroker`/`RiskManager`/`ExecutionEngine` via `ReplayMarketDataProvider` (serves data "as of" a simulated date so nothing can see the future) — a backtest is the live paper-trading pipeline fed historical bars, not a separate simulation. `metrics.py` computes total return, CAGR, Sharpe, max drawdown, win rate, average gain/loss, profit factor, and expectancy from an equity curve + trade list (`compute_trade_pnl` reconstructs per-trade realized P&L by replaying fills through a scratch `Portfolio`). `charts.py` builds Plotly equity-curve and drawdown figures; `report_generator.py` renders them into a self-contained HTML file via Jinja2 and saves it to `reports/`. | `models`, `data`, `strategies`, `portfolio`, `risk`, `execution`, `database` |
| `app/email` | `report_data.py` builds the morning/evening report context — a per-strategy comparison table plus combined positions/signals/trades/risk tables (each row tagged with a `strategy` column) and, for the evening report, a combined equity-curve series per strategy — from a list of `StrategyState` (name + live `BrokerInterface` + signals), plus shared `MarketDataProvider`/`SqlTradeRepository`. `renderer.py` turns that into HTML via Jinja2, building a multi-line Plotly equity-curve chart (one line per strategy) for the evening report. `mailer.py` sends it over SMTP if `EMAIL_*` is configured; otherwise it's a no-op (the report is still always saved to disk by the scheduler). Takes its dependencies as plain parameters, not a bundled context object, so it can't accidentally depend on `app.scheduler`. | `models`, `config`, `data`, `execution`, `database`, `risk`, `strategies`, `reporting` |
| `app/scheduler` | `context.py`'s `build_trading_contexts` builds one `TradingContext` per `Settings.strategies` entry — each its own broker rehydrated from the DB, engine, and strategy, all sharing one data provider (and its cache) and one repository — the paper-trading counterpart to `reporting.Backtester`. `jobs.py` has `morning_job` (reset each strategy's daily-loss baseline, scan + trade, email one comparison report), `evening_job` (mark every strategy to market, email one comparison report), and `hourly_scan_job` (optional, trades only, no report). `scheduler_service.py` wires `Settings.morning_report_time`/`evening_report_time`/`hourly_scan_enabled` into APScheduler `CronTrigger`s. | everything above |
| `app/dashboard` | A read-only Flask app (`app.py`, one route) showing a live comparison across every configured strategy: a summary table, a combined equity-curve chart, and combined holdings/signals/risk/transactions tables tagged by strategy — all read from `SqlTradeRepository` plus one live price/signal check per strategy per symbol. Runs on `127.0.0.1` only; never writes to the database or places a trade. | `models`, `config`, `data`, `database`, `risk`, `strategies`, `reporting` |

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
- **Strategies signal on the crossover event, not the ongoing state.**
  `MovingAverageCrossoverStrategy`/`RsiStrategy`/`MacdStrategy` compare
  the previous bar's relationship (fast vs. slow MA, RSI vs. threshold,
  MACD vs. signal line) to the current bar's, and only emit BUY/SELL when
  it actually flipped. The simpler alternative — signal BUY on every bar
  the condition holds — happens to be harmless here too, since
  `RiskManager` already refuses to re-buy a symbol it's holding, but
  edge-triggering is the more standard, portable definition of
  "crossover" and doesn't rely on that downstream guard to behave correctly.
- **A backtest is a replay through the real engine, not a parallel
  simulation.** `Backtester.run` constructs a `PaperBroker` +
  `RiskManager` + `ExecutionEngine` exactly like live paper trading would,
  swapping in a `ReplayMarketDataProvider` that only ever reveals data up
  to the simulated "current date." This means strategy behavior, risk
  enforcement (including stop-loss/take-profit and the daily loss limit),
  and fill/commission accounting are identical in backtest and paper
  trading by construction — there's no second code path to keep in sync.
- **`Portfolio.apply_fill` returns the realized P&L for that fill.**
  Reporting's `compute_trade_pnl` reuses this (via a scratch `Portfolio`
  seeded with unlimited cash, since it's reconstructing accounting
  history rather than validating affordability) instead of
  re-implementing average-cost math to get per-trade P&L for win
  rate/profit factor/expectancy — one source of truth for "how is
  realized P&L computed."
- **Chart builders return `Figure` objects; they don't know about files,
  HTML, or Jinja2.** `report_generator.py` is the only place that decides
  a report is a single self-contained HTML file (Plotly's JS pulled from
  a CDN once and reused across charts) — charts or the metrics themselves
  could be reused by the dashboard or email reports later without change.
  (They now are: the dashboard and the evening email report both reuse
  `app.reporting.charts.build_equity_curve_chart` unchanged.)
- **The scheduler rehydrates each strategy's paper trading state from the
  database on startup instead of resetting to `INITIAL_CAPITAL`.**
  `build_trading_context` reads the most recent `AccountSnapshotRecord`
  for that `strategy_name`'s cash and `list_open_positions(strategy_name)`
  for holdings, seeding a fresh `PaperBroker`/`Portfolio` with them.
  Without this, restarting `run_scheduler.py` would silently wipe out
  simulated trading history for every strategy — which would be a bad
  enough bug in any persistence layer, but especially misleading in a
  tool whose entire purpose is tracking simulated performance over time.
- **`app.database.engine`'s `get_engine`/`get_session_factory` are keyed
  by database URL, not an unconditional singleton.** They were originally
  a plain "first call wins" cache; that's invisible in production (one
  process always uses one `Settings`), but it silently broke any code
  path that constructs more than one `Settings` in-process — which
  `TradingContext` now legitimately does (real code, and every test that
  exercises it). Keying by URL keeps the effectively-singleton behavior
  in production while giving each distinct database its own engine.
- **Email report builders take a `BrokerInterface`, not a `PaperBroker`.**
  Same reasoning as `RiskManager`: `report_data.py` only calls
  `get_account()`/`get_positions()`, so the identical report-building code
  would work unchanged against a live broker later.
- **The dashboard never holds a live broker or portfolio.** It reads
  `SqlTradeRepository.list_open_positions()`/`equity_curve()`/`list_trades()`
  directly — the database is the single source of truth once the
  scheduler has persisted to it, so the dashboard doesn't need (and, since
  it must never place a trade, shouldn't have) a `PaperBroker` of its own.
  A tiny internal adapter (`_StaticPositionsView`) lets it reuse
  `reporting.position_rows` — built for a live `BrokerInterface` — over
  that static list without changing `position_rows`'s signature.
- **"Today" in trade/report filtering is computed in UTC, not local time.**
  `Fill`/`Account` timestamps are always UTC-aware (`PaperBroker` uses
  `datetime.now(UTC)` throughout); comparing them against Python's
  local-timezone `date.today()` would misclassify trades near midnight
  UTC for any non-UTC user. Precise local-market-timezone trading-day
  boundaries (e.g. NYSE's 4pm ET close) are out of scope for this version.
- **Each strategy gets its own independent simulated account, not a
  shared pool split between strategies.** `positions` and
  `account_snapshots` are keyed by `(strategy_name, ...)` rather than
  globally, so two strategies can each hold a position in the same
  symbol, or have completely different equity curves, at once. This is
  what makes "which strategy is performing best" a meaningful, apples-
  to-apples question rather than an artifact of shared capital
  constraints — the alternative (splitting one account's cash across
  strategies) would let one strategy's trades starve another's.
- **`ExecutionEngine` knows its own `strategy_name` for tagging
  persisted snapshots; risk limits stay global, not per-strategy.**
  `RiskLimits` comes from one shared `Settings`, so every strategy plays
  by the same stop-loss/take-profit/position-sizing rules — the
  comparison is about strategy logic, not one strategy getting looser
  risk controls than another.
- **Sentiment is scraped + scored locally (VADER), not judged by an
  LLM.** An LLM would give more nuanced judgments, but at the cost of a
  required API key and a per-call price — in tension with "don't require
  API keys unless optional." VADER is free, runs with no network call
  for the scoring step itself, and is specifically tuned for short,
  informal text like headlines. `SentimentAnalyzer` is still an
  interface, so an LLM-backed implementation could be swapped in later
  as an opt-in upgrade without changing `SentimentService` or
  `SentimentFilteredStrategy`.
- **Sentiment filters BUY signals only; it never generates or blocks a
  SELL.** `SentimentFilteredStrategy` only consults `SentimentService`
  when the wrapped strategy proposes a BUY, downgrading it to HOLD on
  bearish sentiment. SELL and HOLD pass through untouched — risk-driven
  exits (`RiskManager.check_exits`) are already independent of any
  signal, and a strategy's own SELL logic shouldn't be second-guessed by
  a noisier, lower-fidelity signal.
- **`SentimentFilteredStrategy` is a decorator, not a new strategy
  class per base strategy.** Any existing `Strategy` can be wrapped
  (`SentimentFilteredStrategy(RsiStrategy(), sentiment_service)`) without
  modification. It's registered in `app.strategies.factory` as
  `sma_sentiment` — because the factory is the one place every other
  module (scheduler, dashboard, backtester) already goes through to
  resolve a strategy by name, adding this required no changes to any of
  them; it just shows up as another comparable strategy.
- **`SentimentService.get_sentiment` returns `None` on failure, never
  raises.** A scraping error (network blip, malformed feed, a symbol
  with no news coverage) is logged and treated as "sentiment unknown" —
  `SentimentFilteredStrategy` treats unknown the same as neutral/bullish
  (passes the signal through) rather than blocking trades because a
  third-party feed hiccuped.

## Project layout

```
app/
├── config/       settings.py            — .env → typed Settings
├── models/       enums.py, domain.py    — shared dataclasses & enums
├── utils/        logging_config.py      — 5 rotating log files
├── data/         base.py, yfinance_provider.py, cache.py, watchlist.py, factory.py
│                                        — MarketDataProvider, YFinanceProvider,
│                                          CachedMarketDataProvider, load_watchlist
├── indicators/   moving_average.py, rsi.py, macd.py
│                                        — sma, ema, rsi, macd
├── sentiment/    news_provider.py, analyzer.py, service.py, factory.py
│                                        — GoogleNewsRssProvider, VaderSentimentAnalyzer,
│                                          SentimentService, build_sentiment_service
├── strategies/   base.py, moving_average_crossover.py, rsi_strategy.py, macd_strategy.py,
│                 sentiment_filtered.py — Strategy interface + 4 implementations
├── portfolio/    portfolio.py           — Portfolio ledger (cash/positions/P&L)
├── risk/         rules.py, risk_manager.py — RiskLimits + RiskManager
├── execution/    broker_base.py, paper_broker.py, engine.py, repository.py
│                                        — BrokerInterface, PaperBroker, ExecutionEngine
├── database/     engine.py, orm_models.py, repository.py
│                                        — SQLAlchemy engine/session + SqlTradeRepository
├── reporting/    backtest.py, metrics.py, charts.py, positions.py, report_generator.py, templates/
│                                        — Backtester, PerformanceMetrics, Plotly charts,
│                                          position_rows, HTML report generation
├── email/        mailer.py, report_data.py, renderer.py, templates/
│                                        — SMTP sender, report context builders, Jinja2 rendering
├── scheduler/    context.py, jobs.py, scheduler_service.py
│                                        — TradingContext, morning/evening/hourly jobs, APScheduler wiring
└── dashboard/    app.py, templates/     — read-only Flask app
database/         SQLite file + on-disk market-data cache (gitignored)
logs/             app.log, trades.log, errors.log, scheduler.log, market_data.log (gitignored)
reports/          generated HTML/chart output (gitignored)
tests/            pytest suite
run_backtest.py   python run_backtest.py --symbols AAPL,MSFT --strategy sma
run_scheduler.py  python run_scheduler.py            — starts the paper-trading scheduler
run_dashboard.py  python run_dashboard.py [--port N]  — starts the local dashboard
```

## Configuration

All configuration lives in `.env` (see `.env.example` for the full list
with defaults: `INITIAL_CAPITAL`, `WATCHLIST`, `STRATEGIES` (comma-separated
subset of `sma`/`rsi`/`macd`/`sma_sentiment` — each runs as its own
independent simulated account), `DATABASE_PATH`,
`EMAIL_USERNAME`/`EMAIL_PASSWORD`/`EMAIL_TO`, `MORNING_REPORT_TIME`,
`EVENING_REPORT_TIME`, `HOURLY_SCAN_ENABLED`, `SENTIMENT_HEADLINE_LIMIT`,
`SENTIMENT_CACHE_TTL_SECONDS`, risk-limit percentages, etc.). Every value
has a working default, so the app runs with no `.env` file and no email
credentials at all — email sending is skipped (and logged) when
`EMAIL_*` isn't fully configured, and every report is still saved to
`reports/` regardless. Sentiment scraping/scoring needs no credentials
either — it's opt-in via `STRATEGIES` only.

## Development phases

1. **Architecture & skeleton** — project structure, domain
   models, config, logging, core interfaces (`Strategy`,
   `MarketDataProvider`, `BrokerInterface`), database bootstrap.
2. **Paper trading engine** — `PaperBroker`, `Portfolio`,
   `RiskManager`, `ExecutionEngine`, ORM persistence for trades/positions.
3. **Market data** — `yfinance` provider + on-disk cache, watchlist loading.
4. **Strategies & indicators** — SMA/EMA/RSI/MACD, Moving Average
   Crossover / RSI / MACD strategies.
5. **Backtesting & reporting** — `run_backtest.py`, performance metrics
   (Sharpe, CAGR, drawdown, ...), equity curve + benchmark charts.
6. **Scheduler, email reports, dashboard** — morning/evening
   jobs (`run_scheduler.py`), HTML email reports, local dashboard
   (`run_dashboard.py`).

Each phase shipped runnable and tested before the next began. All six are
complete on `main`. Since then: multi-strategy comparison (each strategy
trades its own account) and, on `feature/sentiment-analysis`, the
`sma_sentiment` strategy described above.
