"""
Technical Indicator Calculator
Computes all technical indicators used for signal generation
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """OHLCV candle data"""
    timestamp: any
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class IndicatorCalculator:
    """Calculate technical indicators from price data"""

    def __init__(self, default_periods: Dict[str, int] = None):
        self.periods = default_periods or {
            'rsi': 14,
            'stoch': 14,
            'stoch_smooth': 3,
            'atr': 14,
            'ema_fast': 9,
            'ema_medium': 21,
            'ema_slow': 50,
            'ema_trend': 200,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'bb_period': 20,
            'bb_std': 2.0,
            'vwap_period': 20
        }

    # ============= Moving Averages =============

    def sma(self, data: List[float], period: int) -> List[float]:
        """Simple Moving Average"""
        if len(data) < period:
            return [None] * len(data)

        result = [None] * (period - 1)
        for i in range(period - 1, len(data)):
            result.append(sum(data[i - period + 1:i + 1]) / period)
        return result

    def ema(self, data: List[float], period: int) -> List[float]:
        """Exponential Moving Average"""
        if len(data) < period:
            return [None] * len(data)

        multiplier = 2 / (period + 1)
        result = [None] * (period - 1)

        # First EMA is SMA
        first_ema = sum(data[:period]) / period
        result.append(first_ema)

        for i in range(period, len(data)):
            ema_val = (data[i] * multiplier) + (result[-1] * (1 - multiplier))
            result.append(ema_val)

        return result

    def calculate_emas(self, closes: List[float]) -> Dict[str, List[float]]:
        """Calculate all EMA variants"""
        return {
            'ema_9': self.ema(closes, self.periods['ema_fast']),
            'ema_21': self.ema(closes, self.periods['ema_medium']),
            'ema_50': self.ema(closes, self.periods['ema_slow']),
            'ema_200': self.ema(closes, self.periods['ema_trend'])
        }

    # ============= RSI =============

    def rsi(self, closes: List[float], period: int = None) -> List[float]:
        """Relative Strength Index"""
        period = period or self.periods['rsi']
        if len(closes) < period + 1:
            return [None] * len(closes)

        # Calculate price changes
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        # Initialize gains and losses
        gains = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]

        result = [None] * period

        # First average
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        if avg_loss == 0:
            result.append(100)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

        # Subsequent values using smoothed average
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - (100 / (1 + rs)))

        return result

    # ============= Stochastic =============

    def stochastic(self, highs: List[float], lows: List[float],
                   closes: List[float], k_period: int = None,
                   d_period: int = None) -> Tuple[List[float], List[float]]:
        """Stochastic Oscillator (%K and %D)"""
        k_period = k_period or self.periods['stoch']
        d_period = d_period or self.periods['stoch_smooth']

        if len(closes) < k_period:
            return [None] * len(closes), [None] * len(closes)

        stoch_k = [None] * (k_period - 1)

        for i in range(k_period - 1, len(closes)):
            highest_high = max(highs[i - k_period + 1:i + 1])
            lowest_low = min(lows[i - k_period + 1:i + 1])

            if highest_high == lowest_low:
                stoch_k.append(50)
            else:
                k = ((closes[i] - lowest_low) / (highest_high - lowest_low)) * 100
                stoch_k.append(k)

        stoch_d = self.sma([v for v in stoch_k if v is not None], d_period)
        # Pad with None to match length
        stoch_d = [None] * (len(stoch_k) - len(stoch_d)) + stoch_d

        return stoch_k, stoch_d

    # ============= ATR =============

    def atr(self, highs: List[float], lows: List[float],
            closes: List[float], period: int = None) -> List[float]:
        """Average True Range"""
        period = period or self.periods['atr']

        if len(closes) < 2:
            return [None] * len(closes)

        # Calculate True Range
        tr = [highs[0] - lows[0]]  # First TR is just H-L
        for i in range(1, len(closes)):
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            ))

        # ATR is smoothed TR
        if len(tr) < period:
            return [None] * len(closes)

        result = [None] * (period - 1)
        first_atr = sum(tr[:period]) / period
        result.append(first_atr)

        for i in range(period, len(tr)):
            atr_val = (result[-1] * (period - 1) + tr[i]) / period
            result.append(atr_val)

        return result

    # ============= MACD =============

    def macd(self, closes: List[float], fast: int = None,
             slow: int = None, signal: int = None) -> Tuple[List[float], List[float], List[float]]:
        """MACD (Line, Signal, Histogram)"""
        fast = fast or self.periods['macd_fast']
        slow = slow or self.periods['macd_slow']
        signal = signal or self.periods['macd_signal']

        ema_fast = self.ema(closes, fast)
        ema_slow = self.ema(closes, slow)

        macd_line = []
        for f, s in zip(ema_fast, ema_slow):
            if f is None or s is None:
                macd_line.append(None)
            else:
                macd_line.append(f - s)

        # Filter out None for signal calculation
        valid_macd = [v for v in macd_line if v is not None]
        signal_line_valid = self.ema(valid_macd, signal) if len(valid_macd) >= signal else []

        # Pad signal line
        signal_line = [None] * (len(macd_line) - len(signal_line_valid)) + signal_line_valid

        # Histogram
        histogram = []
        for m, s in zip(macd_line, signal_line):
            if m is None or s is None:
                histogram.append(None)
            else:
                histogram.append(m - s)

        return macd_line, signal_line, histogram

    # ============= Bollinger Bands =============

    def bollinger_bands(self, closes: List[float], period: int = None,
                        std_dev: float = None) -> Tuple[List[float], List[float], List[float]]:
        """Bollinger Bands (Upper, Middle, Lower)"""
        period = period or self.periods['bb_period']
        std_dev = std_dev or self.periods['bb_std']

        if len(closes) < period:
            return [None] * len(closes), [None] * len(closes), [None] * len(closes)

        middle = self.sma(closes, period)
        upper = []
        lower = []

        for i in range(len(closes)):
            if middle[i] is None:
                upper.append(None)
                lower.append(None)
            else:
                # Calculate standard deviation
                window = closes[max(0, i - period + 1):i + 1]
                std = np.std(window)
                upper.append(middle[i] + std_dev * std)
                lower.append(middle[i] - std_dev * std)

        return upper, middle, lower

    # ============= VWAP =============

    def vwap(self, highs: List[float], lows: List[float],
             closes: List[float], volumes: List[float]) -> List[float]:
        """Volume Weighted Average Price"""
        if not volumes or all(v == 0 for v in volumes):
            # Return SMA if no volume data
            return self.sma(closes, self.periods['vwap_period'])

        result = []
        cumulative_tpv = 0
        cumulative_volume = 0

        for i in range(len(closes)):
            typical_price = (highs[i] + lows[i] + closes[i]) / 3
            volume = volumes[i] if volumes[i] > 0 else 1

            cumulative_tpv += typical_price * volume
            cumulative_volume += volume

            if cumulative_volume > 0:
                result.append(cumulative_tpv / cumulative_volume)
            else:
                result.append(None)

        return result

    # ============= Pattern Detection =============

    def detect_engulfing(self, candles: List[Candle]) -> Optional[str]:
        """Detect bullish or bearish engulfing pattern"""
        if len(candles) < 2:
            return None

        prev = candles[-2]
        curr = candles[-1]

        # Bullish engulfing
        if (prev.close < prev.open and  # Previous is bearish
                curr.close > curr.open and  # Current is bullish
                curr.open <= prev.close and  # Opens at or below prev close
                curr.close >= prev.open):  # Closes at or above prev open
            return 'bull_engulfing'

        # Bearish engulfing
        if (prev.close > prev.open and  # Previous is bullish
                curr.close < curr.open and  # Current is bearish
                curr.open >= prev.close and  # Opens at or above prev close
                curr.close <= prev.open):  # Closes at or below prev open
            return 'bear_engulfing'

        return None

    def detect_pin_bar(self, candle: Candle, atr: float = None) -> Optional[str]:
        """Detect pin bar (hammer/shooting star)"""
        body = abs(candle.close - candle.open)
        upper_wick = candle.high - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.low
        total_range = candle.high - candle.low

        if total_range == 0:
            return None

        # Body should be small relative to total range
        if body / total_range > 0.3:
            return None

        # Bullish pin bar (hammer)
        if lower_wick > body * 2 and upper_wick < body:
            return 'bull_pin'

        # Bearish pin bar (shooting star)
        if upper_wick > body * 2 and lower_wick < body:
            return 'bear_pin'

        return None

    def detect_fvg(self, candles: List[Candle]) -> Optional[str]:
        """Detect Fair Value Gap"""
        if len(candles) < 3:
            return None

        c1, c2, c3 = candles[-3], candles[-2], candles[-1]

        # Bullish FVG: Gap between c1 high and c3 low
        if c3.low > c1.high:
            return 'bull_fvg'

        # Bearish FVG: Gap between c1 low and c3 high
        if c3.high < c1.low:
            return 'bear_fvg'

        return None

    def detect_bos(self, candles: List[Candle], lookback: int = 20) -> Optional[str]:
        """Detect Break of Structure"""
        if len(candles) < lookback:
            return None

        recent = candles[-lookback:]
        highs = [c.high for c in recent[:-1]]
        lows = [c.low for c in recent[:-1]]

        highest = max(highs)
        lowest = min(lows)
        current = candles[-1]

        # Bullish BOS: Break above recent high
        if current.close > highest:
            return 'bull_bos'

        # Bearish BOS: Break below recent low
        if current.close < lowest:
            return 'bear_bos'

        return None

    # ============= Complete Indicator Set =============

    def calculate_all(self, candles: List[Candle]) -> Dict[str, any]:
        """Calculate all indicators for given candles"""
        if not candles:
            return {}

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        # Calculate all indicators
        emas = self.calculate_emas(closes)
        rsi_vals = self.rsi(closes)
        stoch_k, stoch_d = self.stochastic(highs, lows, closes)
        atr_vals = self.atr(highs, lows, closes)
        macd_line, macd_signal, macd_hist = self.macd(closes)
        bb_upper, bb_middle, bb_lower = self.bollinger_bands(closes)
        vwap_vals = self.vwap(highs, lows, closes, volumes)

        # Get latest values
        return {
            'rsi': rsi_vals[-1] if rsi_vals else None,
            'stoch_k': stoch_k[-1] if stoch_k else None,
            'stoch_d': stoch_d[-1] if stoch_d else None,
            'atr': atr_vals[-1] if atr_vals else None,
            'ema_9': emas['ema_9'][-1] if emas['ema_9'] else None,
            'ema_21': emas['ema_21'][-1] if emas['ema_21'] else None,
            'ema_50': emas['ema_50'][-1] if emas['ema_50'] else None,
            'ema_200': emas['ema_200'][-1] if emas['ema_200'] else None,
            'macd': macd_line[-1] if macd_line else None,
            'macd_signal': macd_signal[-1] if macd_signal else None,
            'macd_hist': macd_hist[-1] if macd_hist else None,
            'bb_upper': bb_upper[-1] if bb_upper else None,
            'bb_middle': bb_middle[-1] if bb_middle else None,
            'bb_lower': bb_lower[-1] if bb_lower else None,
            'vwap': vwap_vals[-1] if vwap_vals else None,
            # Pattern detection
            'pattern_engulfing': self.detect_engulfing(candles),
            'pattern_pin': self.detect_pin_bar(candles[-1]) if candles else None,
            'pattern_fvg': self.detect_fvg(candles),
            'pattern_bos': self.detect_bos(candles)
        }

    def get_indicator_series(self, candles: List[Candle]) -> Dict[str, List[float]]:
        """Get full indicator series for all candles"""
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        emas = self.calculate_emas(closes)
        macd_line, macd_signal, macd_hist = self.macd(closes)
        bb_upper, bb_middle, bb_lower = self.bollinger_bands(closes)
        stoch_k, stoch_d = self.stochastic(highs, lows, closes)

        return {
            'rsi': self.rsi(closes),
            'stoch_k': stoch_k,
            'stoch_d': stoch_d,
            'atr': self.atr(highs, lows, closes),
            'ema_9': emas['ema_9'],
            'ema_21': emas['ema_21'],
            'ema_50': emas['ema_50'],
            'ema_200': emas['ema_200'],
            'macd': macd_line,
            'macd_signal': macd_signal,
            'macd_hist': macd_hist,
            'bb_upper': bb_upper,
            'bb_middle': bb_middle,
            'bb_lower': bb_lower,
            'vwap': self.vwap(highs, lows, closes, volumes)
        }


# Global indicator calculator
indicators = IndicatorCalculator()
