"""
CryptoBot Configuration
Paper trading bot — NO real orders ever placed.
"""
import os

# ── Kraken API (used ONLY for price data, never for orders) ──────────────
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY")

if not KRAKEN_API_KEY:
    raise RuntimeError("Missing required environment variable: KRAKEN_API_KEY")
if not KRAKEN_PRIVATE_KEY:
    raise RuntimeError("Missing required environment variable: KRAKEN_PRIVATE_KEY")

# ── Paper-Trading Account ────────────────────────────────────────────────
INITIAL_BALANCE = 500.0          # USD virtual balance
PAIR = "XXBTZUSD"                # Kraken pair name for BTC/USD
PAIR_DISPLAY = "BTC/USD"

# ── Risk Rules (from RISK_RULES.md — relaxed for paper trading) ────────────
MAX_RISK_PER_TRADE_PCT = 20.0    # 20% of account per trade ($100 on $500) — paper mode, bigger P&L for training engine
MAX_CONCURRENT_POSITIONS = 5     # 5 concurrent positions — more data for learning
STOP_LOSS_PCT = 2.0              # default stop-loss %
DAILY_MAX_LOSS_PCT = 15.0        # $75 on $500 — paper mode, need data
WEEKLY_MAX_LOSS_PCT = 25.0       # $125 on $500 — paper mode
DRAWDOWN_PAUSE_PCT = 30.0        # 30% drawdown pause — paper mode, let it run

# ── Grid Bot (Strategy 1) ───────────────────────────────────────────────
GRID_ALLOCATION_PCT = 80.0       # 80% of balance ($400)
GRID_RANGE_PCT = 10.0            # ±10% around current price
GRID_LEVELS = 10                 # number of grid lines
GRID_RESERVE_PCT = 20.0          # keep 20% ($100) reserve
MAX_GRID_POSITIONS = 2           # max open grid positions (leaves 3 slots for other strategies)

# ── Sentiment Swing (Strategy 2) ────────────────────────────────────────
SENTIMENT_API_URL = "https://api.alternative.me/fng/"
FEAR_THRESHOLD = 25              # extreme fear → buy signal
GREED_THRESHOLD = 75             # extreme greed → sell signal
SWING_TAKE_PROFIT_PCT = 5.0     # 5-8% target (use 5% as default)
SWING_STOP_LOSS_PCT = 2.0

# ── Political / Macro Signals (Strategy 6) ──────────────────────────────
POLITICAL_SIGNAL_THRESHOLD = 50   # composite score ±50 triggers trade
POLITICAL_DECAY_HOURS = 4.0       # political signals lose relevance after 4h
POLITICAL_ENABLE_TRUMP = True     # toggle Trump/Truth Social signals
POLITICAL_ENABLE_CONGRESS = True  # toggle congressional trading signals
POLITICAL_ENABLE_FED = True       # toggle Federal Reserve/macro signals
POLITICAL_ENABLE_SEC = True       # toggle SEC EDGAR institutional signals

# ── Strategy Enable/Disable Toggles ─────────────────────────────────────
# Dead-weight strategies (1 trade each in 6-month backtest) — disabled by default
ENABLE_EMA_MACD = False           # EMA/MACD: 1 trade in 6mo backtest, wastes compute
ENABLE_BOLLINGER = False          # Bollinger: 1 trade in 6mo backtest, wastes compute
ENABLE_TARIFF_WHIPLASH = False    # Tariff whiplash: 1 trade in 6mo, needs real tariff events
ENABLE_CONGRESS_FRONTRUN = True   # Congressional front-running: 50% WR, 2.42 PF — keep active
ENABLE_RSI_DIVERGENCE = True      # RSI divergence: keep for signal diversity

# ── Research — Binance Futures (451 from US IP, disable to stop log spam) ──
ENABLE_BINANCE_RESEARCH = False   # US IP gets 451; re-enable with VPN/proxy

# ── Scheduling ───────────────────────────────────────────────────────────
CHECK_INTERVAL_SECONDS = 300     # 5 minutes

# ── Paths ────────────────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADE_LOG_PATH = os.path.join(BOT_DIR, "TRADE_LOG.md")
STATE_FILE = os.path.join(BOT_DIR, "bot_state.json")
LOG_FILE = os.path.join(BOT_DIR, "bot.log")
