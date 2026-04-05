#!/usr/bin/env python3
"""
CryptoBot — Paper Trading Bot
==============================
Connects to Kraken for real-time BTC/USD prices.
Runs five strategies:
  1. Grid Bot (passive, ranging markets)
  2. Sentiment Swing (Fear & Greed driven)
  3. EMA/MACD Momentum (trending markets, ADX>25)
  4. Bollinger Mean Reversion (ranging markets, ADX<30)
  5. RSI Divergence (reversal catching, 4h timeframe)
Simulates trades with a virtual $500 balance.
NO real orders are ever placed.

Usage:
    pip install -r requirements.txt
    python bot.py
"""
import sys
import os
import time

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on shell environment
import logging
import signal
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from utils.logger import setup_logging, log_daily_summary
from utils.kraken_client import KrakenClient
from utils.risk_manager import RiskManager
from strategies.grid import GridBot
from strategies.sentiment import SentimentSwing
from strategies.ema_macd import EmaMacdMomentum
from strategies.bollinger import BollingerMeanReversion
from strategies.rsi_divergence import RsiDivergence
from trainer.engine import run_cycle, load_training_state, save_training_state
from manager.health import full_health_check, format_health_report
from manager.researcher import run_full_research, format_research_report

logger = logging.getLogger("cryptobot.main")

# ── Graceful shutdown ────────────────────────────────────────────────────
_running = True

def _shutdown(sig, frame):
    global _running
    logger.info("Shutdown signal received — stopping bot...")
    _running = False

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def main():
    setup_logging()
    logger.info("=" * 60)
    logger.info("CryptoBot Paper Trading Bot starting")
    logger.info("  Balance: $%.2f (virtual)", config.INITIAL_BALANCE)
    logger.info("  Pair: %s", config.PAIR_DISPLAY)
    logger.info("  Interval: %ds", config.CHECK_INTERVAL_SECONDS)
    logger.info("  Mode: PAPER TRADING ONLY — no real orders")
    logger.info("=" * 60)

    # Initialize components
    kraken = KrakenClient()
    risk = RiskManager()
    grid = GridBot(kraken, risk)
    sentiment = SentimentSwing(kraken, risk)
    ema_macd = EmaMacdMomentum(kraken, risk)
    bollinger = BollingerMeanReversion(kraken, risk)
    rsi_div = RsiDivergence(kraken, risk)

    # Track daily summary
    last_summary_date = None
    tick_count = 0

    # Training engine state
    training_state = load_training_state()
    training_interval_ticks = 12  # run trainer every 12 ticks (~60min at 5min ticks)
    last_training_tick = 0

    # Health check & research intervals
    health_interval_ticks = 36   # health check every 36 ticks (~3h)
    last_health_tick = 0
    research_interval_ticks = 72  # full research every 72 ticks (~6h)
    last_research_tick = 0

    while _running:
        try:
            tick_count += 1
            ticker = kraken.get_ticker()
            if not ticker:
                logger.warning("Could not fetch price — retrying in %ds",
                               config.CHECK_INTERVAL_SECONDS)
                time.sleep(config.CHECK_INTERVAL_SECONDS)
                continue

            price = ticker["last"]
            logger.info("Tick #%d | BTC/USD: $%.2f | Bid: $%.2f | Ask: $%.2f | Balance: $%.2f",
                        tick_count, price, ticker["bid"], ticker["ask"], risk.balance)

            # ── Check existing positions for SL/TP ───────────────────────
            closed = risk.check_stop_loss_take_profit(price)
            for pos in closed:
                from utils.logger import log_trade_to_md
                log_trade_to_md(pos)

            # ── Run strategies ───────────────────────────────────────────
            if not risk.is_paused:
                # Grid bot: reinitialize if price moved too far
                if grid.should_reinitialize(price):
                    grid.initialize(price)

                grid_actions = grid.evaluate(price)
                sentiment_actions = sentiment.evaluate(price)
                ema_actions = ema_macd.evaluate(price)
                boll_actions = bollinger.evaluate(price)
                rsi_actions = rsi_div.evaluate(price)

                for name, acts in [("Grid", grid_actions), ("Sentiment", sentiment_actions),
                                   ("EMA/MACD", ema_actions), ("Bollinger", boll_actions),
                                   ("RSI Div", rsi_actions)]:
                    if acts:
                        logger.info("%s: %d actions this tick", name, len(acts))
            else:
                logger.warning("Trading PAUSED: %s", risk.pause_reason)

            # ── Recursive training engine ───────────────────────────
            if tick_count - last_training_tick >= training_interval_ticks:
                try:
                    logger.info("─" * 40 + " TRAINING CYCLE " + "─" * 40)
                    report = run_cycle(kraken, training_state)
                    adj_count = report["adjustments"].get("total", 0)
                    if adj_count > 0:
                        logger.info("Trainer tuned %d parameters this cycle", adj_count)
                    last_training_tick = tick_count
                except Exception as te:
                    logger.error("Training cycle failed: %s", te)
                    last_training_tick = tick_count

            # ── Health check (manager) ────────────────────────────────────────
            if tick_count - last_health_tick >= health_interval_ticks:
                try:
                    health = full_health_check()
                    if health["overall"] in ("critical", "error"):
                        logger.error("HEALTH ALERT:\n%s", format_health_report(health))
                    elif health["overall"] == "warning":
                        logger.warning("Health warnings:\n%s", format_health_report(health))
                    else:
                        logger.info("Health check: %s", health["overall"])
                    last_health_tick = tick_count
                except Exception as he:
                    logger.error("Health check failed: %s", he)
                    last_health_tick = tick_count

            # ── Research sweep ────────────────────────────────────────────────
            if tick_count - last_research_tick >= research_interval_ticks:
                try:
                    logger.info("─" * 40 + " RESEARCH SWEEP " + "─" * 40)
                    ohlc_data = kraken.get_ohlc(interval=60, count=100)
                    research = run_full_research(ohlc_data)
                    if research["total_findings"] > 0:
                        logger.info("Research: %d findings\n%s",
                                    research["total_findings"],
                                    format_research_report(research))
                    else:
                        logger.info("Research sweep: no actionable findings")
                    last_research_tick = tick_count
                except Exception as re_err:
                    logger.error("Research sweep failed: %s", re_err)
                    last_research_tick = tick_count

            # ── Daily summary ────────────────────────────────────────────
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if last_summary_date != today and datetime.now(timezone.utc).hour >= 23:
                summary = risk.get_daily_summary()
                log_daily_summary(summary)
                last_summary_date = today
                logger.info("Daily summary: P&L=$%+.2f | Balance=$%.2f | Win rate=%.0f%%",
                            summary["daily_pnl"], summary["balance"], summary["win_rate"])

            # ── Sleep until next tick ────────────────────────────────────
            logger.debug("Sleeping %ds until next tick...", config.CHECK_INTERVAL_SECONDS)
            # Sleep in 1s increments so we can catch shutdown signals
            for _ in range(config.CHECK_INTERVAL_SECONDS):
                if not _running:
                    break
                time.sleep(1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.exception("Unhandled error in main loop: %s", e)
            time.sleep(30)  # Back off on errors

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Bot stopped. Final balance: $%.2f", risk.balance)
    summary = risk.get_daily_summary()
    log_daily_summary(summary)
    risk.save_state()
    logger.info("State saved. Goodbye.")


if __name__ == "__main__":
    main()
