"""
Base Signal Generator
Abstract base class for commodity-specific signal generators
"""

import abc
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

import sys
sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.indicators import IndicatorCalculator, Candle

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Trading signal data structure"""
    symbol: str
    symbol_id: int
    timestamp: datetime
    timeframe: str
    direction: str  # BUY or SELL
    setup_name: str
    conditions: List[str]
    confidence: float
    tier: str  # A, B, or C
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    target_bot: str = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'symbol_id': self.symbol_id,
            'timestamp': self.timestamp,
            'timeframe': self.timeframe,
            'direction': self.direction,
            'setup_name': self.setup_name,
            'conditions': self.conditions,
            'confidence': self.confidence,
            'tier': self.tier,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'target_bot': self.target_bot,
            'status': 'pending',
            'atr': self.atr,
            'metadata': self.metadata
        }


class BaseSignalGenerator(abc.ABC):
    """Base class for signal generators"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.symbol_id = db.get_symbol_id(symbol)
        self.symbol_config = config.get_symbol_config(symbol)
        self.setups = config.get_all_setups()
        self.indicator_calc = IndicatorCalculator()

        # Signal cooldowns (setup_name -> last_signal_time)
        self.cooldowns: Dict[str, datetime] = {}
        self.default_cooldown = timedelta(minutes=30)

        # Cache for recent candles
        self.candle_cache: Dict[str, List[Candle]] = {}

        logger.info(f"Initialized {self.__class__.__name__} for {symbol}")

    @abc.abstractmethod
    def generate_signals(self) -> List[Signal]:
        """Generate signals for the symbol - implemented by subclasses"""
        pass

    def get_candles(self, timeframe: str, count: int = 200) -> List[Candle]:
        """Get candles from database, use cache if available"""
        cache_key = f"{timeframe}_{count}"

        # Check cache
        cached = self.candle_cache.get(cache_key)
        if cached and len(cached) >= count:
            return cached[-count:]

        # Fetch from database
        data = db.get_price_data(self.symbol_id, timeframe, limit=count)

        if not data:
            return []

        # Sort ascending by timestamp
        data = sorted(data, key=lambda x: x['timestamp'])

        candles = [
            Candle(
                timestamp=d['timestamp'],
                open=float(d['open']),
                high=float(d['high']),
                low=float(d['low']),
                close=float(d['close']),
                volume=float(d.get('volume', 0))
            )
            for d in data
        ]

        self.candle_cache[cache_key] = candles
        return candles

    def clear_cache(self):
        """Clear candle cache"""
        self.candle_cache.clear()

    def check_cooldown(self, setup_name: str) -> bool:
        """Check if setup is on cooldown"""
        last_signal = self.cooldowns.get(setup_name)
        if not last_signal:
            return True
        return datetime.now() - last_signal >= self.default_cooldown

    def set_cooldown(self, setup_name: str):
        """Set cooldown for a setup"""
        self.cooldowns[setup_name] = datetime.now()

    def check_conditions(self, conditions: List[str], candles: List[Candle],
                         indicators: Dict) -> Tuple[bool, float]:
        """
        Check if all conditions are met

        Returns:
            (all_met: bool, confidence: float)
        """
        if not candles or not indicators:
            return False, 0

        met_count = 0
        total = len(conditions)

        for cond in conditions:
            if self._check_single_condition(cond, candles, indicators):
                met_count += 1

        all_met = met_count == total
        confidence = met_count / total if total > 0 else 0

        return all_met, confidence

    def _check_single_condition(self, condition: str, candles: List[Candle],
                                 indicators: Dict) -> bool:
        """Check a single condition"""
        condition = condition.lower().strip()

        # Day conditions
        current_day = datetime.now().strftime('%A').lower()
        if condition == 'monday':
            return current_day == 'monday'
        elif condition == 'tuesday':
            return current_day == 'tuesday'
        elif condition == 'wednesday':
            return current_day == 'wednesday'
        elif condition == 'thursday':
            return current_day == 'thursday'
        elif condition == 'friday':
            return current_day == 'friday'
        elif condition == 'sunday':
            return current_day == 'sunday'

        # RSI conditions
        rsi = indicators.get('rsi')
        if rsi is not None:
            if condition == 'rsi<20':
                return rsi < 20
            elif condition == 'rsi<30':
                return rsi < 30
            elif condition == 'rsi<40':
                return rsi < 40
            elif condition == 'rsi>60':
                return rsi > 60
            elif condition == 'rsi>70':
                return rsi > 70
            elif condition == 'rsi>80':
                return rsi > 80

        # Stochastic conditions
        stoch = indicators.get('stoch_k')
        if stoch is not None:
            if condition == 'stoch<20':
                return stoch < 20
            elif condition == 'stoch<30':
                return stoch < 30
            elif condition == 'stoch>70':
                return stoch > 70
            elif condition == 'stoch>80':
                return stoch > 80

        # Pattern conditions
        pattern_engulfing = indicators.get('pattern_engulfing')
        pattern_pin = indicators.get('pattern_pin')
        pattern_fvg = indicators.get('pattern_fvg')
        pattern_bos = indicators.get('pattern_bos')

        if condition == 'bull_engulfing':
            return pattern_engulfing == 'bull_engulfing'
        elif condition == 'bear_engulfing':
            return pattern_engulfing == 'bear_engulfing'
        elif condition == 'bull_pin':
            return pattern_pin == 'bull_pin'
        elif condition == 'bear_pin':
            return pattern_pin == 'bear_pin'
        elif condition == 'bull_fvg':
            return pattern_fvg == 'bull_fvg'
        elif condition == 'bear_fvg':
            return pattern_fvg == 'bear_fvg'
        elif condition == 'bull_bos':
            return pattern_bos == 'bull_bos'
        elif condition == 'bear_bos':
            return pattern_bos == 'bear_bos'

        # Candle color conditions
        if candles:
            latest = candles[-1]
            if condition == 'green_candle' or condition == 'green':
                return latest.close > latest.open
            elif condition == 'red_candle' or condition == 'red':
                return latest.close < latest.open

        # EMA conditions
        if candles and indicators.get('ema_50') and indicators.get('ema_200'):
            price = candles[-1].close
            if condition == 'above_ema50':
                return price > indicators['ema_50']
            elif condition == 'below_ema50':
                return price < indicators['ema_50']
            elif condition == 'above_ema200':
                return price > indicators['ema_200']
            elif condition == 'below_ema200':
                return price < indicators['ema_200']
            elif condition == 'ema50_above_ema200':
                return indicators['ema_50'] > indicators['ema_200']
            elif condition == 'ema50_below_ema200':
                return indicators['ema_50'] < indicators['ema_200']

        logger.debug(f"Unknown condition: {condition}")
        return False

    def calculate_levels(self, direction: str, entry: float, atr: float,
                         target_rr: float = 5.0, stop_atr_mult: float = 1.0) -> Tuple[float, float]:
        """Calculate stop loss and take profit levels"""
        stop_distance = atr * stop_atr_mult

        if direction == 'BUY':
            stop_loss = entry - stop_distance
            take_profit = entry + (stop_distance * target_rr)
        else:  # SELL
            stop_loss = entry + stop_distance
            take_profit = entry - (stop_distance * target_rr)

        return round(stop_loss, 2), round(take_profit, 2)

    def assign_target_bot(self, timeframe: str, confidence: float, tier: str) -> str:
        """Assign signal to appropriate bot based on timeframe and confidence"""
        # Sniper bot for very high confidence
        if confidence >= 0.85:
            return 'sniper'

        # Based on timeframe
        if timeframe in ['MINUTE', 'MINUTE_5']:
            return 'scalper'
        elif timeframe in ['MINUTE_15', 'HOUR']:
            if confidence >= 0.6:
                return 'day_trader'
            return 'swing'
        elif timeframe in ['HOUR_4', 'DAY']:
            return 'position'

        return 'day_trader'  # Default

    def create_signal(self, setup: Dict, candles: List[Candle],
                      indicators: Dict, confidence: float) -> Optional[Signal]:
        """Create a signal from a setup"""
        if not candles:
            return None

        latest = candles[-1]
        atr = indicators.get('atr', 1.0)

        # Get tier-specific parameters
        tier = setup.get('tier', 'B')
        tier_config = config.get(f'signal_tiers.{tier}', {})
        weight = tier_config.get('weight', 1.0)

        # Adjust confidence by tier weight
        adjusted_confidence = min(1.0, confidence * weight)

        # Get bot config for R:R
        target_bot = self.assign_target_bot(setup['tf'], adjusted_confidence, tier)
        bot_config = config.get_bot_config(target_bot)
        target_rr = bot_config.get('target_rr', 5.0)
        stop_atr = bot_config.get('stop_atr_multiplier', 1.0)

        # Calculate levels
        entry = latest.close
        stop_loss, take_profit = self.calculate_levels(
            setup['dir'], entry, atr, target_rr, stop_atr
        )

        signal = Signal(
            symbol=self.symbol,
            symbol_id=self.symbol_id,
            timestamp=datetime.now(),
            timeframe=setup['tf'],
            direction=setup['dir'],
            setup_name=setup['name'],
            conditions=setup.get('conds', []),
            confidence=adjusted_confidence,
            tier=tier,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr=atr,
            target_bot=target_bot,
            metadata={
                'historical_wr': setup.get('wr', 0),
                'historical_mfe': setup.get('mfe', 0),
                'rsi': indicators.get('rsi'),
                'stoch': indicators.get('stoch_k')
            }
        )

        return signal

    def save_signal(self, signal: Signal) -> int:
        """Save signal to database"""
        signal_id = db.insert_signal(signal.to_dict())
        if signal_id:
            logger.info(f"Saved signal {signal_id}: {signal.setup_name} {signal.direction}")
            self.set_cooldown(signal.setup_name)
        return signal_id

    def publish_signal(self, signal: Signal):
        """Publish signal to message queue"""
        channel = f'signals:{self.symbol.lower()}'
        mq.publish(channel, signal.to_dict())
        logger.info(f"Published signal to {channel}")


