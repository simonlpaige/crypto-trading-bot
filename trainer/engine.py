"""
Training Engine — the recursive self-improvement loop.

Cycle:
  1. ANALYZE  — score each strategy's recent performance
  2. RESEARCH — fetch market context (volatility regime, sentiment)
  3. DIAGNOSE — map issues to root causes
  4. TUNE     — adjust one parameter per strategy within safe bounds
  5. LOG      — record everything
  6. WAIT     — sleep, then repeat

Safety:
  - Parameters never leave research-backed bounds
  - Max one change per strategy per cycle
  - Max 20% range movement per cycle
  - All changes logged with full before/after
  - Reverts if performance degrades over 3 consecutive cycles
"""
import json
import logging
import math
import os
import time
import signal
from datetime import datetime

import config
from trainer.analyzer import full_analysis
from trainer.researcher import build_market_context, RESEARCH_PARAMS
from trainer.tuner import generate_adjustments, apply_adjustments, load_overrides
from utils.kraken_client import KrakenClient

logger = logging.getLogger("cryptobot.trainer.engine")

TRAINING_STATE_FILE = os.path.join(config.BOT_DIR, "trainer", "training_state.json")
TRAINING_REPORT_DIR = os.path.join(config.BOT_DIR, "trainer", "reports")

_running = True

def _shutdown(sig, frame):
    global _running
    logger.info("Training engine shutdown signal received")
    _running = False

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def load_training_state() -> dict:
    if os.path.exists(TRAINING_STATE_FILE):
        with open(TRAINING_STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "cycles_completed": 0,
        "total_adjustments": 0,
        "consecutive_degradations": 0,
        "last_cycle": None,
        "last_pnl_snapshot": None,
        "revert_count": 0,
    }


