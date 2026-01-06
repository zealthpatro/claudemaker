#!/usr/bin/env python3
"""
Data Collector Microservice
Fetches real-time price data for Gold and Silver from Capital.com API
Stores in PostgreSQL and publishes to Redis for real-time processing
"""

import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import threading

# Add parent path for imports
sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.capital_api import api
from services.shared.notifications import notifier
from services.shared.indicators import Candle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/data/collector.log')
    ]
)
logger = logging.getLogger('data_collector')


class DataCollector:
    """
    Collects price data from Capital.com API at regular intervals
    and stores in database while publishing to message queue
    """

    def __init__(self):
        self.running = False
        self.symbols = config.get_enabled_symbols()
        self.symbol_ids: Dict[str, int] = {}
        self.last_candles: Dict[str, Dict[str, datetime]] = {}  # symbol -> {timeframe -> last_timestamp}
        self.collection_interval = 60  # Collect every minute
        self.health_interval = 60  # Health check every minute

        # Timeframes to collect (in order of frequency)
        self.timeframes = ['MINUTE', 'MINUTE_5', 'MINUTE_15', 'HOUR', 'HOUR_4', 'DAY']

        # Epic mapping for Capital.com
        self.epic_map = {
            'XAUUSD': 'GOLD',
            'XAGUSD': 'SILVER'
        }

    def start(self):
        """Start the data collector"""
        logger.info("Starting Data Collector...")

        # Initialize
        self._init_database()
        self._init_symbols()
        self._authenticate()

        # Fetch historical data on startup
        self._fetch_historical_data()

        self.running = True

        # Start collection loop
        logger.info("Data Collector started successfully")
        self._collection_loop()

    def stop(self):
        """Stop the data collector"""
        logger.info("Stopping Data Collector...")
        self.running = False

    def _init_database(self):
        """Initialize database schema"""
        try:
            db.init_schema()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _init_symbols(self):
        """Ensure symbols exist in database"""
        for symbol in self.symbols:
            symbol_config = config.get_symbol_config(symbol)
            symbol_id = db.ensure_symbol(symbol, symbol_config.get('name', symbol))
            self.symbol_ids[symbol] = symbol_id
            self.last_candles[symbol] = {}
            logger.info(f"Initialized symbol {symbol} with ID {symbol_id}")

    def _authenticate(self):
        """Authenticate with Capital.com API"""
        if not api.authenticate():
            logger.error("Failed to authenticate with Capital.com")
            notifier.send_system_alert('error', 'Failed to authenticate with Capital.com', 'data_collector')
            raise Exception("Authentication failed")
        logger.info("Authenticated with Capital.com")

    def _fetch_historical_data(self):
        """Fetch historical data for all symbols and timeframes"""
        logger.info("Fetching historical data...")

        for symbol in self.symbols:
            epic = self.epic_map.get(symbol, symbol)
            symbol_id = self.symbol_ids[symbol]

            for timeframe in self.timeframes:
                tf_config = config.get_timeframe_config(timeframe)
                days = tf_config.get('fetch_history_days', 7)

                try:
                    # Calculate how many candles we need
                    seconds_per_candle = tf_config.get('seconds', 60)
                    max_candles = min(1000, (days * 86400) // seconds_per_candle)

                    candles = api.fetch_candles(symbol, timeframe, count=max_candles)

                    if candles:
                        self._store_candles(symbol_id, timeframe, candles)
                        logger.info(f"Fetched {len(candles)} {timeframe} candles for {symbol}")

                        # Track last candle timestamp
                        self.last_candles[symbol][timeframe] = candles[-1]['timestamp']
                    else:
                        logger.warning(f"No candles returned for {symbol} {timeframe}")

                except Exception as e:
                    logger.error(f"Failed to fetch {timeframe} data for {symbol}: {e}")

                # Rate limiting
                time.sleep(0.5)

        logger.info("Historical data fetch complete")

    def _store_candles(self, symbol_id: int, timeframe: str, candles: List[Dict]) -> int:
        """Store candles in database"""
        data = []
        for candle in candles:
            data.append({
                'symbol_id': symbol_id,
                'timeframe': timeframe,
                'timestamp': candle['timestamp'],
                'open': candle['open'],
                'high': candle['high'],
                'low': candle['low'],
                'close': candle['close'],
                'volume': candle.get('volume', 0)
            })

        return db.insert_price_data_bulk(data)

    def _collection_loop(self):
        """Main collection loop"""
        last_health = time.time()

        while self.running:
            try:
                start_time = time.time()

                # Collect data for each symbol
                for symbol in self.symbols:
                    self._collect_symbol_data(symbol)

                # Send heartbeat
                if time.time() - last_health >= self.health_interval:
                    self._send_heartbeat()
                    last_health = time.time()

                # Sleep until next collection
                elapsed = time.time() - start_time
                sleep_time = max(0, self.collection_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                self.stop()
            except Exception as e:
                logger.error(f"Collection loop error: {e}")
                time.sleep(10)  # Wait before retrying

    def _collect_symbol_data(self, symbol: str):
        """Collect latest data for a symbol"""
        epic = self.epic_map.get(symbol, symbol)
        symbol_id = self.symbol_ids[symbol]

        try:
            # Fetch latest 1-minute candle
            candles = api.fetch_candles(symbol, 'MINUTE', count=5)

            if candles:
                latest = candles[-1]

                # Store in database
                self._store_candles(symbol_id, 'MINUTE', candles)

                # Cache current price
                mq.cache_price(symbol, latest['close'])

                # Publish to Redis for real-time processing
                mq.publish(f'price:{symbol.lower()}:1m', latest)

                # Cache latest candle
                mq.cache_candle(symbol, 'MINUTE', latest)

                logger.debug(f"{symbol}: {latest['close']:.2f}")

                # Check if we need to update higher timeframes
                self._check_higher_timeframes(symbol, symbol_id, latest['timestamp'])

        except Exception as e:
            logger.error(f"Failed to collect data for {symbol}: {e}")

    def _check_higher_timeframes(self, symbol: str, symbol_id: int, current_time: datetime):
        """Check if higher timeframes need updating"""
        for timeframe in self.timeframes[1:]:  # Skip MINUTE, already collected
            tf_config = config.get_timeframe_config(timeframe)
            tf_seconds = tf_config.get('seconds', 300)

            # Get last timestamp for this timeframe
            last_ts = self.last_candles[symbol].get(timeframe)

            if last_ts is None:
                # First time, fetch
                should_fetch = True
            else:
                # Check if new candle should be available
                expected_next = last_ts + timedelta(seconds=tf_seconds)
                should_fetch = current_time >= expected_next

            if should_fetch:
                try:
                    candles = api.fetch_candles(symbol, timeframe, count=3)
                    if candles:
                        self._store_candles(symbol_id, timeframe, candles)
                        self.last_candles[symbol][timeframe] = candles[-1]['timestamp']

                        # Cache and publish
                        mq.cache_candle(symbol, timeframe, candles[-1])
                        mq.publish(f'candles:{symbol.lower()}:{timeframe.lower()}', candles[-1])

                        logger.debug(f"Updated {timeframe} candle for {symbol}")

                except Exception as e:
                    logger.error(f"Failed to update {timeframe} for {symbol}: {e}")

                time.sleep(0.2)  # Rate limiting

    def _send_heartbeat(self):
        """Send service heartbeat"""
        data = {
            'symbols': self.symbols,
            'last_collection': datetime.now().isoformat(),
            'requests_count': api._request_count
        }
        mq.send_heartbeat('data_collector', 'running', data)
        db.update_service_state('data_collector', 'running', data)


def main():
    """Main entry point"""
    collector = DataCollector()

    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        collector.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        collector.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Data Collector crashed: {e}', 'data_collector')
        sys.exit(1)


if __name__ == '__main__':
    main()
