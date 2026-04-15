# CryptoBot — Risk Management Rules

## ABSOLUTE RULES (never override)

### Position Limits
- **Paper Phase (current):** Max 20% per trade ($100 on $500), 5 concurrent positions (relaxed for training data)
- **Live Phase (future):** Revert to 2% per trade, 3 concurrent
- No leverage above 2x (1x preferred in Phase 1-2)

### Loss Limits
- Stop-loss required on EVERY position — no exceptions
- **Paper Phase:** Daily 15% / Weekly 25% / Drawdown pause 30%
- **Live Phase:** Daily 5% / Weekly 10% / Drawdown pause 15%

### Asset Restrictions
- Phase 1-2: BTC and ETH ONLY
- No meme coins, no alt-coins under $1B market cap
- No futures/options until Phase 3 (if ever)
- No margin trading above 2x

### Withdrawal/Security
- API keys: trade-only permissions, NO withdrawal
- No agent can request fund transfers
- Simon is the only person who can deposit or withdraw
- All API keys rotated monthly

## ESCALATION PROTOCOL
1. **Yellow alert** (5% daily loss): Sentinel notifies CEO, reduces position sizes by 50%
2. **Red alert** (10% weekly loss): Sentinel pauses new trades, CEO reviews all open positions
3. **Emergency stop** (15% drawdown): Sentinel closes ALL positions, alerts Simon via Telegram
4. **Manual override**: Simon can pause/resume at any time via Telegram command

## PERFORMANCE TRACKING
- Log every trade in TRADE_LOG.md
- Daily P&L summary in memory/YYYY-MM-DD.md
- Weekly performance report to Simon (win rate, total P&L, max drawdown, Sharpe ratio)
- Monthly strategy review: keep, modify, or kill each active strategy
