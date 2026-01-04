# GOLD TRADING BOT - COMPLETE SYSTEM DOCUMENTATION
## Full Context for Claude Code

---

## PROJECT OVERVIEW

**Objective:** Automated gold (XAUUSD) trading system targeting 4X account growth in 30 days

**Status:** LIVE on Capital.com Demo Accounts

**Created:** January 3, 2026

---

## CREDENTIALS & API KEYS

### Capital.com API
```
API Key: 3F3RHbKsBbivSLYe
Email: saurav.patr@gmail.com
Password: Cl@ud#123
Base URL: https://demo-api-capital.backend-capital.com
API Expiry: January 3, 2027
```

### Trading Accounts
```
Account 1 (Fixed R:R Strategy):
  Name: test patro
  ID: 303527589371466014
  Balance: 50,838.00 AED (~$13,800 USD)

Account 2 (Adaptive Strategy):
  Name: adaptive claude
  ID: 303621563255902494
  Balance: 54,000.00 AED (~$14,700 USD)
```

### Telegram Notifications
```
Bot Name: Capital_demo_bot
Bot Username: @XaUdemo_bot
Bot Token: 8376345331:AAHWoZzkqT26cyeRPGa8MfcaVZWvTcan9lU
Chat ID: 7831118282
```

### Database (Historical Data)
```
Host: 165.227.191.236
Database: trading_bot
User: trader
Password: TradingBot2026Secure!
Tables: price_data, signals, trades
```

---

## VERIFIED TRADING SETUPS (Backtested)

### Performance Summary from 30-Day Backtest
- Total Signals: 64
- Best Strategy: 1:5 R:R Fixed Target
- Result: $3,000 → $10,740 (258% gain)
- Win Rate @ 1:5: 39%

### TIER A: HIGH CONFIDENCE SETUPS

| Setup | Timeframe | Direction | Win Rate | Avg MFE | Median Duration |
|-------|-----------|-----------|----------|---------|-----------------|
| 5min: bear_fvg + mon | 5min | SELL | 56% | 20.9R | 10 min |
| 1H: mon + rsi<40 | 1H | BUY | 50% | 2.3R | 3 hrs |
| 1H: mon + rsi<30 | 1H | BUY | 56% | 2.2R | 3 hrs |

### TIER B: STANDARD SETUPS

| Setup | Timeframe | Direction | Win Rate | Avg MFE | Median Duration |
|-------|-----------|-----------|----------|---------|-----------------|
| 15min: bull_bos + rsi<20 | 15min | BUY | 35% | 8.7R | 45 min |
| 15min: green + rsi<20 | 15min | BUY | 36% | 7.4R | 52 min |
| 5min: bear_fvg + wed | 5min | SELL | 35% | 1.9R | 32 min |
| 4H: bull_eng + rsi<30 | 4H | BUY | 37% | 8.2R | 16 hrs |
| 1D: bull_pin + stoch<30 | 1D | BUY | 45% | 9.9R | 2 days |

### TIER C: RUNNER SETUPS (Low Risk, High Reward)

| Setup | Timeframe | Direction | Win Rate | Avg MFE | Median Duration |
|-------|-----------|-----------|----------|---------|-----------------|
| 1H: stoch>80 + sun | 1H | SELL | 35% | 17.5R | 3 hrs |
| 1H: rsi<20 + sun | 1H | BUY | 41% | N/A | 3 hrs |

---

## STRATEGY CONFIGURATIONS

### Bot 1: FIXED_RR (Account: test patro)
```python
# All setups use same parameters
TARGET_RR = 5.0      # 1:5 Risk:Reward
RISK_PCT = 0.03      # 3% per trade
STOP_ATR = 1.0       # 1 ATR stop loss
MAX_TRADES = 4       # Max open positions
```

### Bot 2: ADAPTIVE (Account: adaptive claude)
```python
# Tier-based parameters
TIER_A:  target_rr=2.5-3.0, risk=3-4%, stop=1.0 ATR
TIER_B:  target_rr=5.0,     risk=2-3%, stop=1.0 ATR
TIER_C:  target_rr=10.0,    risk=1%,   stop=2.0 ATR
```

---

