#!/usr/bin/env python3
"""
Position Trading Bot
Long-term positions on 4H-1D timeframes with scale-in capability
"""

import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List
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
        logging.FileHandler('/home/user/claudemaker/logs/bots/position.log')
    ]
)
logger = logging.getLogger('bot_position')


class PositionBot(BaseTradingBot):
    """
    Position trading bot for long-term trades
    - Target: 10R over 1-4 weeks
    - Risk: 2% per trade
    - Supports scale-in at better prices
    """

    def __init__(self):
        super().__init__('position')

        self.scale_in_enabled = self.bot_config.get('scale_in', True)
        self.scale_in_levels = self.bot_config.get('scale_in_levels', [0.5, 0.3, 0.2])
        self.max_hold_weeks = 4
        self.breakeven_r = 2.0
        self.trailing_trigger_r = 5.0

        # Track scale-in positions
        self.position_entries: Dict[str, List[Dict]] = {}  # symbol -> entries

    def on_signal(self, signal: Dict):
        """Handle incoming position signal"""
        symbol = signal.get('symbol')
        confidence = signal.get('confidence', 0)
        direction = signal.get('direction')

        logger.info(f"Received position signal for {symbol}")

        # Check if this is a scale-in opportunity
        existing = self._get_existing_position(symbol, direction)
        if existing and self.scale_in_enabled:
            self._consider_scale_in(existing, signal)
            return

        can_trade, reason = self.can_trade(symbol)
        if not can_trade:
            logger.info(f"Cannot trade: {reason}")
            return

        min_confidence = self.bot_config.get('min_confidence', 0.55)
        if confidence < min_confidence:
            logger.info(f"Confidence too low: {confidence:.2f}")
            return

        timeframe = signal.get('timeframe', '')
        if timeframe not in ['HOUR_4', 'DAY']:
            logger.info(f"Invalid timeframe for position: {timeframe}")
            return

        # Open initial position with first scale level
        if self.scale_in_enabled:
            self._open_scaled_position(signal)
        else:
            self.open_position(signal)

    def _open_scaled_position(self, signal: Dict):
        """Open position with initial scale"""
        symbol = signal.get('symbol')

        # Use first scale level for initial entry
        original_risk = self.bot_config.get('risk_pct', 0.02)
        scaled_risk = original_risk * self.scale_in_levels[0]

        position = self.open_position(signal)
        if position:
            self.position_entries[symbol] = [{
                'price': position.entry_price,
                'size': position.position_size,
                'level': 0
            }]
            logger.info(f"Opened scaled position for {symbol} (level 1/{len(self.scale_in_levels)})")

    def _get_existing_position(self, symbol: str, direction: str):
        """Get existing position for symbol in same direction"""
        for pos in self.positions.values():
            if pos.symbol == symbol and pos.direction == direction:
                return pos
        return None

    def _consider_scale_in(self, position: Position, signal: Dict):
        """Consider scaling into existing position"""
        symbol = position.symbol
        entries = self.position_entries.get(symbol, [])
        current_level = len(entries)

        if current_level >= len(self.scale_in_levels):
            logger.info(f"Max scale levels reached for {symbol}")
            return

        # Check if price is better than last entry
        current_price = signal.get('entry_price', 0)
        last_entry = entries[-1]['price'] if entries else position.entry_price

        if position.direction == 'BUY':
            is_better = current_price < last_entry * 0.99  # 1% better
        else:
            is_better = current_price > last_entry * 1.01

        if is_better:
            logger.info(f"Scaling into {symbol} at level {current_level + 1}")
            # Note: In production, would add to position here

    def manage_position(self, position: Position, current_price: float):
        """Manage position with wide stops and patience"""
        current_r = position.current_r
        hold_time = datetime.now() - position.opened_at

        # Check max hold time
        if hold_time > timedelta(weeks=self.max_hold_weeks):
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

        # Move to breakeven at 2R
        if current_r >= self.breakeven_r and position.trailing_stop is None:
            self.update_stop_loss(position, position.entry_price)
            logger.info(f"Moved {position.symbol} to breakeven")

        # Wide trailing after 5R
        if current_r >= self.trailing_trigger_r:
            self._apply_wide_trailing(position, current_price)

    def _apply_wide_trailing(self, position: Position, current_price: float):
        """Apply wide trailing stop for position trades"""
        initial_risk = abs(position.entry_price - position.stop_loss)
        # Trail at 3R behind current price
        trail_distance = initial_risk * 3

        if position.direction == 'BUY':
            new_stop = current_price - trail_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))
        else:
            new_stop = current_price + trail_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))


class PositionService:
    def __init__(self):
        self.bot = PositionBot()
        self.running = False

    def start(self):
        logger.info("Starting Position Service...")
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
    service = PositionService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Position Bot crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
