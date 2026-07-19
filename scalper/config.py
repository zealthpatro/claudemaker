"""Central configuration for the self-learning scalper.

Credentials are read from FULL_CONFIG.json at the repo root (or the path in
SCALPER_CONFIG env var) so they live in one place.
"""

import json
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("SCALPER_CONFIG", os.path.join(_REPO_ROOT, "FULL_CONFIG.json"))


def load_full_config(path=CONFIG_PATH):
    with open(path) as f:
        return json.load(f)


# --- Instruments ---------------------------------------------------------
GOLD = "XAUUSD"
SILVER = "XAGUSD"
INSTRUMENTS = [GOLD, SILVER]

# HOUSE RULE: SELL signals on silver consistently lose (-7R to -25R live).
# Any strategy emitting a SELL on these instruments is hard-blocked.
BUY_ONLY_INSTRUMENTS = {SILVER}

# HOUSE RULE: every gold SELL requires RSI > this on the signal candle.
# Removing this filter previously cost 24,351 AED.
SELL_RSI_FLOOR = 55.0

# Capital.com resolution names per timeframe key used in the DB.
TIMEFRAMES = {
    "5min": "MINUTE_5",
    "15min": "MINUTE_15",
    "30min": "MINUTE_30",
    "1h": "HOUR",
    "4h": "HOUR_4",
    "1d": "DAY",
}

# Minutes per timeframe (used for trades/day metrics and session math).
TIMEFRAME_MINUTES = {
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# --- Risk (SCALPER_RESEARCH_PLAN.md Phase 6) -----------------------------
RISK_RULES = {
    "per_trade_risk": 0.02,       # 2% base risk per trade
    "daily_loss_limit": 0.05,     # stop trading for the day at -5%
    "weekly_loss_limit": 0.10,    # stop trading for the week at -10%
    "max_positions": 3,
    "scale_up_after_wins": 5,     # 5 consecutive wins -> 2.5%
    "scale_up_risk": 0.025,
    "scale_down_after_losses": 3, # 3 consecutive losses -> 1%
    "scale_down_risk": 0.01,
    "min_units": 1,               # Capital.com rejects size < 1 unit
}

# --- Sessions (UTC hours) -------------------------------------------------
SESSIONS = {
    "asia": (0, 7),
    "london": (7, 12),
    "overlap": (12, 16),   # London/NY overlap
    "new_york": (16, 21),
}

# ICT kill zones: the windows around London and NY opens where the
# highest-probability moves originate.
KILL_ZONES = [(7, 10), (12, 15)]

# --- Learning loop --------------------------------------------------------
LEARNER_STATE_PATH = os.path.join(_REPO_ROOT, "scalper_state", "learner.json")


def db_config():
    """Postgres connection kwargs from FULL_CONFIG.json."""
    cfg = load_full_config()["database"]
    return {
        "host": cfg["host"],
        "database": cfg["dbname"],
        "user": cfg["user"],
        "password": cfg["password"],
    }


def capital_config():
    """Capital.com API credentials from FULL_CONFIG.json."""
    cfg = load_full_config()["capital_com"]
    return {
        "api_key": cfg["api_key"],
        "identifier": cfg["identifier"],
        "password": cfg["password"],
        "base_url": cfg["base_url"],
    }
