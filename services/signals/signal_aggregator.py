#!/usr/bin/env python3
"""
Signal Aggregator Microservice
Combines signals from Gold and Silver generators, calculates confluence,
and routes to appropriate trading bots
"""

import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from collections import defaultdict

sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/signals/aggregator.log')
    ]
)
logger = logging.getLogger('signal_aggregator')


class SignalAggregator:
    """
    Aggregates signals from multiple sources, calculates confluence,
    and routes to trading bots
    """

    def __init__(self):
        self.running = False

        # Confluence weights
        self.timeframe_weights = {
            'DAY': 2.0,
            'HOUR_4': 1.5,
            'HOUR': 1.2,
            'MINUTE_15': 1.0,
            'MINUTE_5': 0.8,
            'MINUTE': 0.6
        }

        # Cross-commodity correlation factor
        self.correlation_boost = 0.15  # Boost when gold and silver align

        # Recent signals cache for confluence
        self.recent_signals: Dict[str, List[Dict]] = defaultdict(list)
        self.signal_ttl = timedelta(minutes=30)

        # Bot routing thresholds
        self.bot_thresholds = {
            'sniper': {'min_confidence': 0.85, 'min_confluence': 0.80},
            'scalper': {'min_confidence': 0.60, 'min_confluence': 0.50},
            'day_trader': {'min_confidence': 0.55, 'min_confluence': 0.45},
            'swing': {'min_confidence': 0.50, 'min_confluence': 0.40},
            'position': {'min_confidence': 0.55, 'min_confluence': 0.50}
        }

    def start(self):
        """Start the aggregator"""
        logger.info("Starting Signal Aggregator...")

        # Subscribe to signal channels
        mq.subscribe('signals:gold', self._on_signal)
        mq.subscribe('signals:silver', self._on_signal)

        self.running = True
        self._aggregation_loop()

    def stop(self):
        """Stop the aggregator"""
        logger.info("Stopping Signal Aggregator...")
        self.running = False

    def _on_signal(self, channel: str, data: Dict):
        """Handle incoming signals"""
        symbol = data.get('symbol', '')
        logger.debug(f"Received signal for {symbol}")

        # Add to recent signals
        data['received_at'] = datetime.now()
        self.recent_signals[symbol].append(data)

        # Clean old signals
        self._clean_old_signals()

    def _clean_old_signals(self):
        """Remove expired signals from cache"""
        now = datetime.now()
        for symbol in list(self.recent_signals.keys()):
            self.recent_signals[symbol] = [
                s for s in self.recent_signals[symbol]
                if now - s.get('received_at', now) < self.signal_ttl
            ]

    def _aggregation_loop(self):
        """Main aggregation loop"""
        while self.running:
            try:
                # Get pending signals from database
                pending = db.get_pending_signals()

                if pending:
                    self._process_pending_signals(pending)

                # Send heartbeat
                mq.send_heartbeat('signal_aggregator', 'running', {
                    'pending_signals': len(pending) if pending else 0
                })

                time.sleep(5)  # Check every 5 seconds

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Aggregation error: {e}")
                time.sleep(10)

    def _process_pending_signals(self, signals: List[Dict]):
        """Process pending signals with confluence analysis"""
        # Group by symbol and direction
        grouped = defaultdict(list)
        for sig in signals:
            key = (sig['symbol_id'], sig['direction'])
            grouped[key].append(sig)

        for (symbol_id, direction), group in grouped.items():
            # Calculate confluence
            confluence = self._calculate_confluence(group)

            # Check cross-commodity alignment
            cross_boost = self._check_cross_commodity(symbol_id, direction)
            total_confluence = min(1.0, confluence + cross_boost)

            # Process best signal from group
            best_signal = max(group, key=lambda s: s['confidence'])

            # Boost confidence with confluence
            boosted_confidence = min(1.0, best_signal['confidence'] * (1 + total_confluence * 0.2))

            # Route to appropriate bot
            target_bot = self._route_to_bot(
                best_signal, boosted_confidence, total_confluence
            )

            if target_bot:
                self._dispatch_to_bot(best_signal, target_bot, boosted_confidence, total_confluence)

    def _calculate_confluence(self, signals: List[Dict]) -> float:
        """Calculate multi-timeframe confluence score"""
        if not signals:
            return 0

        total_weight = 0
        weighted_confidence = 0

        for sig in signals:
            tf = sig.get('timeframe', 'HOUR')
            weight = self.timeframe_weights.get(tf, 1.0)
            conf = sig.get('confidence', 0.5)

            total_weight += weight
            weighted_confidence += weight * conf

        return weighted_confidence / total_weight if total_weight > 0 else 0

    def _check_cross_commodity(self, symbol_id: int, direction: str) -> float:
        """Check if other commodities align with this direction"""
        boost = 0

        # Get recent signals for other symbols
        for symbol, signals in self.recent_signals.items():
            if not signals:
                continue

            # Check if this is a different symbol
            other_symbol_id = db.get_symbol_id(symbol)
            if other_symbol_id == symbol_id:
                continue

            # Check for aligned signals
            aligned = [s for s in signals if s.get('direction') == direction]
            if aligned:
                boost += self.correlation_boost

        return min(boost, 0.3)  # Cap boost at 30%

    def _route_to_bot(self, signal: Dict, confidence: float,
                      confluence: float) -> Optional[str]:
        """Determine which bot should handle this signal"""
        timeframe = signal.get('timeframe', '')

        # Sniper bot for ultra-high confidence
        if confidence >= self.bot_thresholds['sniper']['min_confidence']:
            if confluence >= self.bot_thresholds['sniper']['min_confluence']:
                return 'sniper'

        # Route by timeframe
        if timeframe in ['MINUTE', 'MINUTE_5']:
            if confidence >= self.bot_thresholds['scalper']['min_confidence']:
                return 'scalper'

        elif timeframe in ['MINUTE_15', 'HOUR']:
            if confidence >= self.bot_thresholds['day_trader']['min_confidence']:
                return 'day_trader'

        elif timeframe in ['HOUR_4']:
            if confidence >= self.bot_thresholds['swing']['min_confidence']:
                return 'swing'

        elif timeframe == 'DAY':
            if confidence >= self.bot_thresholds['position']['min_confidence']:
                return 'position'

        # Default to day_trader if meets minimum
        if confidence >= 0.50:
            return 'day_trader'

        return None

    def _dispatch_to_bot(self, signal: Dict, bot_type: str,
                         confidence: float, confluence: float):
        """Dispatch signal to appropriate bot"""
        # Update signal in database
        db.execute(
            """UPDATE signals SET
               target_bot = %s,
               confidence = %s,
               status = 'dispatched'
               WHERE id = %s""",
            (bot_type, confidence, signal['id'])
        )

        # Prepare dispatch message
        dispatch = {
            'signal_id': signal['id'],
            'symbol': signal.get('symbol') or self._get_symbol_name(signal['symbol_id']),
            'symbol_id': signal['symbol_id'],
            'direction': signal['direction'],
            'timeframe': signal['timeframe'],
            'setup_name': signal['setup_name'],
            'confidence': confidence,
            'confluence': confluence,
            'tier': signal['tier'],
            'entry_price': float(signal['entry_price']) if signal['entry_price'] else None,
            'stop_loss': float(signal['stop_loss']) if signal['stop_loss'] else None,
            'take_profit': float(signal['take_profit']) if signal['take_profit'] else None,
            'dispatched_at': datetime.now().isoformat()
        }

        # Publish to bot-specific channel
        channel = f'commands:{bot_type}'
        mq.publish(channel, dispatch)

        logger.info(f"Dispatched signal {signal['id']} to {bot_type} "
                    f"(conf={confidence:.2f}, confl={confluence:.2f})")

        # Also publish to aggregated channel for monitoring
        mq.publish('signals:aggregated', dispatch)

    def _get_symbol_name(self, symbol_id: int) -> str:
        """Get symbol name from ID"""
        result = db.fetch_one("SELECT name FROM symbols WHERE id = %s", (symbol_id,))
        return result['name'] if result else 'UNKNOWN'


def main():
    aggregator = SignalAggregator()

    def signal_handler(signum, frame):
        aggregator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        aggregator.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Signal Aggregator crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
