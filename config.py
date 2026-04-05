"""
CryptoBot Configuration
Paper trading bot - NO real orders ever placed.

All sensitive values loaded from environment variables.
Copy .env.example to .env and fill in your credentials.
"""
import os

# ── Kraken API (used ONLY for price data, never for orders) ─────────────────
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY", "")
KRAKEN_PRIVATE_KEY = os.getenv("KRAKEN_PRIVATE_KEY", "")

# ── Paper-Trading Account ────────────────────────────────────────────────────
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "500.0"))
PAIR = os.getenv("TRADING_PAIR", "XXBTZUSD")
PAIR_DISPLAY = os.getenv("PAIR_DISPLAY", "BTC/USD")

# ── Risk Rules ───────────────────────────────────────────────────────────────
MAX_RISK_PER_TRADE_PCT = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "2.0"))
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", "5"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "2.0"))
DAILY_MAX_LOSS_PCT = float(os.getenv("DAILY_MAX_LOSS_PCT", "5.0"))
WEEKLY_MAX_LOSS_PCT = float(os.getenv("WEEKLY_MAX_LOSS_PCT", "10.0"))
DRAWDOWN_PAUSE_PCT = float(os.getenv("DRAWDOWN_PAUSE_PCT", "15.0"))

# ── Grid Bot (Strategy 1) ────────────────────────────────────────────────────
GRID_ALLOCATION_PCT = 80.0       # 80% of balance
GRID_RANGE_PCT = 10.0            # ±10% around current price
GRID_LEVELS = 10                 # number of grid lines
GRID_RESERVE_PCT = 20.0          # keep 20% reserve

# ── Sentiment Swing (Strategy 2) ─────────────────────────────────────────────
SENTIMENT_API_URL = "https://api.alternative.me/fng/"
FEAR_THRESHOLD = 25              # extreme fear → buy signal
GREED_THRESHOLD = 75             # extreme greed → sell signal
SWING_TAKE_PROFIT_PCT = 5.0     # 5% target
SWING_STOP_LOSS_PCT = 2.0

# ── Scheduling ────────────────────────────────────────────────────────────────
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))

# ── Paths ─────────────────────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADE_LOG_PATH = os.path.join(BOT_DIR, "TRADE_LOG.md")
STATE_FILE = os.path.join(BOT_DIR, "bot_state.json")
LOG_FILE = os.path.join(BOT_DIR, "bot.log")
