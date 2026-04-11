# crypto-trading-bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Paper Trading](https://img.shields.io/badge/Mode-Paper%20Trading%20Only-orange)](https://en.wikipedia.org/wiki/Paper_trading)

A Python paper-trading bot for BTC/USD on Kraken with **8 concurrent strategies**, political/macro signal analysis, a self-improving training engine, and strict risk management. **No real orders are ever placed.**

## Architecture

```
bot.py (main loop, 5-min ticks)
├── strategies/
│   ├── grid.py              – Grid bot for sideways markets
│   ├── sentiment.py         – Fear & Greed Index swing trades
│   ├── ema_macd.py          – EMA/MACD momentum (SMA50 trend filter)
│   ├── bollinger.py         – Bollinger mean reversion
│   ├── rsi_divergence.py    – RSI divergence reversals
│   ├── political.py         – Political signal composite scoring
│   └── novel.py             – Tariff Whiplash + Congressional Front-Running
├── trainer/
│   ├── engine.py            – Training loop (runs every 60 min)
│   ├── analyzer.py          – Scores strategy performance
│   ├── tuner.py             – Adjusts parameters within safe bounds
│   ├── researcher.py        – Market context + volatility regime
│   ├── meta_learner.py      – Tunes the trainer's own hyperparameters
│   ├── discovery.py         – Pattern mining + correlation analysis
│   └── backtester.py        – Historical backtesting engine
├── manager/
│   ├── health.py            – System health checks
│   ├── researcher.py        – Research sweeps
│   └── supervisor.py        – Orchestration
└── utils/
    ├── kraken_client.py     – Price data only (no orders)
    ├── risk_manager.py      – Position sizing + loss limits + centralized logging
    ├── congress_trades.py   – House Clerk XML + Senate EFDS parsers
    ├── fed_signals.py       – FOMC/CPI/jobs/GDP calendar + FRED API
    ├── sec_filings.py       – SEC EDGAR 13F institutional crypto holdings
    └── logger.py            – Structured logging
```

## Strategies

### Original 5
1. **Grid Bot** — Sets buy/sell levels ±10% around reference price. Sideways markets.
2. **Sentiment Swing** — Fear & Greed Index signal. Buys extreme fear, shorts extreme greed.
3. **EMA/MACD Momentum** — 12/26 EMA crossover + MACD histogram + SMA50 trend filter.
4. **Bollinger Mean Reversion** — 20-period bands with RSI confirmation, ADX <30 filter.
5. **RSI Divergence** — Detects bullish/bearish divergence on 4h timeframes.

### Political & Macro (NEW)
6. **Political Signal Analysis** — Composite scorer (-100 to +100) scanning Truth Social keywords, FOMC decisions, SEC actions. 4-hour signal decay window.
7. **Tariff Whiplash** — Detects tariff-induced dips (3.5% threshold), targets 75% recovery within 72h.
8. **Congressional Front-Running** — Triggers when 3+ Congress members file crypto-adjacent PTRs. Hold 7-14 days.

## Backtest Results (30-day, Mar–Apr 2026)

| Strategy | Win Rate | Profit Factor | Sharpe | Notes |
|----------|----------|---------------|--------|-------|
| Congress Frontrun | 75% | 2.44 | 5.36 | ⭐ Best performer |
| Grid | 70% | 1.37 | 2.11 | Steady in range |
| Political | 100% | — | — | 2 trades (promising) |
| Tariff Whiplash | 50% | — | — | Needs tuning |
| EMA/MACD | 60% | 1.18 | 1.45 | Improved with SMA50 |

## Political Signal Correlations

| Signal Type | BTC Impact (24h) |
|-------------|------------------|
| Crypto-positive news | +3.48% |
| Fed decisions | +1.40% |
| Tariff announcements | -0.55% (recovers by 72h) |

## Data Sources

- **Kraken API** — Real-time OHLCV (public, read-only)
- **House Clerk XML** — Congressional stock/crypto trade disclosures
- **Senate EFDS** — Senate financial disclosure filings
- **FRED API** — FOMC schedule, CPI, jobs, GDP data
- **SEC EDGAR** — 13F institutional crypto holdings
- **Fear & Greed Index** — Market sentiment

## Quick Start

```bash
git clone https://github.com/simonlpaige/crypto-trading-bot.git
cd crypto-trading-bot

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your Kraken API key (read-only scope sufficient)

# Run the bot
python bot.py

# Run backtests
python bot.py --backtest
```

## Configuration

All sensitive values loaded from environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KRAKEN_API_KEY` | — | Kraken API key (read-only) |
| `KRAKEN_PRIVATE_KEY` | — | Kraken private key |
| `INITIAL_BALANCE` | `500.0` | Virtual starting balance (USD) |
| `MAX_CONCURRENT_POSITIONS` | `3` | Max open positions |
| `DAILY_MAX_LOSS_PCT` | `5.0` | Daily loss limit (%) |
| `DRAWDOWN_PAUSE_PCT` | `15.0` | Drawdown % that pauses trading |
| `FRED_API_KEY` | — | FRED API key (for fed signals) |

## Features

- 🤖 **8 concurrent strategies** — 5 technical + 3 political/macro
- 🏛️ **Congressional trade tracking** — House + Senate disclosure parsing
- 📡 **Political signal analysis** — Truth Social, FOMC, SEC composite scoring
- 🧠 **Self-improving training engine** — tunes parameters every hour
- 🔄 **Meta-learner** — recursively improves the trainer
- 🛡️ **Strict risk management** — per-trade limits, daily/weekly caps, circuit breaker
- 📊 **Backtesting engine** — historical strategy validation
- 🔍 **Pattern discovery** — mines correlations between signals and outcomes

## License

MIT
