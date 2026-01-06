#!/usr/bin/env python3
"""
Sniper Trading Bot
High-conviction trades only with maximum confidence signals
Uses limit orders for precise entries
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
from services.shared.capital_api import api
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/bots/sniper.log')
    ]
)
logger = logging.getLogger('bot_sniper')


class SniperBot(BaseTradingBot):
    """
    Sniper bot for ultra-high conviction trades
    - Target: 15-20R
    - Risk: 5% per trade (high conviction)
    - Uses limit orders for precise entries
    - Only takes trades with 85%+ confidence
    """

    def __init__(self):
        super().__init__('sniper')

        self.limit_orders_only = self.bot_config.get('limit_orders_only', True)
        self.entry_improvement_pct = 0.002  # Try to get 0.2% better entry
        self.pending_orders: Dict[str, Dict] = {}  # order_id -> order details
        self.order_expiry_minutes = 60  # Cancel unfilled orders after 1 hour

    def on_signal(self, signal: Dict):
        """Handle incoming sniper signal"""
        symbol = signal.get('symbol')
        confidence = signal.get('confidence', 0)

        logger.info(f"Received sniper signal for {symbol} (conf={confidence:.2f})")

        # Only ultra-high confidence
        min_confidence = self.bot_config.get('min_confidence', 0.85)
        if confidence < min_confidence:
            logger.info(f"Confidence below sniper threshold: {confidence:.2f} < {min_confidence}")
            return

        can_trade, reason = self.can_trade(symbol)
        if not can_trade:
            logger.info(f"Cannot trade: {reason}")
            return

        if self.limit_orders_only:
            self._place_limit_order(signal)
        else:
            position = self.open_position(signal)
            if position:
                logger.info(f"Opened sniper position for {symbol}")

    def _place_limit_order(self, signal: Dict):
        """Place limit order for better entry"""
        symbol = signal.get('symbol')
        direction = signal.get('direction')
        entry = signal.get('entry_price')
        stop = signal.get('stop_loss')
        target = signal.get('take_profit')

        # Calculate improved entry price
        if direction == 'BUY':
            limit_price = entry * (1 - self.entry_improvement_pct)
        else:
            limit_price = entry * (1 + self.entry_improvement_pct)

        # Calculate stop and target distances
        stop_distance = abs(entry - stop)
        profit_distance = abs(target - entry)

        # Calculate position size
        position_size = self.calculate_position_size(symbol, limit_price, stop)

        # Place limit order
        epic = self._get_epic(symbol)
        success, result = api.place_limit_order(
            epic=epic,
            direction=direction,
            size=position_size,
            level=round(limit_price, 2),
            stop_distance=round(stop_distance, 2),
            profit_distance=round(profit_distance, 2)
        )

        if success:
            order_id = result.get('dealReference', '')
            self.pending_orders[order_id] = {
                'signal': signal,
                'limit_price': limit_price,
                'placed_at': datetime.now(),
                'order_id': order_id
            }
            logger.info(f"Placed sniper limit order for {symbol} @ {limit_price:.2f}")
        else:
            # Fall back to market order
            logger.warning(f"Limit order failed, using market order: {result}")
            self.open_position(signal)

    def manage_position(self, position: Position, current_price: float):
        """Manage sniper position - patient for big moves"""
        current_r = position.current_r

        # Check basic TP/SL
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

        # Move to breakeven at 3R (later than other bots - we want the full move)
        if current_r >= 3.0 and position.trailing_stop is None:
            self.update_stop_loss(position, position.entry_price)
            logger.info(f"Sniper: Moved {position.symbol} to breakeven")

        # Lock in profit at 7R
        if current_r >= 7.0:
            self._lock_profit(position, current_price, current_r)

        # Aggressive trailing after 10R
        if current_r >= 10.0:
            self._aggressive_trail(position, current_price)

    def _lock_profit(self, position: Position, current_price: float, current_r: float):
        """Lock in a portion of profit"""
        initial_risk = abs(position.entry_price - position.stop_loss)
        # Lock at entry + 3R
        lock_distance = initial_risk * 3

        if position.direction == 'BUY':
            new_stop = position.entry_price + lock_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))
                logger.info(f"Sniper: Locked 3R profit on {position.symbol}")
        else:
            new_stop = position.entry_price - lock_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))
                logger.info(f"Sniper: Locked 3R profit on {position.symbol}")

    def _aggressive_trail(self, position: Position, current_price: float):
        """Aggressive trailing after large gains"""
        initial_risk = abs(position.entry_price - position.stop_loss)
        # Trail at 5R behind current
        trail_distance = initial_risk * 5

        if position.direction == 'BUY':
            new_stop = current_price - trail_distance
            if new_stop > position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))
        else:
            new_stop = current_price + trail_distance
            if new_stop < position.stop_loss:
                self.update_stop_loss(position, round(new_stop, 2))

    def _check_pending_orders(self):
        """Check and manage pending limit orders"""
        now = datetime.now()

        for order_id, order in list(self.pending_orders.items()):
            placed_at = order['placed_at']

            # Cancel expired orders
            if now - placed_at > timedelta(minutes=self.order_expiry_minutes):
                api.cancel_order(order_id)
                del self.pending_orders[order_id]
                logger.info(f"Cancelled expired sniper order {order_id}")


class SniperService:
    def __init__(self):
        self.bot = SniperBot()
        self.running = False

    def start(self):
        logger.info("Starting Sniper Service...")
        self.running = True
        try:
            self.bot.start()
            while self.running:
                self.bot._send_heartbeat()
                self.bot._check_pending_orders()
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self.bot.stop()


def main():
    service = SniperService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Sniper Bot crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