class MultiTimeframeAnalyzer:
    """Analyze signals across multiple timeframes for confluence"""

    def __init__(self):
        self.timeframe_weights = {
            'DAY': 1.5,
            'HOUR_4': 1.3,
            'HOUR': 1.2,
            'MINUTE_15': 1.1,
            'MINUTE_5': 1.0,
            'MINUTE': 0.9
        }

    def calculate_confluence(self, signals: List[Signal]) -> float:
        """Calculate confluence score from multiple timeframe signals"""
        if not signals:
            return 0

        # Group by direction
        buy_weight = 0
        sell_weight = 0

        for sig in signals:
            weight = self.timeframe_weights.get(sig.timeframe, 1.0)
            if sig.direction == 'BUY':
                buy_weight += weight * sig.confidence
            else:
                sell_weight += weight * sig.confidence

        # Confluence is the dominant direction's relative strength
        total_weight = buy_weight + sell_weight
        if total_weight == 0:
            return 0

        return max(buy_weight, sell_weight) / total_weight

    def get_aligned_direction(self, signals: List[Signal]) -> Optional[str]:
        """Get the direction with most confluence"""
        buy_score = sum(1 for s in signals if s.direction == 'BUY')
        sell_score = sum(1 for s in signals if s.direction == 'SELL')

        if buy_score > sell_score:
            return 'BUY'
        elif sell_score > buy_score:
            return 'SELL'
        return None
