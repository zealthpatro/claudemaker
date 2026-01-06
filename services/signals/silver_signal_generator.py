#!/usr/bin/env python3
"""
Silver Signal Generator Microservice
Generates buy/sell signals for XAGUSD based on adapted gold setups
and silver-specific patterns including gold/silver ratio analysis
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
        logging.FileHandler('/home/user/claudemaker/logs/signals/silver.log')
    ]
)
logger = logging.getLogger('silver_signal_generator')


class SilverSignalGenerator(BaseSignalGenerator):
    """
    Signal generator optimized for Silver (XAGUSD) trading
    Uses adapted gold setups plus silver-specific analysis
    """

    def __init__(self):
        super().__init__('XAGUSD')

        # Silver-specific parameters
        self.pip_value = 0.001
        self.min_atr = 0.02  # Silver has different volatility profile
        self.max_atr = 0.5

        # Gold/Silver ratio settings
        self.gold_symbol_id = db.get_symbol_id('XAUUSD')
        self.typical_gs_ratio = 80  # Historical average
        self.ratio_deviation_threshold = 5  # Standard deviations

        # Silver-specific setups
        self.silver_setups = [
            # Silver tends to be more volatile and momentum-driven
            {
                'name': 'silver_momentum_surge',
                'tf': 'MINUTE_5',
                'dir': 'DYNAMIC',
                'conds': ['momentum_breakout', 'volume_spike'],
                'wr': 0.48,
                'mfe': 6.0,
                'tier': 'B'
            },
            {
                'name': 'silver_mean_reversion',
                'tf': 'MINUTE_15',
                'dir': 'DYNAMIC',
                'conds': ['extreme_rsi', 'bb_pierce'],
                'wr': 0.55,
                'mfe': 3.0,
                'tier': 'A'
            },
            # Gold/Silver ratio trades
            {
                'name': 'gs_ratio_long',
                'tf': 'HOUR',
                'dir': 'BUY',
                'conds': ['gs_ratio_high', 'silver_oversold'],
                'wr': 0.52,
                'mfe': 5.0,
                'tier': 'B'
            },
            {
                'name': 'gs_ratio_short',
                'tf': 'HOUR',
                'dir': 'SELL',
                'conds': ['gs_ratio_low', 'silver_overbought'],
                'wr': 0.50,
                'mfe': 4.5,
                'tier': 'B'
            },
            # Silver follows gold with lag
            {
                'name': 'gold_lead_follow',
                'tf': 'MINUTE_15',
                'dir': 'DYNAMIC',
                'conds': ['gold_moved', 'silver_lagging'],
                'wr': 0.58,
                'mfe': 2.5,
                'tier': 'A'
            }
        ]

        # Cache for gold prices (for correlation analysis)
        self.gold_prices: List[float] = []

        logger.info("Silver Signal Generator initialized")

    def generate_signals(self) -> List[Signal]:
        """Generate all signals for Silver"""
        signals = []

        # Clear cache
        self.clear_cache()

        # Update gold prices for ratio calculation
        self._update_gold_prices()

        # Check adapted setups from config (same as gold but for silver)
        for setup in self.setups:
            signal = self._check_adapted_setup(setup)
            if signal:
                signals.append(signal)

        # Check silver-specific setups
        for setup in self.silver_setups:
            signal = self._check_silver_setup(setup)
            if signal:
                signals.append(signal)

        # Apply confluence filter
        signals = self._filter_signals(signals)

        return signals

    def _update_gold_prices(self):
        """Update gold prices for correlation analysis"""
        if self.gold_symbol_id:
            gold_data = db.get_price_data(self.gold_symbol_id, 'MINUTE_15', limit=50)
            if gold_data:
                gold_data = sorted(gold_data, key=lambda x: x['timestamp'])
                self.gold_prices = [float(d['close']) for d in gold_data]

    def _check_adapted_setup(self, setup: Dict) -> Optional[Signal]:
        """Check setups adapted from gold"""
        setup_name = f"silver_{setup.get('name', '')}"

        if not self.check_cooldown(setup_name):
            return None

        timeframe = setup.get('tf', 'HOUR')
        candles = self.get_candles(timeframe, 200)

        if len(candles) < 50:
            return None

        indicators = self.indicator_calc.calculate_all(candles)

        # Validate ATR for silver's volatility
        atr = indicators.get('atr', 0)
        if atr < self.min_atr or atr > self.max_atr:
            return None

        # Check conditions
        conditions = setup.get('conds', [])
        all_met, confidence = self.check_conditions(conditions, candles, indicators)

        if not all_met:
            return None

        # Silver typically has lower win rates but higher R:R potential
        historical_wr = setup.get('wr', 0.5) * 0.95  # Slight reduction for silver
        confidence = (confidence + historical_wr) / 2

        # Create signal with silver-specific name
        adapted_setup = setup.copy()
        adapted_setup['name'] = setup_name
        adapted_setup['tier'] = setup.get('tier', 'B')

        signal = self.create_signal(adapted_setup, candles, indicators, confidence)

        if signal:
            signal_id = self.save_signal(signal)
            if signal_id:
                self.publish_signal(signal)
                self._notify_signal(signal)

        return signal

    def _check_silver_setup(self, setup: Dict) -> Optional[Signal]:
        """Check silver-specific setups"""
        setup_name = setup.get('name', '')

        if not self.check_cooldown(setup_name):
            return None

        timeframe = setup.get('tf', 'MINUTE_15')
        candles = self.get_candles(timeframe, 200)

        if len(candles) < 50:
            return None

        indicators = self.indicator_calc.calculate_all(candles)

        # Check silver-specific conditions
        conditions = setup.get('conds', [])
        met_count = 0

        for cond in conditions:
            if self._check_silver_condition(cond, candles, indicators):
                met_count += 1

        if met_count < len(conditions):
            return None

        confidence = met_count / len(conditions) if conditions else 0

        # Determine direction for dynamic setups
        direction = setup.get('dir')
        if direction == 'DYNAMIC':
            direction = self._determine_silver_direction(candles, indicators)
            if not direction:
                return None

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

    def _check_silver_condition(self, condition: str, candles: List,
                                 indicators: Dict) -> bool:
        """Check silver-specific conditions"""
        condition = condition.lower()

        # Gold/Silver ratio conditions
        if condition.startswith('gs_ratio'):
            return self._check_gs_ratio_condition(condition, candles)

        # Momentum conditions
        if condition == 'momentum_breakout':
            return self._check_momentum_breakout(candles, indicators)

        if condition == 'volume_spike':
            return self._check_volume_spike(candles)

        # Mean reversion conditions
        if condition == 'extreme_rsi':
            rsi = indicators.get('rsi')
            return rsi is not None and (rsi < 20 or rsi > 80)

        if condition == 'bb_pierce':
            return self._check_bb_pierce(candles, indicators)

        # Gold lead conditions
        if condition == 'gold_moved':
            return self._check_gold_moved()

        if condition == 'silver_lagging':
            return self._check_silver_lagging(candles)

        # Overbought/oversold for ratio trades
        if condition == 'silver_oversold':
            rsi = indicators.get('rsi')
            return rsi is not None and rsi < 35

        if condition == 'silver_overbought':
            rsi = indicators.get('rsi')
            return rsi is not None and rsi > 65

        # Fall back to base class
        return self._check_single_condition(condition, candles, indicators)

    def _check_gs_ratio_condition(self, condition: str, candles: List) -> bool:
        """Check Gold/Silver ratio conditions"""
        if not candles or not self.gold_prices:
            return False

        silver_price = candles[-1].close
        gold_price = self.gold_prices[-1] if self.gold_prices else 0

        if silver_price <= 0 or gold_price <= 0:
            return False

        current_ratio = gold_price / silver_price

        if condition == 'gs_ratio_high':
            # Silver undervalued relative to gold
            return current_ratio > self.typical_gs_ratio * 1.1
        elif condition == 'gs_ratio_low':
            # Silver overvalued relative to gold
            return current_ratio < self.typical_gs_ratio * 0.9

        return False

    def _check_momentum_breakout(self, candles: List, indicators: Dict) -> bool:
        """Check for momentum breakout"""
        if len(candles) < 20:
            return False

        # Recent range
        recent_high = max(c.high for c in candles[-20:-1])
        recent_low = min(c.low for c in candles[-20:-1])
        current = candles[-1].close

        # Check for breakout with momentum
        macd_hist = indicators.get('macd_hist', 0)

        if current > recent_high and macd_hist > 0:
            return True
        if current < recent_low and macd_hist < 0:
            return True

        return False

    def _check_volume_spike(self, candles: List) -> bool:
        """Check for volume spike"""
        if len(candles) < 20:
            return False

        avg_volume = sum(c.volume for c in candles[-20:-1]) / 19
        current_volume = candles[-1].volume

        if avg_volume > 0:
            return current_volume > avg_volume * 1.5

        return False

    def _check_bb_pierce(self, candles: List, indicators: Dict) -> bool:
        """Check if price pierced Bollinger Bands"""
        if not candles:
            return False

        bb_upper = indicators.get('bb_upper')
        bb_lower = indicators.get('bb_lower')
        current = candles[-1]

        if bb_upper and bb_lower:
            return current.high > bb_upper or current.low < bb_lower

        return False

    def _check_gold_moved(self) -> bool:
        """Check if gold made a significant move"""
        if len(self.gold_prices) < 10:
            return False

        recent_change = (self.gold_prices[-1] - self.gold_prices[-5]) / self.gold_prices[-5]
        return abs(recent_change) > 0.005  # 0.5% move

    def _check_silver_lagging(self, candles: List) -> bool:
        """Check if silver is lagging gold's move"""
        if len(candles) < 10 or len(self.gold_prices) < 10:
            return False

        gold_change = (self.gold_prices[-1] - self.gold_prices[-5]) / self.gold_prices[-5]
        silver_change = (candles[-1].close - candles[-5].close) / candles[-5].close

        # Silver should move in same direction but less
        if gold_change > 0 and 0 < silver_change < gold_change * 0.5:
            return True
        if gold_change < 0 and gold_change * 0.5 < silver_change < 0:
            return True

        return False

    def _determine_silver_direction(self, candles: List, indicators: Dict) -> Optional[str]:
        """Determine trade direction for dynamic setups"""
        votes = {'BUY': 0, 'SELL': 0}

        # EMA trend
        ema_50 = indicators.get('ema_50')
        ema_200 = indicators.get('ema_200')
        if ema_50 and ema_200:
            if ema_50 > ema_200:
                votes['BUY'] += 1
            else:
                votes['SELL'] += 1

        # RSI
        rsi = indicators.get('rsi')
        if rsi:
            if rsi < 30:
                votes['BUY'] += 1
            elif rsi > 70:
                votes['SELL'] += 1

        # Gold direction (silver tends to follow)
        if len(self.gold_prices) >= 5:
            gold_trend = self.gold_prices[-1] - self.gold_prices[-5]
            if gold_trend > 0:
                votes['BUY'] += 1
            else:
                votes['SELL'] += 1

        # Recent price action
        if len(candles) >= 5:
            recent_change = candles[-1].close - candles[-5].close
            if recent_change > 0:
                votes['BUY'] += 0.5  # Less weight
            else:
                votes['SELL'] += 0.5

        if votes['BUY'] > votes['SELL']:
            return 'BUY'
        elif votes['SELL'] > votes['BUY']:
            return 'SELL'
        return None

    def _filter_signals(self, signals: List[Signal]) -> List[Signal]:
        """Filter and prioritize signals"""
        if len(signals) <= 1:
            return signals

        # Group by direction
        buy_signals = [s for s in signals if s.direction == 'BUY']
        sell_signals = [s for s in signals if s.direction == 'SELL']

        # Keep only consistent direction
        if buy_signals and sell_signals:
            buy_conf = sum(s.confidence for s in buy_signals)
            sell_conf = sum(s.confidence for s in sell_signals)
            signals = buy_signals if buy_conf > sell_conf else sell_signals

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals[:2]  # Max 2 signals

    def _notify_signal(self, signal: Signal):
        """Send notification"""
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


class SilverSignalService:
    """Service wrapper for Silver Signal Generator"""

    def __init__(self):
        self.generator = SilverSignalGenerator()
        self.running = False
        self.scan_interval = 60

    def start(self):
        """Start the service"""
        logger.info("Starting Silver Signal Service...")
        self.running = True

        while self.running:
            try:
                signals = self.generator.generate_signals()

                if signals:
                    logger.info(f"Generated {len(signals)} signals")

                self._send_heartbeat(len(signals))
                time.sleep(self.scan_interval)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(30)

    def stop(self):
        logger.info("Stopping Silver Signal Service...")
        self.running = False

    def _send_heartbeat(self, signal_count: int):
        mq.send_heartbeat('silver_signal_generator', 'running', {
            'signals_generated': signal_count,
            'last_scan': datetime.now().isoformat()
        })
        db.update_service_state('silver_signal_generator', 'running')


def main():
    service = SilverSignalService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notifier.send_system_alert('critical', f'Silver Signal Generator crashed: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