def save_training_state(state: dict):
    os.makedirs(os.path.dirname(TRAINING_STATE_FILE), exist_ok=True)
    with open(TRAINING_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def save_report(cycle: int, report: dict):
    """Save a per-cycle report as JSON."""
    os.makedirs(TRAINING_REPORT_DIR, exist_ok=True)
    path = os.path.join(TRAINING_REPORT_DIR, f"cycle_{cycle:04d}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report saved: %s", path)


def check_for_revert(training_state: dict, current_pnl: float) -> bool:
    """
    If PnL has degraded for 3 consecutive cycles, revert all overrides
    to defaults and reset.
    """
    last_pnl = training_state.get("last_pnl_snapshot")
    if last_pnl is not None and current_pnl < last_pnl:
        training_state["consecutive_degradations"] += 1
        logger.warning("Performance degraded: $%.4f → $%.4f (streak: %d)",
                       last_pnl, current_pnl, training_state["consecutive_degradations"])
    else:
        training_state["consecutive_degradations"] = 0

    if training_state["consecutive_degradations"] >= 3:
        logger.warning("3 consecutive degradations — REVERTING all overrides to defaults")
        # Clear overrides file
        overrides_file = os.path.join(config.BOT_DIR, "trainer", "param_overrides.json")
        if os.path.exists(overrides_file):
            with open(overrides_file, "w") as f:
                json.dump({}, f)
        training_state["consecutive_degradations"] = 0
        training_state["revert_count"] = training_state.get("revert_count", 0) + 1
        return True
    return False


def simulate_backtest_trades(ohlc: list, strategies: list) -> list:
    """Simulate what-if trades from recent OHLC data for zero-trade periods.

    When no real trades have closed, this generates synthetic outcomes so the
    analyzer has something to learn from. Rough but better than silence.

    Logic per strategy:
    - ema_macd / rsi_divergence: enter at open, exit at close each bar
    - sentiment: skip (no meaningful intra-bar signal)
    - bollinger: enter when bar touches lower band, exit at SMA
    - grid: not simulated (grid requires state)

    Returns list of synthetic position-like dicts compatible with analyzer.
    """
    if not ohlc or len(ohlc) < 10:
        return []

    synthetic = []
    now = datetime.utcnow().isoformat()

    # ── EMA/MACD: simple momentum simulation ─────────────────────────────
    if "ema_macd" in strategies:
        # Use last 20 bars; enter long if close > open (green candle), short otherwise
        for i, bar in enumerate(ohlc[-20:]):
            side = "buy" if bar["close"] > bar["open"] else "sell"
            entry = bar["open"]
            exit_price = bar["close"]
            pnl_pct = (exit_price - entry) / entry if side == "buy" else (entry - exit_price) / entry
            pnl = pnl_pct * 10.0  # small notional ($10 per sim trade)
            synthetic.append({
                "strategy": "ema_macd",
                "side": side,
                "entry_price": entry,
                "exit_price": exit_price,
                "pnl": round(pnl, 4),
                "opened_at": now,
                "closed_at": now,
                "simulated": True,
            })

    # ── RSI Divergence: similar bar-by-bar logic ──────────────────────────
    if "rsi_divergence" in strategies:
        closes = [c["close"] for c in ohlc]
        # Compute a rough 14-period RSI for each bar
        for i in range(14, len(ohlc[-20:]) + 14):
            if i >= len(closes):
                break
            gains = [max(closes[j] - closes[j - 1], 0) for j in range(i - 13, i + 1)]
            losses = [max(closes[j - 1] - closes[j], 0) for j in range(i - 13, i + 1)]
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rs = avg_gain / avg_loss if avg_loss > 0 else 100
            rsi = 100 - (100 / (1 + rs))

            bar = ohlc[i] if i < len(ohlc) else ohlc[-1]
            if rsi < 40:  # oversold → simulate long
                side = "buy"
                entry = bar["open"]
                # Simulate: exit after 2 bars or at low (whatever comes first)
                exit_bar = ohlc[min(i + 2, len(ohlc) - 1)]
                exit_price = exit_bar["close"]
            elif rsi > 60:  # overbought → simulate short
                side = "sell"
                entry = bar["open"]
                exit_bar = ohlc[min(i + 2, len(ohlc) - 1)]
                exit_price = exit_bar["close"]
            else:
                continue

            pnl_pct = (exit_price - entry) / entry if side == "buy" else (entry - exit_price) / entry
            pnl = pnl_pct * 10.0
            synthetic.append({
                "strategy": "rsi_divergence",
                "side": side,
                "entry_price": entry,
                "exit_price": exit_price,
                "pnl": round(pnl, 4),
                "opened_at": now,
                "closed_at": now,
                "simulated": True,
            })

    # ── Bollinger: enter near lower band, exit at SMA ─────────────────────
    if "bollinger" in strategies:
        closes = [c["close"] for c in ohlc]
        for i in range(20, len(ohlc)):
            window = closes[i - 20:i]
            sma = sum(window) / 20
            std = math.sqrt(sum((x - sma) ** 2 for x in window) / 20)
            lower_band = sma - 2 * std
            upper_band = sma + 2 * std

            bar = ohlc[i]
            if bar["low"] <= lower_band:  # touched lower band → long
                entry = lower_band
                exit_price = sma
                pnl_pct = (exit_price - entry) / entry
                pnl = pnl_pct * 10.0
                synthetic.append({
                    "strategy": "bollinger",
                    "side": "buy",
                    "entry_price": round(entry, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 4),
                    "opened_at": now,
                    "closed_at": now,
                    "simulated": True,
                })
            elif bar["high"] >= upper_band:  # touched upper band → short
                entry = upper_band
                exit_price = sma
                pnl_pct = (entry - exit_price) / entry
                pnl = pnl_pct * 10.0
                synthetic.append({
                    "strategy": "bollinger",
                    "side": "sell",
                    "entry_price": round(entry, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl": round(pnl, 4),
                    "opened_at": now,
                    "closed_at": now,
                    "simulated": True,
                })

    logger.info("Simulated %d backtest trades across %d strategies",
                len(synthetic), len(strategies))
    return synthetic


def inject_simulated_trades(analysis: dict, ohlc: list) -> dict:
    """Inject synthetic trades into analysis for strategies with no data.
    
    Patches the analysis dict in-place so generate_adjustments() has
    something to work with even before real trades close.
    """
    no_data_strats = [
        name for name, strat_analysis in analysis.get("strategies", {}).items()
        if strat_analysis.get("status") == "no_data"
    ]

    if not no_data_strats:
        return analysis  # Nothing to do

    logger.info("No closed trades for: %s — running simulated backtest", no_data_strats)
    sim_trades = simulate_backtest_trades(ohlc, no_data_strats)

    if not sim_trades:
        return analysis

    # Rebuild per-strategy analysis from simulated trades
    from trainer.analyzer import analyze_strategy as _analyze
    for strat in no_data_strats:
        strat_sims = [t for t in sim_trades if t["strategy"] == strat]
        if not strat_sims:
            continue

        wins = [t for t in strat_sims if t["pnl"] > 0]
        losses = [t for t in strat_sims if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in strat_sims)
        win_rate = len(wins) / len(strat_sims) * 100 if strat_sims else 0
        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        issues = []
        if win_rate < 50:
            issues.append(f"low_win_rate:{win_rate:.0f}%")
        if 0 < risk_reward < 1.3:
            issues.append(f"bad_risk_reward:{risk_reward:.2f}")

        analysis["strategies"][strat] = {
            "strategy": strat,
            "trade_count": len(strat_sims),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "risk_reward": round(risk_reward, 2) if risk_reward != float("inf") else 99.0,
            "max_drawdown": 0.0,
            "avg_hold_hours": 0.1,
            "sl_hits": 0,
            "tp_hits": 0,
            "long_win_rate": 0.0,
            "short_win_rate": 0.0,
            "issues": issues,
            "status": "simulated" if not issues else "simulated_needs_improvement",
            "note": "Synthetic backtest — no real trades closed yet",
        }
        # Update totals
        analysis["total_trades"] = sum(
            s.get("trade_count", 0) for s in analysis["strategies"].values()
        )
        analysis["total_pnl"] = round(sum(
            s.get("total_pnl", 0) for s in analysis["strategies"].values()
        ), 4)

    return analysis


def run_cycle(kraken: KrakenClient, training_state: dict) -> dict:
    """Execute one training cycle. Returns a report dict."""
    cycle_num = training_state["cycles_completed"] + 1
    logger.info("=" * 50)
    logger.info("TRAINING CYCLE #%d", cycle_num)
    logger.info("=" * 50)

    report = {
        "cycle": cycle_num,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # ── Step 1: ANALYZE ──────────────────────────────────────────────────
    logger.info("Step 1: Analyzing trade performance...")
    # Read lookback_days from meta_overrides (meta-learner can adjust this)
    _meta_lookback = 14
    try:
        _meta_overrides_path = os.path.join(config.BOT_DIR, "trainer", "meta_overrides.json")
        if os.path.exists(_meta_overrides_path):
            with open(_meta_overrides_path, "r") as _f:
                _meta_overrides_path = json.load(_f)
            _meta_lookback = int(_meta_overrides_path.get("lookback_days_analysis", 14))
    except Exception:
        pass
    analysis = full_analysis(lookback_days=_meta_lookback)
    report["analysis"] = analysis
    logger.info("  Total trades: %d | PnL: $%.4f | Issues: %s",
                analysis["total_trades"], analysis["total_pnl"], analysis["all_issues"])

    # ── Step 2: RESEARCH ─────────────────────────────────────────────────
    logger.info("Step 2: Fetching market context...")
    ohlc = kraken.get_ohlc(interval=60, count=100)

    # Inject simulated trades when no real ones have closed yet
    if analysis["total_trades"] == 0 and ohlc:
        logger.info("No closed trades yet — injecting simulated backtest data")
        analysis = inject_simulated_trades(analysis, ohlc)
        report["analysis"] = analysis
        report["simulation_used"] = True
        logger.info("  After simulation: %d synthetic trades", analysis["total_trades"])
    else:
        report["simulation_used"] = False

    market_context = build_market_context(ohlc)
    report["market_context"] = market_context
    fg = market_context.get("fear_greed", {})
    vol = market_context.get("volatility", {})
    logger.info("  Fear & Greed: %s (%s) | Volatility: %s | Recommendations: %s",
                fg.get("current", "?"), fg.get("classification", "?"),
                vol.get("regime", "?"), market_context.get("recommendations", []))

    # ── Always record discovery snapshot ─────────────────────────────────
    try:
        from trainer.discovery import record_snapshot
        record_snapshot(market_context, analysis, ohlc)
    except Exception as de:
        logger.error("Discovery snapshot failed: %s", de)

    # ── Step 3: CHECK FOR REVERT ─────────────────────────────────────────
    reverted = check_for_revert(training_state, analysis["total_pnl"])
    report["reverted"] = reverted
    if reverted:
        logger.warning("Overrides reverted to defaults this cycle")
        report["adjustments"] = {"applied": [], "total": 0, "reason": "reverted"}
    else:
        # ── Step 4: TUNE ─────────────────────────────────────────────────
        logger.info("Step 3: Generating parameter adjustments...")
        adjustments = generate_adjustments(analysis, market_context)
        report["proposed_adjustments"] = [
            {"strategy": a["strategy"], "param": a["param"],
             "old": a["old_value"], "new": a["new_value"], "reason": a["reason"]}
            for a in adjustments
        ]

        if adjustments:
            logger.info("Step 4: Applying %d adjustments...", len(adjustments))
            result = apply_adjustments(adjustments)
            report["adjustments"] = result
            training_state["total_adjustments"] += result["total"]
        else:
            logger.info("No adjustments needed this cycle")
            report["adjustments"] = {"applied": [], "total": 0}

    # ── Step 5: DISCOVER ─────────────────────────────────────────────────
    if cycle_num % 6 == 0:  # every 6th cycle (~6 hours at 60-min intervals)
        logger.info("Step 5: Running correlation discovery...")
        try:
            from trainer.discovery import scan_correlations, mine_patterns, propose_strategy, get_discovery_summary

            correlations = scan_correlations()
            patterns = mine_patterns()

            if correlations:
                report["top_correlations"] = correlations[:5]
                logger.info("  Top correlation: %s → %s (r=%.3f)",
                            correlations[0]["signal"], correlations[0]["target"],
                            correlations[0]["correlation"])

            if patterns:
                report["discovered_patterns"] = patterns[:3]
                logger.info("  Found %d patterns; top: %s (%.0f%% win rate, n=%d)",
                            len(patterns), patterns[0]["name"],
                            patterns[0]["win_rate"] * 100, patterns[0]["occurrences"])
                for p in patterns:
                    if p.get("confidence", 0) > 0.7:
                        proposal = propose_strategy(p)
                        if proposal:
                            logger.info("  Strategy proposed: %s", proposal["name"])

            summary = get_discovery_summary()
            report["discovery_summary"] = summary
            logger.info("  Discovery: %d history entries, %d total proposals",
                        summary.get("signal_history_entries", 0),
                        summary.get("total_proposals", 0))
        except Exception as disc_err:
            logger.error("Discovery step failed: %s", disc_err)

    # ── Update state ─────────────────────────────────────────────────────
    training_state["cycles_completed"] = cycle_num
    training_state["last_cycle"] = datetime.utcnow().isoformat()
    training_state["last_pnl_snapshot"] = analysis["total_pnl"]

    save_report(cycle_num, report)
    save_training_state(training_state)

    # ── Step 6: META-LEARNING ─────────────────────────────────────────────
    # Record this cycle's results for meta-evaluation.
    # Run a full meta-cycle every 12th training cycle (~12 hours).
    try:
        from trainer.meta_learner import record_training_outcome, run_meta_cycle, load_meta_state

        # Always record the outcome so meta-learner has data to learn from
        record_training_outcome(report)

        if cycle_num % 12 == 0:
            logger.info("Step 6: Running meta-learning cycle (every 12th cycle)...")
            meta_state = load_meta_state()
            meta_report = run_meta_cycle(training_state)
            report["meta_learning"] = meta_report

            if meta_report.get("hyperparameter_changes"):
                for change in meta_report["hyperparameter_changes"]:
                    logger.info("META: %s: %s → %s (%s)",
                                change["param"], change["old"], change["new"], change["reason"])
            if meta_report.get("reset_to_defaults"):
                logger.warning("META: reset all hyperparameters to defaults (recursive failure recovery)")
        else:
            logger.debug("Step 6: meta-learning outcome recorded (meta-cycle every 12th)")
    except Exception as me:
        logger.error("Meta-learning failed: %s", me)

    logger.info("Cycle #%d complete. Adjustments: %d | Balance: $%.2f",
                cycle_num, report["adjustments"].get("total", 0), analysis["balance"])

    return report


def run_forever(interval_minutes: int = 60):
    """
    Main entry point: run the training loop forever.
    
    Default: every 60 minutes.
    On a $500 paper account with 5-min ticks, this means the trainer
    evaluates ~12 data points per cycle and tunes accordingly.
    """
    logger.info("Training Engine starting (interval=%dm)", interval_minutes)
    kraken = KrakenClient()
    training_state = load_training_state()

    while _running:
        try:
            report = run_cycle(kraken, training_state)

            # Log summary
            adj_count = report["adjustments"].get("total", 0)
            if adj_count > 0:
                logger.info("Cycle summary: %d parameters tuned", adj_count)
                for a in report["adjustments"].get("applied", []):
                    logger.info("  → %s.%s: %s → %s", a["strategy"], a["param"],
                                a["old_value"], a["new_value"])

        except Exception as e:
            logger.exception("Training cycle failed: %s", e)

        # Sleep in small increments for graceful shutdown
        for _ in range(interval_minutes * 60):
            if not _running:
                break
            time.sleep(1)

    logger.info("Training Engine stopped. Cycles: %d, Total adjustments: %d",
                training_state["cycles_completed"], training_state["total_adjustments"])


def run_once():
    """Run a single training cycle and exit (for testing)."""
    kraken = KrakenClient()
    training_state = load_training_state()
    report = run_cycle(kraken, training_state)
    return report


if __name__ == "__main__":
    from utils.logger import setup_logging
    setup_logging()
    
    import sys
    if "--once" in sys.argv:
        report = run_once()
        print(json.dumps(report, indent=2))
    else:
        run_forever()
