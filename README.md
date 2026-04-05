# crypto-trading-bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Paper Trading](https://img.shields.io/badge/Mode-Paper%20Trading%20Only-orange)](https://en.wikipedia.org/wiki/Paper_trading)

A Python paper-trading bot for BTC/USD on Kraken with five concurrent strategies, a self-improving training engine, and strict risk management. **No real orders are ever placed.**

## Architecture

```
bot.py (main loop, 5-min ticks)
├── strategies/
│   ├── grid.py           – Grid bot for sideways markets
│   ├── sentiment.py      – Fear & Greed Index swing trades
│   ├── ema_macd.py       – EMA/MACD momentum
│   ├── bollinger.py      – Bollinger mean reversion
│   └── rsi_divergence.py – RSI divergence reversals
├── trainer/
│   ├── engine.py         – Training loop (runs every 60 min)
│   ├── analyzer.py       – Scores strategy performance
│   ├── tuner.py          – Adjusts parameters within safe bounds
│   ├── researcher.py     – Market context + volatility regime
│   ├── meta_learner.py   – Tunes the trainer's own hyperparameters
│   └── discovery.py      – Pattern mining + correlation analysis
├── manager/
│   ├── health.py         – System health checks
│   ├── researcher.py     – Research sweeps
│   └── supervisor.py     – Orchestration
└── utils/
    ├── kraken_client.py  – Price data only (no orders)
    ├── risk_manager.py   – Position sizing + loss limits
    └── logger.py         – Structured logging
```

## Features

- 🤖 **Five concurrent strategies** — grid, sentiment, EMA/MACD, Bollinger bands, RSI divergence
- 🧠 **Self-improving training engine** — analyzes performance and tunes parameters every hour
- 🔄 **Meta-learner** — recursively improves the trainer itself
- 🛡️ **Strict risk management** — per-trade limits, daily/weekly loss caps, drawdown circuit breaker
- 📊 **Market regime detection** — switches strategy weights based on ADX/volatility
- 🔍 **Pattern discovery** — mines correlations between signals and outcomes
- 📝 **Full trade logging** — structured JSONL + markdown trade log

## Quick Start

```bash
# Clone the repo
git clone https://github.com/simonlpaige/crypto-trading-bot.git
cd crypto-trading-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Kraken API key (read-only is fine, no trading perms needed)

# Run the bot (paper trading only)
python bot.py
```

## Configuration

All sensitive values are loaded from environment variables. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `KRAKEN_API_KEY` | — | Kraken API key (read-only scope sufficient) |
| `KRAKEN_PRIVATE_KEY` | — | Kraken private key |
| `INITIAL_BALANCE` | `500.0` | Virtual starting balance in USD |
| `MAX_RISK_PER_TRADE_PCT` | `2.0` | Max % of balance at risk per trade |
| `MAX_CONCURRENT_POSITIONS` | `5` | Max open positions simultaneously |
| `DAILY_MAX_LOSS_PCT` | `5.0` | Daily loss limit (% of balance) |
| `DRAWDOWN_PAUSE_PCT` | `15.0` | Drawdown % that pauses all trading |
| `CHECK_INTERVAL_SECONDS` | `300` | How often to run strategy evaluations |

## Strategies

### 1. Grid Bot
Sets buy/sell levels ±10% around a reference price. Passive income strategy for sideways markets. Re-centers when price moves >15%.

### 2. Sentiment Swing
Uses the [Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/) as signal. Buys on extreme fear (≤25) with positive divergence, shorts on extreme greed (≥75).

### 3. EMA/MACD Momentum
12/26 EMA crossover with MACD histogram confirmation. ADX filter (>25) ensures we only trade trending markets. Targets 3.2% with 1.8% stop.

### 4. Bollinger Mean Reversion
20-period Bollinger Bands with RSI confirmation. ADX filter (<30) ensures we only trade ranging markets. Entry at band touch, exit at middle band.

### 5. RSI Divergence
Detects bullish/bearish divergence on 4h timeframes. Bullish: price lower low + RSI higher low. 1:1.5 risk-reward ratio.

## Training Engine

Every 60 minutes, the trainer:
1. **Analyzes** recent trade performance per strategy
2. **Researches** market context (volatility, sentiment)
3. **Tunes** one parameter per strategy within safe bounds
4. **Detects** if 3 consecutive degradations → reverts to defaults
5. **Discovers** new signal/outcome correlations (every 6th cycle)
6. **Meta-learns** — optimizes the trainer's own hyperparameters (every 12th cycle)

## Risk Management

- 2% max per-trade risk
- 5% daily loss cap
- 10% weekly loss cap  
- 15% drawdown → all trading paused
- Stop-loss/take-profit enforced on every tick

## Tech Stack

- **Python 3.10+**
- **krakenex** + **pykrakenapi** — price data
- **requests** — Fear & Greed API
- **python-dotenv** — environment config

## Disclaimer

This is a **paper trading simulation only**. No real money is involved. Past simulated performance does not guarantee future results. Trade real money at your own risk.

## License

MIT — see [LICENSE](LICENSE)
