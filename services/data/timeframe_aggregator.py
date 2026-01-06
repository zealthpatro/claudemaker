#!/usr/bin/env python3
"""
Timeframe Aggregator Microservice
Aggregates 1-minute candles into higher timeframes (5m, 15m, 1H, 4H, 1D)
and calculates technical indicators for each timeframe
"""

import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import threading

sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.indicators import IndicatorCalculator, Candle
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/data/aggregator.log')
    ]
)
logger = logging.getLogger('timeframe_aggregator')


class TimeframeAggregator:
    """
    Aggregates price data into multiple timeframes and calculates indicators
    """

    def __init__(self):
        self.running = False
        self.symbols = config.get_enabled_symbols()
        self.symbol_ids: Dict[str, int] = {}
        self.indicator_calc = IndicatorCalculator()

        # Timeframes to aggregate (from 1-minute data)
        self.timeframes = {
            'MINUTE_5': {'minutes': 5, 'bars_per_period': 5},
            'MINUTE_15': {'minutes': 15, 'bars_per_period': 15},
            'HOUR': {'minutes': 60, 'bars_per_period': 60},
            'HOUR_4': {'minutes': 240, 'bars_per_period': 240},
            'DAY': {'minutes': 1440, 'bars_per_period': 1440}
        }

        self.aggregation_interval = 60  # Run every minute

    def start(self):
        """Start the aggregator"""
        logger.info("Starting Timeframe Aggregator...")

        self._init_symbols()

        self.running = True

        # Subscribe to 1-minute price updates
        mq.subscribe('price:xauusd:1m', self._on_price_update)
        mq.subscribe('price:xagusd:1m', self._on_price_update)

        logger.info("Timeframe Aggregator started")
        self._aggregation_loop()

    def stop(self):
        """Stop the aggregator"""
        logger.info("Stopping Timeframe Aggregator...")
        self.running = False

    def _init_symbols(self):
        """Initialize symbol IDs"""
        for symbol in self.symbols:
            symbol_id = db.get_symbol_id(symbol)
            if symbol_id:
                self.symbol_ids[symbol] = symbol_id
                logger.info(f"Initialized symbol {symbol} with ID {symbol_id}")

    def _on_price_update(self, channel: str, data: dict):
        """Handle real-time price updates"""
        # Extract symbol from channel (e.g., 'price:xauusd:1m' -> 'XAUUSD')
        parts = channel.split(':')
        if len(parts) >= 2:
            symbol = parts[1].upper()
            logger.debug(f"Received price update for {symbol}")

    def _aggregation_loop(self):
        """Main aggregation loop"""
        last_health = time.time()

        while self.running:
            try:
                start_time = time.time()

                # Aggregate for each symbol
                for symbol in self.symbols:
                    self._aggregate_symbol(symbol)

                # Send heartbeat
                if time.time() - last_health >= 60:
                    self._send_heartbeat()
                    last_health = time.time()

                # Sleep until next aggregation
                elapsed = time.time() - start_time
                sleep_time = max(0, self.aggregation_interval - elapsed)
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Aggregation loop error: {e}")
                time.sleep(10)

    def _aggregate_symbol(self, symbol: str):
        """Aggregate all timeframes for a symbol"""
        symbol_id = self.symbol_ids.get(symbol)
        if not symbol_id:
            return

        for timeframe, tf_config in self.timeframes.items():
            try:
                self._aggregate_timeframe(symbol, symbol_id, timeframe, tf_config)
            except Exception as e:
                logger.error(f"Failed to aggregate {timeframe} for {symbol}: {e}")

    def _aggregate_timeframe(self, symbol: str, symbol_id: int,
                             timeframe: str, tf_config: dict):
        """Aggregate a single timeframe from 1-minute data"""
        bars_needed = tf_config['bars_per_period'] * 2  # Get extra for indicator calculation

        # Get latest 1-minute candles
        minute_candles = db.get_price_data(
            symbol_id, 'MINUTE', limit=bars_needed
        )

        if len(minute_candles) < tf_config['bars_per_period']:
            return  # Not enough data

        # Sort by timestamp ascending
        minute_candles = sorted(minute_candles, key=lambda x: x['timestamp'])

        # Get current aggregation period start
        now = datetime.now()
        period_minutes = tf_config['minutes']

        # Align to period boundary
        period_start = now.replace(second=0, microsecond=0)
        minutes_offset = period_start.minute % period_minutes
        period_start = period_start - timedelta(minutes=minutes_offset)

        if timeframe == 'DAY':
            period_start = period_start.replace(hour=0, minute=0)
        elif timeframe == 'HOUR_4':
            period_start = period_start.replace(minute=0)
            hour_offset = period_start.hour % 4
            period_start = period_start - timedelta(hours=hour_offset)
        elif timeframe == 'HOUR':
            period_start = period_start.replace(minute=0)

        # Find candles in current period
        period_end = period_start + timedelta(minutes=period_minutes)
        period_candles = [
            c for c in minute_candles
            if period_start <= c['timestamp'] < period_end
        ]

        if not period_candles:
            return  # No data in current period

        # Aggregate OHLCV
        aggregated = {
            'timestamp': period_start,
            'open': period_candles[0]['open'],
            'high': max(c['high'] for c in period_candles),
            'low': min(c['low'] for c in period_candles),
            'close': period_candles[-1]['close'],
            'volume': sum(c.get('volume', 0) for c in period_candles)
        }

        # Store aggregated candle
        db.insert_price_data(
            symbol_id, timeframe, aggregated['timestamp'],
            aggregated['open'], aggregated['high'],
            aggregated['low'], aggregated['close'],
            aggregated['volume']
        )

        # Calculate and store indicators
        self._calculate_indicators(symbol, symbol_id, timeframe)

        # Cache and publish
        mq.cache_candle(symbol, timeframe, aggregated)
        mq.publish(f'candles:{symbol.lower()}:{timeframe.lower()}', aggregated)

    def _calculate_indicators(self, symbol: str, symbol_id: int, timeframe: str):
        """Calculate technical indicators for a timeframe"""
        # Get enough candles for indicator calculation
        candles_data = db.get_price_data(symbol_id, timeframe, limit=200)

        if len(candles_data) < 50:
            return  # Not enough data for indicators

        # Sort ascending
        candles_data = sorted(candles_data, key=lambda x: x['timestamp'])

        # Convert to Candle objects
        candles = [
            Candle(
                timestamp=c['timestamp'],
                open=float(c['open']),
                high=float(c['high']),
                low=float(c['low']),
                close=float(c['close']),
                volume=float(c.get('volume', 0))
            )
            for c in candles_data
        ]

        # Calculate all indicators
        indicators = self.indicator_calc.calculate_all(candles)

        # Store in database
        self._store_indicators(symbol_id, timeframe, candles[-1].timestamp, indicators)

        # Publish indicator update
        indicators['symbol'] = symbol
        indicators['timeframe'] = timeframe
        indicators['timestamp'] = candles[-1].timestamp.isoformat()
        mq.publish(f'indicators:{symbol.lower()}:{timeframe.lower()}', indicators)

    def _store_indicators(self, symbol_id: int, timeframe: str,
                          timestamp: datetime, indicators: dict):
        """Store indicators in database"""
        query = """
            INSERT INTO indicators (
                symbol_id, timeframe, timestamp, rsi, stoch_k, stoch_d,
                atr, ema_9, ema_21, ema_50, ema_200, macd, macd_signal,
                macd_hist, bb_upper, bb_middle, bb_lower, vwap
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (symbol_id, timeframe, timestamp) DO UPDATE SET
                rsi = EXCLUDED.rsi, stoch_k = EXCLUDED.stoch_k, stoch_d = EXCLUDED.stoch_d,
                atr = EXCLUDED.atr, ema_9 = EXCLUDED.ema_9, ema_21 = EXCLUDED.ema_21,
                ema_50 = EXCLUDED.ema_50, ema_200 = EXCLUDED.ema_200, macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal, macd_hist = EXCLUDED.macd_hist,
                bb_upper = EXCLUDED.bb_upper, bb_middle = EXCLUDED.bb_middle,
                bb_lower = EXCLUDED.bb_lower, vwap = EXCLUDED.vwap
        """
        params = (
            symbol_id, timeframe, timestamp,
            indicators.get('rsi'), indicators.get('stoch_k'), indicators.get('stoch_d'),
            indicators.get('atr'), indicators.get('ema_9'), indicators.get('ema_21'),
            indicators.get('ema_50'), indicators.get('ema_200'), indicators.get('macd'),
            indicators.get('macd_signal'), indicators.get('macd_hist'),
            indicators.get('bb_upper'), indicators.get('bb_middle'),
            indicators.get('bb_lower'), indicators.get('vwap')
        )
        db.execute(query, params)

    def _send_heartbeat(self):
        """Send service heartbeat"""
        mq.send_heartbeat('timeframe_aggregator', 'running', {
            'symbols': self.symbols,
            'timeframes': list(self.timeframes.keys())
        })
        db.update_service_state('timeframe_aggregator', 'running')


def main():
    aggregator = TimeframeAggregator()

    def signal_handler(signum, frame):
        aggregator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        aggregator.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
