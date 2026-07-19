"""Data pipeline: Postgres Spine loader, Capital.com fetcher, synthetic generator.

Three sources, one output shape: a DataFrame with columns
[timestamp, open, high, low, close, volume] sorted ascending.
"""

import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import config


# --- Postgres (Spine) -----------------------------------------------------

def load_db(instrument, timeframe, days):
    """Load candles from the trading_bot Spine (price_data table)."""
    import psycopg2

    conn = psycopg2.connect(**config.db_config())
    try:
        df = pd.read_sql(
            """
            SELECT timestamp, open, high, low, close
            FROM price_data
            WHERE symbol = %(symbol)s
              AND timeframe = %(timeframe)s
              AND timestamp >= NOW() - INTERVAL '1 day' * %(days)s
            ORDER BY timestamp
            """,
            conn,
            params={"symbol": instrument, "timeframe": timeframe, "days": days},
        )
    finally:
        conn.close()

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    if "volume" not in df.columns:
        df["volume"] = np.nan
    return df


def save_db(df, instrument, timeframe):
    """Upsert candles into price_data. Values converted to Python floats
    before insert — numpy types make psycopg2 fail with 'schema np does
    not exist'."""
    import psycopg2

    conn = psycopg2.connect(**config.db_config())
    try:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO price_data (symbol, timeframe, timestamp, open, high, low, close)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE
                    SET open = EXCLUDED.open, high = EXCLUDED.high,
                        low = EXCLUDED.low, close = EXCLUDED.close
                    """,
                    (
                        instrument,
                        timeframe,
                        row["timestamp"],
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                    ),
                )
        conn.commit()
    finally:
        conn.close()


# --- Capital.com ----------------------------------------------------------

class CapitalClient:
    """Minimal Capital.com REST client with session-token refresh.

    Session tokens expire after ~10 minutes; every request path goes
    through ensure_auth() which re-authenticates at the 9-minute mark.
    """

    AUTH_REFRESH_SECONDS = 540

    def __init__(self, cfg=None):
        self.cfg = cfg or config.capital_config()
        self.cst = None
        self.security_token = None
        self.last_auth = 0.0

    def authenticate(self):
        import requests

        resp = requests.post(
            f"{self.cfg['base_url']}/api/v1/session",
            headers={"X-CAP-API-KEY": self.cfg["api_key"]},
            json={
                "identifier": self.cfg["identifier"],
                "password": self.cfg["password"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        self.cst = resp.headers["CST"]
        self.security_token = resp.headers["X-SECURITY-TOKEN"]
        self.last_auth = time.time()

    def ensure_auth(self):
        if time.time() - self.last_auth > self.AUTH_REFRESH_SECONDS:
            self.authenticate()

    def _headers(self):
        return {"CST": self.cst, "X-SECURITY-TOKEN": self.security_token}

    def fetch_candles(self, instrument, timeframe, days):
        """Fetch OHLC history. Returns the standard candle DataFrame."""
        import requests

        self.ensure_auth()
        resolution = config.TIMEFRAMES[timeframe]
        params = {
            "resolution": resolution,
            "max": 1000,
            "from": (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
            "to": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        }
        resp = requests.get(
            f"{self.cfg['base_url']}/api/v1/prices/{instrument}",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        prices = resp.json().get("prices", [])

        rows = []
        for p in prices:
            rows.append({
                "timestamp": pd.Timestamp(p["snapshotTimeUTC"]),
                "open": (p["openPrice"]["bid"] + p["openPrice"]["ask"]) / 2,
                "high": (p["highPrice"]["bid"] + p["highPrice"]["ask"]) / 2,
                "low": (p["lowPrice"]["bid"] + p["lowPrice"]["ask"]) / 2,
                "close": (p["closePrice"]["bid"] + p["closePrice"]["ask"]) / 2,
                "volume": p.get("lastTradedVolume", np.nan),
            })
        return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


# --- Synthetic (development / engine validation) --------------------------

def synthetic_ohlc(n=5000, timeframe="5min", start_price=2650.0, seed=42):
    """Regime-switching random walk with volatility clustering.

    Not a market model — exists so the feature pipeline and backtest
    engine can be exercised end-to-end without DB/API access. Regimes
    alternate between trend-up, trend-down and chop so structure
    features (BOS, sweeps, FVGs) actually occur.
    """
    rng = np.random.default_rng(seed)
    minutes = config.TIMEFRAME_MINUTES[timeframe]

    drift = 0.0
    vol = 1.0
    closes = np.empty(n)
    price = start_price
    for i in range(n):
        if rng.random() < 0.005:  # regime switch ~every 200 candles
            drift = rng.choice([-0.08, 0.0, 0.08])
            vol = rng.choice([0.6, 1.0, 1.8])
        price += drift + rng.normal(0, vol)
        closes[i] = price

    opens = np.roll(closes, 1)
    opens[0] = start_price
    spread = np.abs(rng.normal(0, 0.8, n)) + 0.2
    highs = np.maximum(opens, closes) + spread * rng.random(n)
    lows = np.minimum(opens, closes) - spread * rng.random(n)
    volume = rng.integers(500, 5000, n).astype(float)

    ts = pd.date_range("2026-01-05", periods=n, freq=f"{minutes}min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volume,
    })


def load(source, instrument, timeframe, days, seed=42):
    """Unified loader. source: 'db' | 'capital' | 'synthetic'."""
    if source == "db":
        return load_db(instrument, timeframe, days)
    if source == "capital":
        return CapitalClient().fetch_candles(instrument, timeframe, days)
    if source == "synthetic":
        candles_per_day = max(1, 1440 // config.TIMEFRAME_MINUTES[timeframe])
        return synthetic_ohlc(n=days * candles_per_day, timeframe=timeframe, seed=seed)
    raise ValueError(f"unknown source: {source}")
