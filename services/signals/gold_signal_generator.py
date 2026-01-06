#!/usr/bin/env python3
"""
Gold Signal Generator Microservice
Generates buy/sell signals for XAUUSD based on backtested setups
"""

import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notifier
from services.signals.base_signal_generator import BaseSignalGenerator, Signal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/signals/gold.log')
    ]
)
logger = logging.getLogger('gold_signal_generator')


class GoldSignalGenerator(BaseSignalGenerator):
    """
    Signal generator optimized for Gold (XAUUSD) trading
    Uses backtested setups with proven win rates
    """

    def __init__(self):
        super().__init__('XAUUSD')

        # Gold-specific parameters
        self.pip_value = 0.01
        self.min_atr = 0.5  # Minimum ATR for valid signals
        self.max_atr = 5.0  # Maximum ATR (avoid extreme volatility)

        # Additional gold-specific setups
        self.gold_setups = [
            # Session-based setups
            {
                'name': 'london_open_momentum',
                'tf': 'MINUTE_15',
                'dir': 'DYNAMIC',
                'conds': ['london_session', 'momentum_aligned'],
                'wr': 0.55,
                'mfe': 3.5,
                'tier': 'B'
            },
            {
                'name': 'ny_overlap_breakout',
                'tf': 'MINUTE_5',
                'dir': 'DYNAMIC',
                'conds': ['ny_overlap', 'breakout'],
                'wr': 0.50,
                'mfe': 4.0,
                'tier': 'B'
            },
            # VWAP setups
            {
                'name': 'vwap_deviation_long',
                'tf': 'MINUTE_15',
                'dir': 'BUY',
                'conds': ['below_vwap_2std', 'rsi<30'],
                'wr': 0.60,
                'mfe': 2.5,
                'tier': 'A'
            },
            {
                'name': 'vwap_deviation_short',
                'tf': 'MINUTE_15',
                'dir': 'SELL',
                'conds': ['above_vwap_2std', 'rsi>70'],
                'wr': 0.58,
                'mfe': 2.5,
                'tier': 'A'
            }
        ]

        logger.info("Gold Signal Generator initialized")

    def generate_signals(self) -> List[Signal]:
        """Generate all signals for Gold"""
        signals = []

        # Clear cache for fresh data
        self.clear_cache()

        # Check each setup from config
        for setup in self.setups:
            signal = self._check_setup(setup)
            if signal:
                signals.append(signal)

        # Check gold-specific setups
        for setup in self.gold_setups:
            signal = self._check_gold_setup(setup)
            if signal:
                signals.append(signal)

        # Multi-timeframe confluence check
        signals = self._filter_by_confluence(signals)

        return signals

    def _check_setup(self, setup: Dict) -> Optional[Signal]:
        """Check a standard setup from config"""
        setup_name = setup.get('name', '')

        # Check cooldown
        if not self.check_cooldown(setup_name):
            return None

        # Get candles for the timeframe
        timeframe = setup.get('tf', 'HOUR')
        candles = self.get_candles(timeframe, 200)

        if len(candles) < 50:
            return None

        # Calculate indicators
        indicators = self.indicator_calc.calculate_all(candles)

        # Validate ATR
        atr = indicators.get('atr', 0)
        if atr < self.min_atr or atr > self.max_atr:
            return None

        # Check conditions
        conditions = setup.get('conds', [])
        all_met, confidence = self.check_conditions(conditions, candles, indicators)

        if not all_met:
            return None

        # Apply win rate boost to confidence
        historical_wr = setup.get('wr', 0.5)
        confidence = (confidence + historical_wr) / 2

        # Create signal
        signal = self.create_signal(setup, candles, indicators, confidence)

        if signal:
            # Save and publish
            signal_id = self.save_signal(signal)
            if signal_id:
                self.publish_signal(signal)
                self._notify_signal(signal)

        return signal

    def _check_gold_setup(self, setup: Dict) -> Optional[Signal]:
        """Check gold-specific setups"""
        setup_name = setup.get('name', '')

        if not self.check_cooldown(setup_name):
            return None

        timeframe = setup.get('tf', 'MINUTE_15')
        candles = self.get_candles(timeframe, 200)

        if len(candles) < 50:
            return None

        indicators = self.indicator_calc.calculate_all(candles)

        # Check gold-specific conditions
        conditions = setup.get('conds', [])
        met_conditions = []
        confidence = 0

        for cond in conditions:
            if self._check_gold_condition(cond, candles, indicators):
                met_conditions.append(cond)
                confidence += 1 / len(conditions)

        if len(met_conditions) < len(conditions):
            return None

        # Determine direction for dynamic setups
        direction = setup.get('dir')
        if direction == 'DYNAMIC':
            direction = self._determine_direction(candles, indicators)
            if not direction:
                return None

        # Create a modified setup with actual direction
        actual_setup = setup.copy()
        actual_setup['dir'] = direction
        actual_setup['tier'] = setup.get('tier', 'B')

        signal = self.create_signal(actual_setup, candles, indicators, confidence)

        if signal:
            signal_id = self.save_signal(signal)
            if signal_id:
                self.publish_signal(signal)
                self._notify_signal(signal)

        return signal

    def _check_gold_condition(self, condition: str, candles: List,
                               indicators: Dict) -> bool:
        """Check gold-specific conditions"""
        condition = condition.lower()
        now = datetime.now()

        # Session conditions
        if condition == 'london_session':
            return 8 <= now.hour < 16  # UTC
        elif condition == 'ny_session':
            return 13 <= now.hour < 21
        elif condition == 'ny_overlap':
            return 13 <= now.hour < 16
        elif condition == 'asia_session':
            return 0 <= now.hour < 8

        # VWAP conditions
        vwap = indicators.get('vwap')
        bb_upper = indicators.get('bb_upper')
        bb_lower = indicators.get('bb_lower')

        if vwap and candles:
            price = candles[-1].close
            atr = indicators.get('atr', 1)

            if condition == 'below_vwap_2std':
                return price < vwap - (2 * atr)
            elif condition == 'above_vwap_2std':
                return price > vwap + (2 * atr)
            elif condition == 'at_vwap':
                return abs(price - vwap) < atr * 0.3

        # Momentum conditions
        macd_hist = indicators.get('macd_hist')
        if condition == 'momentum_aligned':
            if macd_hist is not None:
                return abs(macd_hist) > 0.1  # Sufficient momentum

        # Breakout conditions
        if condition == 'breakout' and len(candles) >= 20:
            recent_high = max(c.high for c in candles[-20:-1])
            recent_low = min(c.low for c in candles[-20:-1])
            current = candles[-1].close

            return current > recent_high or current < recent_low

        # Trend conditions
        ema_50 = indicators.get('ema_50')
        ema_200 = indicators.get('ema_200')

        if condition == 'uptrend' and ema_50 and ema_200:
            return ema_50 > ema_200
        elif condition == 'downtrend' and ema_50 and ema_200:
            return ema_50 < ema_200

        # Use base class check for standard conditions
        return self._check_single_condition(condition, candles, indicators)

    def _determine_direction(self, candles: List, indicators: Dict) -> Optional[str]:
        """Determine trade direction for dynamic setups"""
        if not candles:
            return None

        # Use multiple factors
        votes = {'BUY': 0, 'SELL': 0}

        # EMA trend
        ema_50 = indicators.get('ema_50')
        ema_200 = indicators.get('ema_200')
        if ema_50 and ema_200:
            if ema_50 > ema_200:
                votes['BUY'] += 1
            else:
                votes['SELL'] += 1

        # MACD
        macd_hist = indicators.get('macd_hist')
        if macd_hist is not None:
            if macd_hist > 0:
                votes['BUY'] += 1
            else:
                votes['SELL'] += 1

        # Recent price action
        if len(candles) >= 5:
            recent_close = candles[-1].close
            prev_close = candles[-5].close
            if recent_close > prev_close:
                votes['BUY'] += 1
            else:
                votes['SELL'] += 1

        # Return dominant direction
        if votes['BUY'] > votes['SELL']:
            return 'BUY'
        elif votes['SELL'] > votes['BUY']:
            return 'SELL'
        return None

    def _filter_by_confluence(self, signals: List[Signal]) -> List[Signal]:
        """Filter signals by multi-timeframe confluence"""
        if len(signals) <= 1:
            return signals

        # Group by direction
        buy_signals = [s for s in signals if s.direction == 'BUY']
        sell_signals = [s for s in signals if s.direction == 'SELL']

        # If conflicting signals, keep only the stronger direction
        if buy_signals and sell_signals:
            buy_confidence = sum(s.confidence for s in buy_signals)
            sell_confidence = sum(s.confidence for s in sell_signals)

            if buy_confidence > sell_confidence:
                signals = buy_signals
            else:
                signals = sell_signals

        # Sort by confidence and return top signals
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals[:3]  # Max 3 signals at a time

    def _notify_signal(self, signal: Signal):
        """Send Telegram notification for signal"""
        notifier.send_signal_alert(
            symbol=signal.symbol,
            direction=signal.direction,
            setup=signal.setup_name,
            confidence=signal.confidence,
            tier=signal.tier,
            entry=signal.entry_price,
            stop=signal.stop_loss,
            target=signal.take_profit
        )


class GoldSignalService:
    """Service wrapper for Gold Signal Generator"""

    def __init__(self):
        self.generator = GoldSignalGenerator()
        self.running = False
        self.scan_interval = 60  # Scan every minute

    def start(self):
        """Start the signal generation service"""
        logger.info("Starting Gold Signal Service...")
        self.running = True

        while self.running:
            try:
                # Generate signals
                signals = self.generator.generate_signals()

                if signals:
                    logger.info(f"Generated {len(signals)} signals")

                # Send heartbeat
                self._send_heartbeat(len(signals))

                # Sleep until next scan
                time.sleep(self.scan_interval)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Signal generation error: {e}")
                time.sleep(30)

    def stop(self):
        """Stop the service"""
        logger.info("Stopping Gold Signal Service...")
        self.running = False

    def _send_heartbeat(self, signal_count: int):
        """Send service heartbeat"""
        mq.send_heartbeat('gold_signal_generator', 'running', {
            'signals_generated': signal_count,
            'last_scan': datetime.now().isoformat()
        })
        db.update_service_state('gold_signal_generator', 'running')


def main():
    service = GoldSignalService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Gold Signal Generator crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
