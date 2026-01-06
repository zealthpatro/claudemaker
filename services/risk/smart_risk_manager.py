#!/usr/bin/env python3
"""
Smart Risk Manager - Intelligent position and risk management
- Dynamic risk based on confidence and TP probability
- Max 5% daily margin across all trades
- Smart trade replacement (close weak trades for better setups)
"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.capital_api import CapitalAPI
from services.shared.notifications import notify

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/trader/algo_trading/logs/smart_risk.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('smart-risk-manager')


@dataclass
class TradeScore:
    """Score for evaluating trade quality"""
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    current_pnl: float
    current_r: float
    recovery_difficulty: float  # 0-100, higher = harder to recover
    tp_probability: float       # 0-100, probability of hitting TP
    overall_score: float        # Combined score for comparison


class SmartRiskManager:
    """Intelligent risk and position management"""

    def __init__(self):
        self.api = CapitalAPI()

        # Risk Parameters
        self.max_daily_margin_pct = 5.0      # Max 5% of margin at risk per day
        self.max_single_trade_pct = 2.0      # Max 2% per single trade
        self.max_hourly_drawdown_pct = 3.0   # Max 3% loss per hour
        self.eod_close_hour = 20
        self.eod_close_minute = 30

        # Confidence-based risk tiers
        self.risk_tiers = {
            'ultra_high': {'min_confidence': 90, 'max_risk_pct': 2.0, 'tp_multiplier': 1.5},
            'high':       {'min_confidence': 80, 'max_risk_pct': 1.5, 'tp_multiplier': 1.2},
            'medium':     {'min_confidence': 70, 'max_risk_pct': 1.0, 'tp_multiplier': 1.0},
            'low':        {'min_confidence': 60, 'max_risk_pct': 0.5, 'tp_multiplier': 0.8},
        }

        # State
        self.current_balance = 0
        self.high_water_mark = 0
        self.daily_risk_used = 0
        self.daily_margin_used = 0
        self.open_positions: Dict[str, TradeScore] = {}
        self.hourly_pnl = defaultdict(float)
        self.trading_halted = False
        self.halt_reason = ""

        self._init_state()

    def _init_state(self):
        """Initialize from API and database"""
        try:
            account = self.api.get_account_info()
            if account:
                self.current_balance = float(account.get('balance', 10000))
                self.high_water_mark = self._get_high_water_mark()
                logger.info(f"Balance: ${self.current_balance:.2f}, HWM: ${self.high_water_mark:.2f}")
        except Exception as e:
            logger.error(f"Init error: {e}")
            self.current_balance = 10000
            self.high_water_mark = 10000

    def _get_high_water_mark(self) -> float:
        """Get high water mark from storage"""
        try:
            result = mq.get('high_water_mark')
            if result:
                return float(result.get('value', self.current_balance))
        except:
            pass
        return self.current_balance

    def _save_high_water_mark(self, hwm: float):
        """Save high water mark"""
        mq.set('high_water_mark', {'value': hwm}, ttl=86400 * 30)

    # ============= Confidence-Based Risk Calculation =============

    def calculate_allowed_risk(self, signal: Dict) -> Dict:
        """
        Calculate allowed risk based on signal confidence and TP probability
        Returns: {allowed: bool, risk_pct: float, reason: str}
        """
        confidence = signal.get('confidence', 50)
        tp_probability = self._estimate_tp_probability(signal)

        # Determine risk tier
        tier = self._get_risk_tier(confidence)
        base_risk = tier['max_risk_pct']

        # Adjust risk based on TP probability
        if tp_probability >= 80:
            # High TP probability - can risk more
            adjusted_risk = base_risk * 1.3
        elif tp_probability >= 60:
            adjusted_risk = base_risk * 1.1
        elif tp_probability < 40:
            # Low TP probability - reduce risk
            adjusted_risk = base_risk * 0.7
        else:
            adjusted_risk = base_risk

        # Check daily margin limit
        remaining_daily_margin = self.max_daily_margin_pct - self.daily_margin_used
        if adjusted_risk > remaining_daily_margin:
            if remaining_daily_margin <= 0:
                return {
                    'allowed': False,
                    'risk_pct': 0,
                    'reason': f'Daily margin limit reached ({self.max_daily_margin_pct}%)'
                }
            adjusted_risk = remaining_daily_margin

        # Cap at max single trade
        adjusted_risk = min(adjusted_risk, self.max_single_trade_pct)

        return {
            'allowed': True,
            'risk_pct': adjusted_risk,
            'confidence': confidence,
            'tp_probability': tp_probability,
            'tier': tier,
            'reason': f'Tier: {self._get_tier_name(confidence)}, TP prob: {tp_probability:.0f}%'
        }

    def _get_risk_tier(self, confidence: float) -> Dict:
        """Get risk tier based on confidence"""
        for tier_name, tier in self.risk_tiers.items():
            if confidence >= tier['min_confidence']:
                return tier
        return self.risk_tiers['low']

    def _get_tier_name(self, confidence: float) -> str:
        """Get tier name for logging"""
        for name, tier in self.risk_tiers.items():
            if confidence >= tier['min_confidence']:
                return name
        return 'low'

    def _estimate_tp_probability(self, signal: Dict) -> float:
        """
        Estimate probability of hitting take profit based on:
        - Historical setup performance
        - Current market conditions
        - Multi-timeframe confluence
        """
        base_probability = 50.0

        # Confidence boost
        confidence = signal.get('confidence', 50)
        if confidence >= 85:
            base_probability += 20
        elif confidence >= 75:
            base_probability += 10
        elif confidence >= 65:
            base_probability += 5

        # Tier boost
        tier = signal.get('tier', 'C')
        if tier == 'A':
            base_probability += 15
        elif tier == 'B':
            base_probability += 8

        # Setup historical performance
        setup_name = signal.get('setup_name', '')
        setup_stats = self._get_setup_stats(setup_name)
        if setup_stats:
            historical_win_rate = setup_stats.get('win_rate', 50)
            # Blend historical with base
            base_probability = (base_probability + historical_win_rate) / 2

        # Risk/Reward adjustment
        entry = signal.get('entry_price', 0)
        sl = signal.get('stop_loss', 0)
        tp = signal.get('take_profit', 0)
        if entry and sl and tp:
            rr_ratio = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 1
            if rr_ratio >= 3:
                # Higher R:R is harder to hit
                base_probability -= 10
            elif rr_ratio <= 1.5:
                # Lower R:R is easier
                base_probability += 5

        return min(95, max(20, base_probability))

    def _get_setup_stats(self, setup_name: str) -> Optional[Dict]:
        """Get historical stats for a setup"""
        try:
            result = db.fetch_one("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(pnl_r) as avg_r
                FROM trades t
                JOIN signals s ON t.signal_id = s.id
                WHERE s.setup_name = %s
                AND t.status = 'closed'
                AND t.closed_at >= NOW() - INTERVAL '30 days'
            """, (setup_name,))

            if result and result.get('total', 0) > 5:
                total = result['total']
                wins = result['wins'] or 0
                return {
                    'total': total,
                    'wins': wins,
                    'win_rate': (wins / total * 100) if total > 0 else 50,
                    'avg_r': float(result['avg_r'] or 0)
                }
        except:
            pass
        return None

    # ============= Smart Trade Replacement =============

    def evaluate_trade_replacement(self, new_signal: Dict) -> Dict:
        """
        Evaluate if we should close existing trades to take a new one
        Returns: {should_replace: bool, trades_to_close: list, reason: str}
        """
        if not self.open_positions:
            return {'should_replace': False, 'trades_to_close': [], 'reason': 'No open positions'}

        # Score the new signal
        new_score = self._score_signal(new_signal)

        # Score all open positions
        position_scores = []
        for trade_id, pos in self.open_positions.items():
            score = self._calculate_recovery_score(pos)
            position_scores.append((trade_id, pos, score))

        # Sort by score (lowest = worst performers)
        position_scores.sort(key=lambda x: x[2])

        # Find trades worth replacing
        trades_to_close = []
        freed_margin = 0

        for trade_id, pos, score in position_scores:
            # Compare with new signal
            if new_score > score + 20:  # New signal must be significantly better
                # Check if position is struggling
                if pos.current_r < 0 and pos.recovery_difficulty > 60:
                    trades_to_close.append({
                        'trade_id': trade_id,
                        'symbol': pos.symbol,
                        'current_r': pos.current_r,
                        'recovery_difficulty': pos.recovery_difficulty,
                        'reason': 'Struggling position with better opportunity available'
                    })

                    # Estimate margin that would be freed
                    # (simplified - in reality would need position size * margin rate)
                    freed_margin += 1.0  # Placeholder

        if trades_to_close:
            return {
                'should_replace': True,
                'trades_to_close': trades_to_close,
                'new_signal_score': new_score,
                'reason': f'Found {len(trades_to_close)} weaker positions to replace'
            }

        return {
            'should_replace': False,
            'trades_to_close': [],
            'reason': 'No positions worth replacing for this signal'
        }

    def _score_signal(self, signal: Dict) -> float:
        """Score a new signal (0-100)"""
        score = 0

        # Confidence (0-40 points)
        confidence = signal.get('confidence', 50)
        score += (confidence / 100) * 40

        # Tier (0-20 points)
        tier = signal.get('tier', 'C')
        tier_scores = {'A': 20, 'B': 12, 'C': 5}
        score += tier_scores.get(tier, 5)

        # TP probability (0-25 points)
        tp_prob = self._estimate_tp_probability(signal)
        score += (tp_prob / 100) * 25

        # Risk/Reward (0-15 points)
        entry = signal.get('entry_price', 0)
        sl = signal.get('stop_loss', 0)
        tp = signal.get('take_profit', 0)
        if entry and sl and tp and abs(entry - sl) > 0:
            rr = abs(tp - entry) / abs(entry - sl)
            if rr >= 3:
                score += 15
            elif rr >= 2:
                score += 10
            elif rr >= 1.5:
                score += 5

        return min(100, score)

    def _calculate_recovery_score(self, position: TradeScore) -> float:
        """
        Calculate how likely a position is to recover
        Lower score = harder to recover = better candidate for closing
        """
        score = 50  # Start neutral

        # Current P&L impact
        if position.current_r >= 1:
            score += 30  # Already profitable
        elif position.current_r >= 0:
            score += 15  # At breakeven
        elif position.current_r >= -0.5:
            score += 5   # Slight loss
        elif position.current_r >= -1:
            score -= 10  # Losing
        else:
            score -= 25  # Significant loss

        # Distance to TP vs SL
        if position.current_price and position.entry_price:
            if position.direction == 'BUY':
                dist_to_tp = position.take_profit - position.current_price
                dist_to_sl = position.current_price - position.stop_loss
            else:
                dist_to_tp = position.current_price - position.take_profit
                dist_to_sl = position.stop_loss - position.current_price

            if dist_to_sl > 0 and dist_to_tp > 0:
                ratio = dist_to_tp / dist_to_sl
                if ratio < 1:
                    score += 15  # Closer to TP
                elif ratio > 3:
                    score -= 20  # Much closer to SL

        # Original confidence
        score += (position.confidence / 100) * 20

        return max(0, min(100, score))

    # ============= Position Tracking =============

    def update_positions(self):
        """Update all open position scores"""
        try:
            positions = self.api.get_positions()
            self.daily_margin_used = 0

            for pos in positions:
                deal_id = pos.get('position', {}).get('dealId', '')
                if not deal_id:
                    continue

                position_data = pos.get('position', {})
                market_data = pos.get('market', {})

                entry = float(position_data.get('openLevel', 0))
                current = float(market_data.get('bid', entry))
                sl = float(position_data.get('stopLevel', 0))
                tp = float(position_data.get('limitLevel', 0))
                direction = position_data.get('direction', 'BUY')
                size = float(position_data.get('size', 0))
                pnl = float(position_data.get('unrealisedPnL', 0))

                # Calculate R value
                risk_per_unit = abs(entry - sl) if sl else 1
                if direction == 'BUY':
                    movement = current - entry
                else:
                    movement = entry - current
                current_r = movement / risk_per_unit if risk_per_unit > 0 else 0

                # Create/update score
                trade_score = TradeScore(
                    trade_id=deal_id,
                    symbol=market_data.get('epic', 'UNKNOWN'),
                    direction=direction,
                    entry_price=entry,
                    current_price=current,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=70,  # Default, would need to look up original signal
                    current_pnl=pnl,
                    current_r=current_r,
                    recovery_difficulty=0,
                    tp_probability=0,
                    overall_score=0
                )

                # Calculate derived scores
                trade_score.recovery_difficulty = 100 - self._calculate_recovery_score(trade_score)
                trade_score.overall_score = self._calculate_recovery_score(trade_score)

                self.open_positions[deal_id] = trade_score

                # Track margin used (simplified)
                margin_used = size * entry * 0.05  # Assuming 5% margin requirement
                self.daily_margin_used += (margin_used / self.current_balance) * 100

        except Exception as e:
            logger.error(f"Position update error: {e}")

    # ============= Risk Checks =============

    def check_can_trade(self, signal: Dict) -> Dict:
        """
        Comprehensive check if a new trade is allowed
        Returns: {allowed: bool, risk_pct: float, action: str, reason: str}
        """
        # Check if trading is halted
        if self.trading_halted:
            return {
                'allowed': False,
                'risk_pct': 0,
                'action': 'REJECT',
                'reason': f'Trading halted: {self.halt_reason}'
            }

        # Check hourly drawdown
        if self._check_hourly_drawdown():
            return {
                'allowed': False,
                'risk_pct': 0,
                'action': 'REJECT',
                'reason': 'Hourly drawdown limit reached'
            }

        # Calculate allowed risk for this signal
        risk_calc = self.calculate_allowed_risk(signal)
        if not risk_calc['allowed']:
            # Check if we can replace existing trades
            replacement = self.evaluate_trade_replacement(signal)
            if replacement['should_replace']:
                return {
                    'allowed': True,
                    'risk_pct': risk_calc.get('risk_pct', 1.0),
                    'action': 'REPLACE',
                    'trades_to_close': replacement['trades_to_close'],
                    'reason': replacement['reason']
                }
            return {
                'allowed': False,
                'risk_pct': 0,
                'action': 'REJECT',
                'reason': risk_calc['reason']
            }

        return {
            'allowed': True,
            'risk_pct': risk_calc['risk_pct'],
            'action': 'OPEN',
            'reason': risk_calc['reason']
        }

    def _check_hourly_drawdown(self) -> bool:
        """Check if hourly drawdown limit is breached"""
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        start_key = f"{hour_key}_start"

        if start_key not in self.hourly_pnl:
            self.hourly_pnl[start_key] = self.current_balance

        start_balance = self.hourly_pnl[start_key]
        if start_balance == 0:
            return False

        hourly_dd = ((start_balance - self.current_balance) / start_balance) * 100

        if hourly_dd >= self.max_hourly_drawdown_pct:
            self.halt_trading(f"Hourly drawdown {hourly_dd:.2f}% exceeded {self.max_hourly_drawdown_pct}%")
            return True

        return False

    def halt_trading(self, reason: str):
        """Halt all trading"""
        self.trading_halted = True
        self.halt_reason = reason

        mq.set('trading_halted', {'halted': True, 'reason': reason}, ttl=3600)

        for bot in ['scalper', 'day_trader', 'swing', 'position', 'sniper']:
            mq.publish(f'commands:{bot}', {'command': 'HALT', 'reason': reason})

        logger.critical(f"TRADING HALTED: {reason}")
        notify.send(f"🛑 <b>TRADING HALTED</b>\n\n{reason}")

    def resume_trading(self):
        """Resume trading"""
        self.trading_halted = False
        self.halt_reason = ""

        mq.set('trading_halted', {'halted': False, 'reason': ''}, ttl=3600)

        for bot in ['scalper', 'day_trader', 'swing', 'position', 'sniper']:
            mq.publish(f'commands:{bot}', {'command': 'RESUME'})

        logger.info("Trading resumed")
        notify.send("✅ <b>Trading Resumed</b>")

    # ============= EOD Protection =============

    def check_eod_protection(self):
        """End of day - ensure no red day"""
        now = datetime.now()

        if now.hour == self.eod_close_hour and now.minute >= self.eod_close_minute:
            daily_pnl = self._get_daily_pnl()

            if daily_pnl < 0:
                logger.warning(f"EOD: Daily P&L ${daily_pnl:.2f}, closing losing positions")
                self._close_worst_positions(target_pnl=0)

    def _get_daily_pnl(self) -> float:
        """Get today's P&L"""
        day_key = datetime.now().strftime("%Y-%m-%d")
        start_balance = mq.get(f"daily_start_{day_key}")

        if not start_balance:
            mq.set(f"daily_start_{day_key}", {'balance': self.current_balance}, ttl=86400)
            return 0

        if isinstance(start_balance, dict):
            start_balance = start_balance.get('balance', self.current_balance)

        return self.current_balance - float(start_balance)

    def _close_worst_positions(self, target_pnl: float = 0):
        """Close worst performing positions until target P&L is reached"""
        if not self.open_positions:
            return

        # Sort by recovery score (lowest first = worst)
        sorted_positions = sorted(
            self.open_positions.values(),
            key=lambda p: p.overall_score
        )

        positions_closed = 0
        for pos in sorted_positions:
            if self._get_daily_pnl() >= target_pnl:
                break

            if pos.current_pnl < 0:
                if self.api.close_position(pos.trade_id):
                    positions_closed += 1
                    logger.info(f"EOD: Closed {pos.symbol} ({pos.current_r:.1f}R)")

        if positions_closed > 0:
            notify.send(f"🌙 <b>EOD Protection</b>\n\nClosed {positions_closed} position(s)")

    # ============= Status Publishing =============

    def publish_status(self):
        """Publish current risk status"""
        status = {
            'trading_halted': self.trading_halted,
            'halt_reason': self.halt_reason,
            'current_balance': self.current_balance,
            'high_water_mark': self.high_water_mark,
            'drawdown_from_hwm': ((self.high_water_mark - self.current_balance) / self.high_water_mark * 100) if self.high_water_mark > 0 else 0,
            'daily_margin_used_pct': self.daily_margin_used,
            'daily_margin_limit_pct': self.max_daily_margin_pct,
            'daily_pnl': self._get_daily_pnl(),
            'open_positions': len(self.open_positions),
            'timestamp': datetime.now().isoformat()
        }

        mq.set('risk_status', status, ttl=120)
        mq.publish('risk:status', status)

    # ============= Main Loop =============

    def run(self):
        """Main monitoring loop"""
        logger.info("Smart Risk Manager starting...")
        logger.info(f"Config: Max daily margin={self.max_daily_margin_pct}%, "
                   f"Max hourly DD={self.max_hourly_drawdown_pct}%")

        notify.send(
            f"🧠 <b>Smart Risk Manager Active</b>\n\n"
            f"Max Daily Margin: {self.max_daily_margin_pct}%\n"
            f"Max Hourly DD: {self.max_hourly_drawdown_pct}%\n"
            f"EOD Protection: {self.eod_close_hour}:{self.eod_close_minute}\n"
            f"Balance: ${self.current_balance:.2f}"
        )

        while True:
            try:
                # Update balance
                account = self.api.get_account_info()
                if account:
                    self.current_balance = float(account.get('balance', self.current_balance))

                    if self.current_balance > self.high_water_mark:
                        self.high_water_mark = self.current_balance
                        self._save_high_water_mark(self.high_water_mark)

                # Update positions
                self.update_positions()

                # Check hourly drawdown
                self._check_hourly_drawdown()

                # Check EOD protection
                self.check_eod_protection()

                # Auto-resume at new hour
                if self.trading_halted and 'Hourly' in self.halt_reason:
                    current_hour = datetime.now().strftime("%Y-%m-%d-%H")
                    last_hour = list(self.hourly_pnl.keys())[-1] if self.hourly_pnl else ""
                    if current_hour not in last_hour:
                        self.resume_trading()

                # Publish status
                self.publish_status()

                # Heartbeat
                mq.send_heartbeat('smart-risk-manager')

                time.sleep(30)

            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(10)


if __name__ == '__main__':
    manager = SmartRiskManager()
    manager.run()
