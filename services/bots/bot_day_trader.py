#!/usr/bin/env python3
"""
Day Trader Bot
Intraday trading on 5m-1H timeframes, closes all positions by end of day
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
from services.shared.message_queue import mq
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/bots/day_trader.log')
    ]
)
logger = logging.getLogger('bot_day_trader')


class DayTraderBot(BaseTradingBot):
    """
    Day Trader bot for intraday positions
    - Target: 2-3R within the trading day
    - Risk: 2% per trade
    - Closes all positions before market close
    """

    def __init__(self):
        super().__init__('day_trader')

        self.close_before_day_end = self.bot_config.get('close_before_day_end', True)
        self.market_close_hour = 21  # UTC - close before this hour
        self.breakeven_r = 1.0
        self.trailing_start_r = 1.5
        self.trail_distance_r = 0.75  # Trail at 0.75R behind price

    def on_signal(self, signal: Dict):
        """Handle incoming day trading signal"""
        symbol = signal.get('symbol')
        confidence = signal.get('confidence', 0)

        logger.info(f"Received signal for {symbol} (conf={confidence:.2f})")

        # Check if we can trade
        can_trade, reason = self.can_trade(symbol)
        if not can_trade:
            logger.info(f"Cannot trade {symbol}: {reason}")
            return

        # Check if too close to market close
        if self._near_market_close():
            logger.info("Too close to market close, skipping signal")
            return

        # Check confidence
        min_confidence = self.bot_config.get('min_confidence', 0.55)
        if confidence < min_confidence:
            logger.info(f"Confidence too low: {confidence:.2f}")
            return

        # Validate timeframe
        timeframe = signal.get('timeframe', '')
        valid_tfs = ['MINUTE_5', 'MINUTE_15', 'HOUR']
        if timeframe not in valid_tfs:
            logger.info(f"Invalid timeframe for day trader: {timeframe}")
            return

        position = self.open_position(signal)
        if position:
            logger.info(f"Opened day trade for {symbol}")

    def manage_position(self, position: Position, current_price: float):
        """Manage day trading position"""
        current_r = position.current_r

        # Check for forced close before market close
        if self.close_before_day_end and self._near_market_close():
            logger.info(f"Closing {position.symbol} before market close")
            self.close_position(position, "end_of_day", current_price)
            return

        # Check stop loss and take profit
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

        # Move to breakeven
        if current_r >= self.breakeven_r and position.trailing_stop is None:
            self.update_stop_loss(position, position.entry_price)
            logger.info(f"Moved {position.symbol} to breakeven")

        # Start trailing
        if current_r >= self.trailing_start_r:
            self._apply_trailing_stop(position, current_price, current_r)

    def _apply_trailing_stop(self, position: Position, current_price: float, current_r: float):
        """Apply trailing stop"""
        risk_distance = abs(position.entry_price - position.stop_loss)
        trail_distance = risk_distance * self.trail_distance_r

        if position.direction == 'BUY':
            new_stop = current_price - trail_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, new_stop)
        else:
            new_stop = current_price + trail_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, new_stop)

    def _near_market_close(self) -> bool:
        """Check if near market close"""
        now = datetime.now()
        return now.hour >= self.market_close_hour


class DayTraderService:
    def __init__(self):
        self.bot = DayTraderBot()
        self.running = False

    def start(self):
        logger.info("Starting Day Trader Service...")
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
    service = DayTraderService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Day Trader Bot crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
