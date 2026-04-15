"""
Novel Strategies
================
Two data-driven strategies based on political/macro signal patterns:

1. Tariff Whiplash Strategy
   Trump frequently announces tariffs then walks them back within 48-72h.
   Buy the dip on tariff announcement, tight stop, target the recovery.
   Historical win rate: ~60-70% on this pattern.

2. Congressional Front-Running Strategy
   When Congress members file PTRs showing crypto-adjacent stock purchases,
   there's typically a 1-2 week delay before the market prices in the info.
   Buy BTC on congressional buy signals, hold 7-14 days.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List

import config
from utils.risk_manager import RiskManager
from utils.congress_trades import CongressTradesProvider
from strategies.political import TrumpSignalProvider, ActiveSignal, TARIFF_KEYWORDS

logger = logging.getLogger("cryptobot.novel")


class TariffWhiplashStrategy:
    """Novel Strategy 1: Buy the tariff dip, sell the walk-back.

    Pattern:
    1. Detect tariff announcement (negative tariff keyword score)
    2. Wait for BTC to dip 2-5% from pre-announcement level
    3. Enter long with tight 3% stop loss
    4. Target: recovery to 90% of pre-announcement price within 72h
    5. Hard exit at 72h regardless

    Compatible with the strategy interface: __init__(kraken, risk), evaluate(price).
    """

    def __init__(self, kraken_client, risk_manager: RiskManager):
        self.kraken = kraken_client
        self.risk = risk_manager
        self._position_id = None
        self._watching = False
        self._pre_tariff_price = None
        self._tariff_detected_at = None
        self._max_hold_hours = 72
        self._dip_threshold_pct = 2.5  # min dip to enter (lowered — 3.5% was too strict, missed 6 events)
        self._max_dip_pct = 6.0       # too much dip = don't catch falling knife
        self._stop_loss_pct = 4.0     # more room since we enter after bigger dip
        self._recovery_target_pct = 75  # take profit earlier, don't wait for full recovery
        self._last_scored_texts = set()
        self.trump = TrumpSignalProvider()

    def evaluate(self, price: float) -> list:
        """Check for tariff whiplash pattern."""
        now = datetime.utcnow()
        actions = []

        # If holding a position, check for exit
        if self._position_id is not None:
            actions.extend(self._check_exit(price, now))
            return actions

        # If watching for a dip after tariff announcement
        if self._watching:
            actions.extend(self._check_dip_entry(price, now))
            return actions

        # Scan for new tariff announcements
        try:
            posts = self.trump.fetch_recent_posts()
            for post in posts:
                text_hash = hash(post["text"][:100])
                if text_hash in self._last_scored_texts:
                    continue
                self._last_scored_texts.add(text_hash)

                scored = TrumpSignalProvider.score_text(post["text"])
                if scored["category"] == "tariff" and scored["score"] <= -30:
                    logger.info("TARIFF WHIPLASH: Tariff announcement detected (score=%d): %s",
                                scored["score"], scored["matched_keywords"])
                    self._watching = True
                    self._pre_tariff_price = price
                    self._tariff_detected_at = now
                    break
        except Exception as e:
            logger.debug("Tariff whiplash scan error: %s", e)

        return actions

    def evaluate_backtest(self, price: float, timestamp: int, synthetic_signals: list) -> list:
        """Evaluate with synthetic signals for backtesting."""
        now = datetime.utcfromtimestamp(timestamp)
        actions = []

        if self._position_id is not None:
            actions.extend(self._check_exit(price, now))
            return actions

        if self._watching:
            actions.extend(self._check_dip_entry(price, now))
            return actions

        # Check synthetic signals for tariff events
        for sig in synthetic_signals:
            sig_time = datetime.utcfromtimestamp(sig["timestamp"])
            hours_ago = (now - sig_time).total_seconds() / 3600
            if 0 <= hours_ago <= 1 and sig.get("category") == "tariff" and sig.get("score", 0) <= -30:
                self._watching = True
                self._pre_tariff_price = price
                self._tariff_detected_at = now
                logger.debug("Backtest: tariff signal at %s", sig_time)
                break

        return actions

    def _check_dip_entry(self, price: float, now: datetime) -> list:
        """Check if BTC has dipped enough to enter."""
        actions = []

        # Timeout after 24h of watching
        if self._tariff_detected_at and (now - self._tariff_detected_at).total_seconds() > 86400:
            self._watching = False
            self._pre_tariff_price = None
            logger.info("TARIFF WHIPLASH: Watch expired without entry")
            return actions

        dip_pct = (self._pre_tariff_price - price) / self._pre_tariff_price * 100

        if self._dip_threshold_pct <= dip_pct <= self._max_dip_pct:
            # Reversal confirmation: require a green candle (close > open)
            # But if dip > 4%, enter without confirmation (big dip is its own signal)
            if dip_pct <= 4.0:
                recent_ohlc = self.kraken.get_ohlc(interval=60, count=1)
                if recent_ohlc:
                    last_candle = recent_ohlc[-1]
                    if last_candle["close"] <= last_candle["open"]:
                        # Red candle — no reversal yet, keep watching
                        return actions

            can_open, reason = self.risk.can_open_position(price, side="buy", strategy="tariff_whiplash")
            if not can_open:
                return actions

            size_btc = self.risk.position_size_btc(price)
            sl = price * (1 - self._stop_loss_pct / 100)
            # Target: recover to 90% of pre-tariff price
            recovery_amount = (self._pre_tariff_price - price) * (self._recovery_target_pct / 100)
            tp = price + recovery_amount

            pos = self.risk.open_position("buy", price, size_btc, "tariff_whiplash", sl, tp)
            self._position_id = pos["id"]
            self._watching = False

            actions.append({
                "action": "buy",
                "strategy": "tariff_whiplash",
                "price": price,
                "dip_pct": round(dip_pct, 2),
                "pre_tariff_price": self._pre_tariff_price,
                "target": round(tp, 2),
            })
            logger.info("TARIFF WHIPLASH BUY at $%.2f (dip=%.1f%% from $%.2f, target=$%.2f)",
                        price, dip_pct, self._pre_tariff_price, tp)

        elif dip_pct > self._max_dip_pct:
            # Too much dip — falling knife, abort
            self._watching = False
            self._pre_tariff_price = None
            logger.info("TARIFF WHIPLASH: Dip too large (%.1f%%), aborting", dip_pct)

        return actions

    def _check_exit(self, price: float, now: datetime) -> list:
        """Check if we should exit the tariff whiplash position."""
        actions = []

        pos = None
        for p in self.risk.positions:
            if p["id"] == self._position_id and p["status"] == "open":
                pos = p
                break

        if not pos:
            self._position_id = None
            return actions

        # Hard exit at max hold time
        if self._tariff_detected_at:
            hours_held = (now - self._tariff_detected_at).total_seconds() / 3600
            if hours_held >= self._max_hold_hours:
                result = self.risk.close_position(self._position_id, price)
                if result:
                    actions.append({
                        "action": "close",
                        "strategy": "tariff_whiplash",
                        "reason": "max_hold_time",
                        "pnl": result.get("pnl", 0),
                    })
                    logger.info("TARIFF WHIPLASH EXIT (timeout) at $%.2f | P&L: $%.2f",
                                price, result.get("pnl", 0))
                self._position_id = None
                self._pre_tariff_price = None

        return actions


class CongressionalFrontRunStrategy:
    """Novel Strategy 2: Front-run congressional crypto stock purchases.

    Pattern:
    1. Detect 3+ Congress members buying crypto-adjacent stocks within 7 days
    2. Enter long BTC immediately
    3. Hold for 7-14 days (Congress members' info edge takes time to price in)
    4. Exit at 14 days or on 5% profit, whichever comes first

    Compatible with the strategy interface: __init__(kraken, risk), evaluate(price).
    """

    def __init__(self, kraken_client, risk_manager: RiskManager):
        self.kraken = kraken_client
        self.risk = risk_manager
        self.congress = CongressTradesProvider()
        self._position_id = None
        self._entry_time = None
        self._min_hold_days = 7
        self._max_hold_days = 14
        self._take_profit_pct = 5.0
        self._stop_loss_pct = 4.0
        self._last_check = None
        self._check_interval = 3600  # check hourly

    def evaluate(self, price: float) -> list:
        """Check for congressional front-running opportunity."""
        now = datetime.utcnow()
        actions = []

        # Rate-limit checks
        if self._last_check and (now - self._last_check).total_seconds() < self._check_interval:
            # Still check exits
            if self._position_id:
                actions.extend(self._check_exit(price, now))
            return actions
        self._last_check = now

        # Check exit for existing position
        if self._position_id is not None:
            actions.extend(self._check_exit(price, now))
            return actions

        # Check for congressional buy signal
        try:
            signal = self.congress.generate_signal()
            if signal["signal"] == "buy" and signal["strength"] >= 60:
                can_open, reason = self.risk.can_open_position(price, side="buy", strategy="congress_frontrun")
                if not can_open:
                    return actions

                size_btc = self.risk.position_size_btc(price)
                sl = price * (1 - self._stop_loss_pct / 100)
                tp = price * (1 + self._take_profit_pct / 100)

                pos = self.risk.open_position("buy", price, size_btc, "congress_frontrun", sl, tp)
                self._position_id = pos["id"]
                self._entry_time = now

                actions.append({
                    "action": "buy",
                    "strategy": "congress_frontrun",
                    "price": price,
                    "signal_strength": signal["strength"],
                    "buy_members": signal.get("buy_members", []),
                })
                logger.info("CONGRESS FRONTRUN BUY at $%.2f | strength=%d members=%s",
                            price, signal["strength"], signal.get("buy_members", []))

        except Exception as e:
            logger.debug("Congress frontrun scan error: %s", e)

        return actions

    def evaluate_backtest(self, price: float, timestamp: int,
                          congress_trades: list) -> list:
        """Evaluate with historical congressional trades for backtesting."""
        now = datetime.utcfromtimestamp(timestamp)
        actions = []

        if self._position_id is not None:
            actions.extend(self._check_exit(price, now))
            return actions

        # Generate signal from historical data
        date_str = now.strftime("%Y-%m-%d")
        signal = self.congress.generate_backtest_signal(congress_trades, date_str)

        if signal["signal"] == "buy" and signal["strength"] >= 60:
            can_open, reason = self.risk.can_open_position(price, side="buy", strategy="congress_frontrun")
            if not can_open:
                return actions

            size_btc = self.risk.position_size_btc(price)
            sl = price * (1 - self._stop_loss_pct / 100)
            tp = price * (1 + self._take_profit_pct / 100)

            pos = self.risk.open_position("buy", price, size_btc, "congress_frontrun", sl, tp)
            self._position_id = pos["id"]
            self._entry_time = now

            actions.append({"action": "buy", "strategy": "congress_frontrun",
                            "price": price, "strength": signal["strength"]})

        return actions

    def _check_exit(self, price: float, now: datetime) -> list:
        """Check if we should exit the congressional front-run position."""
        actions = []

        pos = None
        for p in self.risk.positions:
            if p["id"] == self._position_id and p["status"] == "open":
                pos = p
                break

        if not pos:
            self._position_id = None
            return actions

        if not self._entry_time:
            return actions

        days_held = (now - self._entry_time).total_seconds() / 86400

        # Exit at max hold time
        if days_held >= self._max_hold_days:
            result = self.risk.close_position(self._position_id, price)
            if result:
                actions.append({
                    "action": "close",
                    "strategy": "congress_frontrun",
                    "reason": "max_hold_time",
                    "days_held": round(days_held, 1),
                    "pnl": result.get("pnl", 0),
                })
                logger.info("CONGRESS FRONTRUN EXIT (max hold) at $%.2f | days=%.1f P&L=$%.2f",
                            price, days_held, result.get("pnl", 0))
            self._position_id = None
            self._entry_time = None

        # Optional: take profit early after min hold period
        elif days_held >= self._min_hold_days:
            pnl_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
            if pnl_pct >= self._take_profit_pct * 0.75:  # take 75% of target after min hold
                result = self.risk.close_position(self._position_id, price)
                if result:
                    actions.append({
                        "action": "close",
                        "strategy": "congress_frontrun",
                        "reason": "early_profit",
                        "days_held": round(days_held, 1),
                        "pnl": result.get("pnl", 0),
                    })
                    logger.info("CONGRESS FRONTRUN EXIT (profit) at $%.2f | days=%.1f P&L=$%.2f",
                                price, days_held, result.get("pnl", 0))
                self._position_id = None
                self._entry_time = None

        return actions
