#!/usr/bin/env python3
"""
Swing Trading Bot
Multi-day positions on 1H-4H timeframes with trailing stops
"""

import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict
import logging

sys.path.insert(0, '/home/user/claudemaker')

from services.bots.base_trading_bot import BaseTradingBot, Position
from services.shared.config import config
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/bots/swing.log')
    ]
)
logger = logging.getLogger('bot_swing')


class SwingBot(BaseTradingBot):
    """
    Swing trading bot for multi-day positions
    - Target: 5R over 2-5 days
    - Risk: 3% per trade
    - Uses ATR-based trailing stops
    """

    def __init__(self):
        super().__init__('swing')

        self.trailing_enabled = self.bot_config.get('trailing_stop', True)
        self.trailing_trigger_r = self.bot_config.get('trailing_trigger_r', 2.0)
        self.trailing_atr_mult = 1.5  # Trail at 1.5 ATR
        self.max_hold_days = 7  # Maximum hold time

    def on_signal(self, signal: Dict):
        """Handle incoming swing signal"""
        symbol = signal.get('symbol')
        confidence = signal.get('confidence', 0)

        logger.info(f"Received swing signal for {symbol}")

        can_trade, reason = self.can_trade(symbol)
        if not can_trade:
            logger.info(f"Cannot trade: {reason}")
            return

        min_confidence = self.bot_config.get('min_confidence', 0.50)
        if confidence < min_confidence:
            logger.info(f"Confidence too low: {confidence:.2f}")
            return

        timeframe = signal.get('timeframe', '')
        if timeframe not in ['HOUR', 'HOUR_4']:
            logger.info(f"Invalid timeframe for swing: {timeframe}")
            return

        position = self.open_position(signal)
        if position:
            logger.info(f"Opened swing position for {symbol}")

    def manage_position(self, position: Position, current_price: float):
        """Manage swing position with trailing stop"""
        current_r = position.current_r
        hold_time = datetime.now() - position.opened_at

        # Check max hold time
        if hold_time > timedelta(days=self.max_hold_days):
            logger.info(f"Max hold time reached for {position.symbol}")
            self.close_position(position, "time_exit", current_price)
            return

        # Check TP/SL
        if position.direction == 'BUY':
            if current_price >= position.take_profit:
                self.close_position(position, "tp_hit", current_price)
                return
            if current_price <= position.stop_loss:
                self.close_position(position, "sl_hit", current_price)
                return
        else:
            if current_price <= position.take_profit:
                self.close_position(position, "tp_hit", current_price)
                return
            if current_price >= position.stop_loss:
                self.close_position(position, "sl_hit", current_price)
                return

        # Apply trailing stop after trigger
        if self.trailing_enabled and current_r >= self.trailing_trigger_r:
            self._apply_atr_trailing(position, current_price)

    def _apply_atr_trailing(self, position: Position, current_price: float):
        """Apply ATR-based trailing stop"""
        # Estimate ATR from stop distance
        initial_risk = abs(position.entry_price - position.stop_loss)
        atr_estimate = initial_risk / self.bot_config.get('stop_atr_multiplier', 1.5)
        trail_distance = atr_estimate * self.trailing_atr_mult

        if position.direction == 'BUY':
            new_stop = current_price - trail_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))
        else:
            new_stop = current_price + trail_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))


class SwingService:
    def __init__(self):
        self.bot = SwingBot()
        self.running = False

    def start(self):
        logger.info("Starting Swing Service...")
        self.running = True
        try:
            self.bot.start()
            while self.running:
                self.bot._send_heartbeat()
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self.bot.stop()


def main():
    service = SwingService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Swing Bot crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
