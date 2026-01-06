#!/usr/bin/env python3
"""
Scalper Trading Bot
High-frequency trading on 1m-5m timeframes with quick exits
"""

import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

sys.path.insert(0, '/home/user/claudemaker')

from services.bots.base_trading_bot import BaseTradingBot, Position
from services.shared.config import config
from services.shared.message_queue import mq
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/bots/scalper.log')
    ]
)
logger = logging.getLogger('bot_scalper')


class ScalperBot(BaseTradingBot):
    """
    Scalper bot for quick trades on 1m and 5m timeframes
    - Target: 3-5R within 1 hour
    - Risk: 1% per trade
    - Max hold time: 60 minutes
    """

    def __init__(self):
        super().__init__('scalper')

        # Scalper-specific settings
        self.max_hold_minutes = self.bot_config.get('max_hold_minutes', 60)
        self.partial_exit_r = 2.0  # Take partial at 2R
        self.partial_exit_pct = 0.5  # Close 50% at partial
        self.breakeven_r = 1.5  # Move to breakeven at 1.5R
        self.valid_sessions = self.bot_config.get('sessions', ['london_open', 'ny_open'])

    def on_signal(self, signal: Dict):
        """Handle incoming scalping signal"""
        symbol = signal.get('symbol')
        confidence = signal.get('confidence', 0)

        logger.info(f"Received signal for {symbol} (conf={confidence:.2f})")

        # Check if we can trade
        can_trade, reason = self.can_trade(symbol)
        if not can_trade:
            logger.info(f"Cannot trade {symbol}: {reason}")
            return

        # Check if in valid trading session
        if not self._in_valid_session():
            logger.info("Not in valid trading session for scalping")
            return

        # Check confidence threshold
        min_confidence = self.bot_config.get('min_confidence', 0.60)
        if confidence < min_confidence:
            logger.info(f"Confidence too low: {confidence:.2f} < {min_confidence}")
            return

        # Validate timeframe
        timeframe = signal.get('timeframe', '')
        if timeframe not in ['MINUTE', 'MINUTE_5']:
            logger.info(f"Invalid timeframe for scalper: {timeframe}")
            return

        # Open position
        position = self.open_position(signal)
        if position:
            logger.info(f"Opened scalp position for {symbol}")

    def manage_position(self, position: Position, current_price: float):
        """Manage scalp position with aggressive exits"""
        current_r = position.current_r

        # Check max hold time
        hold_time = datetime.now() - position.opened_at
        if hold_time > timedelta(minutes=self.max_hold_minutes):
            logger.info(f"Max hold time reached for {position.symbol}")
            self.close_position(position, "time_exit", current_price)
            return

        # Check if hit take profit
        if position.direction == 'BUY':
            if current_price >= position.take_profit:
                self.close_position(position, "tp_hit", current_price)
                return
            if current_price <= position.stop_loss:
                self.close_position(position, "sl_hit", current_price)
                return
        else:  # SELL
            if current_price <= position.take_profit:
                self.close_position(position, "tp_hit", current_price)
                return
            if current_price >= position.stop_loss:
                self.close_position(position, "sl_hit", current_price)
                return

        # Move to breakeven at 1.5R
        if current_r >= self.breakeven_r and position.trailing_stop is None:
            new_stop = position.entry_price
            if self.update_stop_loss(position, new_stop):
                logger.info(f"Moved {position.symbol} to breakeven")

        # Aggressive trailing after 2R
        if current_r >= 2.0:
            self._trail_stop(position, current_price, current_r)

    def _trail_stop(self, position: Position, current_price: float, current_r: float):
        """Trail stop loss for scalping"""
        risk_distance = abs(position.entry_price - position.stop_loss)

        if position.direction == 'BUY':
            # Trail at 1R below current price
            new_stop = current_price - risk_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, new_stop)
        else:  # SELL
            new_stop = current_price + risk_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, new_stop)

    def _in_valid_session(self) -> bool:
        """Check if current time is in valid trading session"""
        sessions = config.get('sessions', {})
        now = datetime.now()
        current_hour = now.hour

        for session_name in self.valid_sessions:
            session = sessions.get(session_name, {})
            start_hour = int(session.get('start', '00:00').split(':')[0])
            end_hour = int(session.get('end', '23:59').split(':')[0])

            if start_hour <= current_hour < end_hour:
                return True

        return False


class ScalperService:
    """Service wrapper for Scalper Bot"""

    def __init__(self):
        self.bot = ScalperBot()
        self.running = False

    def start(self):
        """Start the service"""
        logger.info("Starting Scalper Service...")
        self.running = True

        try:
            self.bot.start()

            # Main loop
            while self.running:
                self.bot._send_heartbeat()
                time.sleep(60)

        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the service"""
        logger.info("Stopping Scalper Service...")
        self.running = False
        self.bot.stop()


def main():
    service = ScalperService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Scalper Bot crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