## FILE STRUCTURE
```
/home/trader/
├── ultimate_trading_system.py    # Main bot code
├── capital_both_accounts.json    # Capital.com credentials
├── telegram_config.json          # Telegram settings
├── start_bot1.sh                 # Launcher for Bot 1
├── start_bot2.sh                 # Launcher for Bot 2
├── LAUNCH_BOTS.sh               # Start both bots
├── monitor.sh                    # Status monitor
├── bot1.log                      # Bot 1 console output
├── bot2.log                      # Bot 2 console output
├── fixed_rr_detailed.log         # Bot 1 detailed logs
├── adaptive_detailed.log         # Bot 2 detailed logs
└── TRADING_BOT_FULL_CONTEXT.md  # This file
```

---

## SETUP CONDITIONS EXPLAINED

### Indicators Used
```python
RSI (14 period):
  - rsi<20: Extreme oversold
  - rsi<30: Oversold
  - rsi<40: Mild oversold

Stochastic (14 period):
  - stoch>80: Overbought
  - stoch<30: Oversold

ATR (14 period):
  - Used for stop loss and target calculation
  - Stop = 1 ATR (or 2 ATR for runners)
  - Target = ATR × R:R ratio
```

### Pattern Detection
```python
BOS (Break of Structure):
  - bull_bos: Current high > max(last 20 highs)
  - bear_bos: Current low < min(last 20 lows)

FVG (Fair Value Gap):
  - bull_fvg: candle[2].high < candle[0].low
  - bear_fvg: candle[2].low > candle[0].high

Engulfing:
  - bull_eng: Prev bearish, current bullish, body engulfs

Pin Bar:
  - bull_pin: Lower wick > 2× body, small upper wick
```

### Day Filters
```python
mon = Monday    # Multiple setups active
wed = Wednesday # bear_fvg setup
sun = Sunday    # stoch>80 reversal setup
```

---

## EXPECTED PERFORMANCE

### Monthly Projections (Based on Backtest)
```
Signals per month: ~60
Win rate @ 1:5: 39%
Winners: 23 × 5R = 115R
Losers: 37 × -1R = -37R
Net: +78R per month

At 3% risk per trade:
Month 1: $3,000 → $10,000+
Month 2: $10,000 → $33,000+
Month 3: $33,000 → $110,000+
```

### Risk Management Rules
```
Max Daily Drawdown: 15% (stop trading)
Max Weekly Drawdown: 25% (stop trading)
Max Single Trade Risk: 5%
Max Open Trades: 4
Max Same-Direction: 2
```

---

## CRITICAL REMINDERS

1. **Weekend**: Market closed Sat-Sun (bots idle)
2. **Session Refresh**: Every 8 minutes (auto)
3. **Cooldown**: 30-60 min between same setup signals
4. **Day-Specific**: Most setups only trigger Mon/Wed/Sun

---

## COMMANDS
```bash
# Start both bots
/home/trader/LAUNCH_BOTS.sh

# Monitor status
/home/trader/monitor.sh

# Watch Bot 1 live
tail -f /home/trader/bot1.log

# Watch Bot 2 live
tail -f /home/trader/bot2.log

# Stop all bots
pkill -f ultimate_trading_system

# Check if bots running
ps aux | grep ultimate_trading
```

---

## TELEGRAM ALERTS

You will receive:
- Trade entry notifications
- Trade exit notifications
- Daily performance reports
- Critical alerts (drawdown limits)
- Learning insights

---

## KEY DISCOVERIES FROM BACKTESTING

1. **1:5 R:R beats Runner strategy** in 30-day period
   - 1:5 made $10,740 vs Runner lost $1,950

2. **Monday is the best day** for gold trading
   - Multiple high-WR setups trigger

3. **RSI < 20 is powerful** confirmation
   - Significantly increases win rate

4. **FVG (Fair Value Gap)** is most reliable pattern
   - Especially on Monday and Wednesday

5. **Speed matters** - Most winners hit target in hours
   - 5min setups: 10-30 min median
   - 15min setups: 45-60 min median
   - 1H setups: 3 hrs median

6. **Adaptive may outperform Fixed** in volatile markets
   - Takes quick profits on high-confidence setups
   - Lets runners run on low-confidence setups

---

## NOTES FOR CLAUDE CODE

- All credentials are for DEMO accounts (safe to test)
- Bot runs on DigitalOcean VPS at 165.227.191.236
- Historical data in PostgreSQL (same server)
- Telegram notifications working and verified
- Both bots are LIVE and scanning for signals
- Next expected signals: Sunday (stoch setup) or Monday (multiple)

---

## GOAL

**4X the account in 30 days while:**
- Keeping drawdown under 15% daily
- Logging every trade with rationale
- Learning and adapting from results
- Sending real-time updates via Telegram

---

*Last Updated: January 3, 2026 20:22 UTC+4*
