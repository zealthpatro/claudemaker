"""Feature engineering (SCALPER_RESEARCH_PLAN.md Phase 2).

Everything a strategy is allowed to see lives in `prev_*` columns: the
value of each feature on the PREVIOUS, fully closed candle. Strategies
must never read the unshifted columns — the current candle is still
forming when the entry decision is made (backtest methodology Rule:
signal data comes from df.iloc[i-1], entry at candle i's open).
"""

import numpy as np
import pandas as pd

from . import config

# Columns copied into prev_* for signal use.
SIGNAL_COLUMNS = [
    "open", "high", "low", "close",
    "rsi", "stoch_k", "atr", "adx",
    "ema9", "ema21", "ema50", "ema200",
    "macd_hist", "bb_width",
    "vwap", "vwap_upper", "vwap_lower",
    "swing_high_level", "swing_low_level",
    "bull_bos", "bear_bos", "choch",
    "sweep_low", "sweep_high",
    "bull_fvg", "bear_fvg",
    "bull_engulfing", "bear_engulfing", "bull_pin", "bear_pin", "inside_bar",
    "kill_zone", "session_asia", "session_london", "session_overlap", "session_ny",
    "regime",
]

BOOL_COLUMNS = {
    "bull_bos", "bear_bos", "choch", "sweep_low", "sweep_high",
    "bull_fvg", "bear_fvg", "bull_engulfing", "bear_engulfing",
    "bull_pin", "bear_pin", "inside_bar", "kill_zone",
    "session_asia", "session_london", "session_overlap", "session_ny",
}

SWING_LOOKBACK = 2  # fractal pivots: high/low vs 2 candles each side


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))


