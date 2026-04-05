"""
Risk Manager — enforces every rule from RISK_RULES.md.
"""
import logging
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import config

logger = logging.getLogger("cryptobot.risk")


class RiskManager:
    """Tracks P&L, enforces limits, triggers alerts."""

    def __init__(self, state_file: str = config.STATE_FILE):
        self._state_file = state_file
        self._state = self._load_state()

    # ── State persistence ────────────────────────────────────────────────

    def _default_state(self) -> dict:
        return {
            "balance": config.INITIAL_BALANCE,
            "peak_balance": config.INITIAL_BALANCE,
            "positions": [],  # list of open position dicts
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "daily_reset": datetime.utcnow().strftime("%Y-%m-%d"),
            "weekly_reset": datetime.utcnow().strftime("%Y-%m-%d"),
            "paused": False,
            "pause_reason": "",
            "trades_today": 0,
        }

    def _load_state(self) -> dict:
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, "r") as f:
                    state = json.load(f)
                # Reset daily/weekly counters if needed
                self._maybe_reset_counters(state)
                return state
            except Exception:
                logger.warning("Corrupt state file, starting fresh")
        return self._default_state()

    def save_state(self):
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def _maybe_reset_counters(self, state: dict):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if state.get("daily_reset") != today:
            state["daily_pnl"] = 0.0
            state["daily_reset"] = today
            state["trades_today"] = 0
        # Weekly reset on Monday
        now = datetime.utcnow()
        last_reset = datetime.strptime(state.get("weekly_reset", today), "%Y-%m-%d")
        if (now - last_reset).days >= 7:
            state["weekly_pnl"] = 0.0
            state["weekly_reset"] = today

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._state["balance"]

    @property
    def positions(self) -> list:
        return self._state["positions"]

    @property
    def is_paused(self) -> bool:
        return self._state.get("paused", False)

    @property
    def pause_reason(self) -> str:
        return self._state.get("pause_reason", "")

    def can_open_position(self, price: float) -> tuple[bool, str]:
        """Check ALL risk rules before opening a position."""
        if self.is_paused:
            return False, f"Trading paused: {self.pause_reason}"

        # Max concurrent positions
        open_count = len([p for p in self._state["positions"] if p["status"] == "open"])
        if open_count >= config.MAX_CONCURRENT_POSITIONS:
            return False, f"Max {config.MAX_CONCURRENT_POSITIONS} concurrent positions"

        # Daily loss limit
        if abs(self._state["daily_pnl"]) >= self.balance * (config.DAILY_MAX_LOSS_PCT / 100):
            return False, "Daily loss limit reached"

        # Weekly loss limit
        if abs(self._state["weekly_pnl"]) >= self.balance * (config.WEEKLY_MAX_LOSS_PCT / 100):
            return False, "Weekly loss limit reached"

        # Drawdown check
        drawdown = (self._state["peak_balance"] - self.balance) / self._state["peak_balance"] * 100
        if drawdown >= config.DRAWDOWN_PAUSE_PCT:
            self._state["paused"] = True
            self._state["pause_reason"] = f"Drawdown {drawdown:.1f}% exceeds {config.DRAWDOWN_PAUSE_PCT}%"
            self.save_state()
            return False, self._state["pause_reason"]

        return True, "OK"

    def max_position_size_usd(self) -> float:
        """Max USD per trade = 2% of balance."""
        return self.balance * (config.MAX_RISK_PER_TRADE_PCT / 100)

    def position_size_btc(self, price: float) -> float:
        """How much BTC we can buy with max allowed USD."""
        max_usd = self.max_position_size_usd()
        return max_usd / price

    def open_position(self, side: str, price: float, size_btc: float,
                      strategy: str, stop_loss: float, take_profit: float) -> dict:
        """Record a new paper position."""
        pos = {
            "id": f"{strategy}-{int(time.time())}",
            "side": side,
            "entry_price": price,
            "size_btc": size_btc,
            "size_usd": price * size_btc,
            "strategy": strategy,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "status": "open",
            "opened_at": datetime.utcnow().isoformat(),
            "closed_at": None,
            "exit_price": None,
            "pnl": 0.0,
        }
        self._state["positions"].append(pos)
        self._state["trades_today"] += 1
        self.save_state()
        logger.info("OPENED %s %s %.6f BTC @ $%.2f [%s] SL=$%.2f TP=$%.2f",
                     side, config.PAIR_DISPLAY, size_btc, price, strategy, stop_loss, take_profit)
        return pos

    def close_position(self, pos_id: str, exit_price: float) -> Optional[dict]:
        """Close a position, compute P&L, update balance."""
        for pos in self._state["positions"]:
            if pos["id"] == pos_id and pos["status"] == "open":
                pos["status"] = "closed"
                pos["exit_price"] = exit_price
                pos["closed_at"] = datetime.utcnow().isoformat()

                if pos["side"] == "buy":
                    pos["pnl"] = (exit_price - pos["entry_price"]) * pos["size_btc"]
                else:
                    pos["pnl"] = (pos["entry_price"] - exit_price) * pos["size_btc"]

                self._state["balance"] += pos["pnl"]
                self._state["daily_pnl"] += pos["pnl"]
                self._state["weekly_pnl"] += pos["pnl"]

                # Update peak
                if self._state["balance"] > self._state["peak_balance"]:
                    self._state["peak_balance"] = self._state["balance"]

                self.save_state()
                logger.info("CLOSED %s @ $%.2f | P&L: $%.2f | Balance: $%.2f",
                            pos_id, exit_price, pos["pnl"], self.balance)
                return pos
        return None

    def check_stop_loss_take_profit(self, current_price: float) -> list:
        """Check all open positions for SL/TP hits. Returns list of closed positions."""
        closed = []
        for pos in list(self._state["positions"]):
            if pos["status"] != "open":
                continue
            if pos["side"] == "buy":
                if current_price <= pos["stop_loss"]:
                    logger.warning("STOP-LOSS hit for %s @ $%.2f", pos["id"], current_price)
                    result = self.close_position(pos["id"], current_price)
                    if result:
                        closed.append(result)
                elif current_price >= pos["take_profit"]:
                    logger.info("TAKE-PROFIT hit for %s @ $%.2f", pos["id"], current_price)
                    result = self.close_position(pos["id"], current_price)
                    if result:
                        closed.append(result)
            else:  # sell/short (paper only)
                if current_price >= pos["stop_loss"]:
                    logger.warning("STOP-LOSS hit for %s @ $%.2f", pos["id"], current_price)
                    result = self.close_position(pos["id"], current_price)
                    if result:
                        closed.append(result)
                elif current_price <= pos["take_profit"]:
                    logger.info("TAKE-PROFIT hit for %s @ $%.2f", pos["id"], current_price)
                    result = self.close_position(pos["id"], current_price)
                    if result:
                        closed.append(result)
        return closed

    def get_daily_summary(self) -> dict:
        """Generate daily performance summary."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_trades = [p for p in self._state["positions"]
                        if p.get("opened_at", "").startswith(today)]
        closed_today = [p for p in today_trades if p["status"] == "closed"]
        wins = [p for p in closed_today if p["pnl"] > 0]
        losses = [p for p in closed_today if p["pnl"] < 0]

        return {
            "date": today,
            "balance": self.balance,
            "daily_pnl": self._state["daily_pnl"],
            "trades_opened": len(today_trades),
            "trades_closed": len(closed_today),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed_today) * 100 if closed_today else 0,
            "open_positions": len([p for p in self._state["positions"] if p["status"] == "open"]),
            "drawdown_pct": (self._state["peak_balance"] - self.balance) / self._state["peak_balance"] * 100,
            "paused": self.is_paused,
        }