def _atr(df, period=14):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df, period=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def _vwap(df):
    """Daily-anchored VWAP with expanding ±2σ bands.

    Falls back to equal weighting when the feed has no volume (the Spine
    price_data table stores OHLC only).
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].fillna(1.0).replace(0, 1.0)
    day = pd.to_datetime(df["timestamp"]).dt.date

    pv = tp * vol
    cum_pv = pv.groupby(day).cumsum()
    cum_v = vol.groupby(day).cumsum()
    vwap = cum_pv / cum_v

    dev = tp - vwap
    # Expanding std within each day: uses only candles seen so far today.
    sd = dev.groupby(day).expanding().std().reset_index(level=0, drop=True)
    sd = sd.reindex(df.index).fillna(0.0)
    return vwap, vwap + 2 * sd, vwap - 2 * sd


def _swing_levels(df, k=SWING_LOOKBACK):
    """Last CONFIRMED fractal swing high/low as of each candle's close.

    A pivot at bar p needs k bars on each side, so it is only knowable at
    bar p+k — the level is recorded there, then forward-filled. No candle
    ever sees a pivot that hadn't been confirmed yet.
    """
    high, low = df["high"], df["low"]
    n = len(df)
    pivot_high = np.full(n, np.nan)
    pivot_low = np.full(n, np.nan)

    is_ph = pd.Series(True, index=df.index)
    is_pl = pd.Series(True, index=df.index)
    for off in range(1, k + 1):
        is_ph &= (high > high.shift(off)) & (high > high.shift(-off))
        is_pl &= (low < low.shift(off)) & (low < low.shift(-off))

    ph_idx = np.flatnonzero(is_ph.fillna(False).to_numpy())
    pl_idx = np.flatnonzero(is_pl.fillna(False).to_numpy())
    for p in ph_idx:
        if p + k < n:
            pivot_high[p + k] = high.iloc[p]
    for p in pl_idx:
        if p + k < n:
            pivot_low[p + k] = low.iloc[p]

    swing_high = pd.Series(pivot_high, index=df.index).ffill()
    swing_low = pd.Series(pivot_low, index=df.index).ffill()
    return swing_high, swing_low


def add_features(df):
    """Compute all features and the shifted prev_* signal columns."""
    df = df.copy().reset_index(drop=True)

    # --- momentum / trend / volatility indicators
    df["rsi"] = _rsi(df["close"])
    low14 = df["low"].rolling(14).min()
    high14 = df["high"].rolling(14).max()
    df["stoch_k"] = (100 * (df["close"] - low14) / (high14 - low14)).rolling(3).mean()
    df["atr"] = _atr(df)
    df["adx"] = _adx(df)
    for span in (9, 21, 50, 200):
        df[f"ema{span}"] = df["close"].ewm(span=span).mean()
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    macd = ema12 - ema26
    df["macd_hist"] = macd - macd.ewm(span=9).mean()
    sma20 = df["close"].rolling(20).mean()
    sd20 = df["close"].rolling(20).std()
    df["bb_width"] = (4 * sd20) / sma20

    # --- VWAP
    df["vwap"], df["vwap_upper"], df["vwap_lower"] = _vwap(df)

    # --- market structure
    df["swing_high_level"], df["swing_low_level"] = _swing_levels(df)
    level_high_prior = df["swing_high_level"].shift(1)
    level_low_prior = df["swing_low_level"].shift(1)

    df["bull_bos"] = (df["close"] > level_high_prior) & (df["close"].shift(1) <= level_high_prior)
    df["bear_bos"] = (df["close"] < level_low_prior) & (df["close"].shift(1) >= level_low_prior)

    direction = pd.Series(0, index=df.index)
    direction[df["bull_bos"]] = 1
    direction[df["bear_bos"]] = -1
    trend = direction.replace(0, np.nan).ffill()
    df["choch"] = (direction != 0) & trend.shift(1).notna() & (direction != trend.shift(1))

    # liquidity sweep: wick through the level, close back on the right side
    df["sweep_low"] = (df["low"] < level_low_prior) & (df["close"] > level_low_prior)
    df["sweep_high"] = (df["high"] > level_high_prior) & (df["close"] < level_high_prior)

    # fair value gaps (3-candle imbalance)
    df["bull_fvg"] = df["low"] > df["high"].shift(2)
    df["bear_fvg"] = df["high"] < df["low"].shift(2)

    # --- candle patterns
    body = (df["close"] - df["open"]).abs()
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    green = df["close"] > df["open"]
    red = ~green
    prev_green = green.shift(1).fillna(False).astype(bool)

    df["bull_engulfing"] = green & ~prev_green & (df["close"] >= df["open"].shift(1)) & (df["open"] <= df["close"].shift(1))
    df["bear_engulfing"] = red & prev_green & (df["close"] <= df["open"].shift(1)) & (df["open"] >= df["close"].shift(1))
    df["bull_pin"] = (lower_wick > 2 * body) & (lower_wick > upper_wick)
    df["bear_pin"] = (upper_wick > 2 * body) & (upper_wick > lower_wick)
    df["inside_bar"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))

    # --- time / session features (UTC)
    ts = pd.to_datetime(df["timestamp"], utc=True)
    hour = ts.dt.hour
    df["hour"] = hour
    df["day_of_week"] = ts.dt.dayofweek
    for name, (start, end) in config.SESSIONS.items():
        df[f"session_{'ny' if name == 'new_york' else name}"] = (hour >= start) & (hour < end)
    df["kill_zone"] = False
    for start, end in config.KILL_ZONES:
        df["kill_zone"] |= (hour >= start) & (hour < end)

    # --- regime (volatile > trending > ranging)
    atr_q80 = df["atr"].rolling(200, min_periods=50).quantile(0.8)
    df["regime"] = np.where(
        df["atr"] > atr_q80, "volatile",
        np.where(df["adx"] > 25, "trending", "ranging"),
    )

    # --- bias-free signal view: previous closed candle only
    for col in SIGNAL_COLUMNS:
        if col in BOOL_COLUMNS:
            df[f"prev_{col}"] = df[col].shift(1).fillna(False).astype(bool)
        else:
            df[f"prev_{col}"] = df[col].shift(1)

    # Drop indicator warmup; NaN swing levels are kept (comparisons against
    # NaN are False, so structure strategies simply stay flat until the
    # first pivot confirms).
    required = ["prev_rsi", "prev_atr", "prev_ema200", "prev_adx", "prev_stoch_k", "prev_bb_width"]
    return df.dropna(subset=required).reset_index(drop=True)
