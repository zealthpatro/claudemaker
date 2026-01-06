#!/usr/bin/env python3
"""
Risk Manager - Central risk control for all trading bots
- Max 3% drawdown per hour across all bots
- No day ends with a loss (EOD protection)
- Compounding only (position sizing based on high-water mark)
"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
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
        logging.FileHandler('/home/trader/algo_trading/logs/risk_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('risk-manager')


class RiskManager:
    """Central risk management for the trading system"""

    def __init__(self):
        self.api = CapitalAPI()

        # Risk parameters
        self.max_hourly_drawdown_pct = 3.0  # Max 3% loss in any hour
        self.max_daily_drawdown_pct = 5.0   # Max 5% loss per day (safety net)
        self.eod_close_hour = 20            # Close losing trades at 8 PM
        self.eod_close_minute = 30          # 8:30 PM
        self.min_profit_to_keep = 0.0       # Minimum profit to keep position open at EOD

        # State tracking
        self.hourly_pnl: Dict[str, float] = defaultdict(float)  # hour_key -> pnl
        self.daily_pnl: float = 0.0
        self.high_water_mark: float = 0.0
        self.starting_balance: float = 0.0
        self.current_balance: float = 0.0
        self.trading_halted: bool = False
        self.halt_reason: str = ""
        self.last_hour_check: str = ""
        self.last_day_check: str = ""

        # Initialize
        self._init_state()

    def _init_state(self):
        """Initialize state from database and API"""
        try:
            account = self.api.get_account_info()
            if account:
                self.current_balance = float(account.get('balance', 10000))
                self.starting_balance = self.current_balance
                self.high_water_mark = self._get_high_water_mark()
                logger.info(f"Initialized: Balance=${self.current_balance:.2f}, HWM=${self.high_water_mark:.2f}")
            else:
                logger.warning("Could not get account info, using defaults")
                self.current_balance = 10000
                self.starting_balance = 10000
                self.high_water_mark = 10000
        except Exception as e:
            logger.error(f"Init error: {e}")
            self.current_balance = 10000
            self.high_water_mark = 10000

    def _get_high_water_mark(self) -> float:
        """Get high water mark from database or current balance"""
        try:
            result = db.fetch_one(
                "SELECT value FROM system_state WHERE service_name = 'high_water_mark'"
            )
            if result:
                return float(result.get('value', self.current_balance))
        except:
            pass
        return self.current_balance

    def _save_high_water_mark(self, hwm: float):
        """Save high water mark to database"""
        try:
            db.execute("""
                INSERT INTO system_state (service_name, status, config)
                VALUES ('high_water_mark', 'active', %s::jsonb)
                ON CONFLICT (service_name) DO UPDATE
                SET config = %s::jsonb, updated_at = NOW()
            """, (f'{{"value": {hwm}}}', f'{{"value": {hwm}}}'))
        except Exception as e:
            logger.error(f"Failed to save HWM: {e}")

    def _get_hour_key(self) -> str:
        """Get current hour key for tracking"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d-%H")

    def _get_day_key(self) -> str:
        """Get current day key for tracking"""
        return datetime.now().strftime("%Y-%m-%d")

    def update_balance(self) -> float:
        """Update current balance from API"""
        try:
            account = self.api.get_account_info()
            if account:
                self.current_balance = float(account.get('balance', self.current_balance))

                # Update high water mark if we have new highs
                if self.current_balance > self.high_water_mark:
                    self.high_water_mark = self.current_balance
                    self._save_high_water_mark(self.high_water_mark)
                    logger.info(f"New high water mark: ${self.high_water_mark:.2f}")

                return self.current_balance
        except Exception as e:
            logger.error(f"Balance update error: {e}")
        return self.current_balance

    def calculate_hourly_drawdown(self) -> float:
        """Calculate drawdown for current hour"""
        hour_key = self._get_hour_key()

        # Reset if new hour
        if hour_key != self.last_hour_check:
            self.hourly_pnl[hour_key] = 0
            self.last_hour_check = hour_key
            # Store starting balance for this hour
            self.hourly_pnl[f"{hour_key}_start"] = self.current_balance

        start_balance = self.hourly_pnl.get(f"{hour_key}_start", self.current_balance)
        if start_balance == 0:
            return 0

        hourly_change = self.current_balance - start_balance
        hourly_drawdown_pct = (hourly_change / start_balance) * 100

        return hourly_drawdown_pct

    def calculate_daily_pnl(self) -> float:
        """Calculate P&L for current day"""
        day_key = self._get_day_key()

        # Reset if new day
        if day_key != self.last_day_check:
            self.daily_pnl = 0
            self.last_day_check = day_key
            # Store starting balance for this day
            mq.set(f"daily_start_{day_key}", self.current_balance, ttl=86400)

        start_balance = mq.get(f"daily_start_{day_key}", self.current_balance)
        if isinstance(start_balance, dict):
            start_balance = start_balance.get('price', self.current_balance)

        return self.current_balance - float(start_balance)

    def check_hourly_drawdown(self) -> bool:
        """Check if hourly drawdown limit is breached"""
        drawdown = self.calculate_hourly_drawdown()

        if drawdown <= -self.max_hourly_drawdown_pct:
            self.halt_trading(f"Hourly drawdown limit breached: {drawdown:.2f}%")
            return True

        # Warning at 2%
        if drawdown <= -2.0:
            logger.warning(f"Hourly drawdown warning: {drawdown:.2f}%")
            notify.send(f"⚠️ <b>Drawdown Warning</b>\n\nHourly: {drawdown:.2f}%\nLimit: {self.max_hourly_drawdown_pct}%")

        return False

    def halt_trading(self, reason: str):
        """Halt all trading activity"""
        self.trading_halted = True
        self.halt_reason = reason

        # Publish halt command to all bots
        halt_msg = {
            'command': 'HALT',
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }

        for bot in ['scalper', 'day_trader', 'swing', 'position', 'sniper']:
            mq.publish(f'commands:{bot}', halt_msg)

        # Set global halt flag
        mq.set('trading_halted', {'halted': True, 'reason': reason}, ttl=3600)

        logger.critical(f"TRADING HALTED: {reason}")
        notify.send(f"🛑 <b>TRADING HALTED</b>\n\n{reason}\n\nAll bots stopped.")

    def resume_trading(self):
        """Resume trading after halt"""
        self.trading_halted = False
        self.halt_reason = ""

        resume_msg = {
            'command': 'RESUME',
            'timestamp': datetime.now().isoformat()
        }

        for bot in ['scalper', 'day_trader', 'swing', 'position', 'sniper']:
            mq.publish(f'commands:{bot}', resume_msg)

        mq.set('trading_halted', {'halted': False, 'reason': ''}, ttl=3600)

        logger.info("Trading resumed")
        notify.send("✅ <b>Trading Resumed</b>\n\nAll bots active.")

    def check_eod_protection(self):
        """End of day protection - close losing positions to ensure no red days"""
        now = datetime.now()

        # Check if it's EOD time
        if now.hour == self.eod_close_hour and now.minute >= self.eod_close_minute:
            daily_pnl = self.calculate_daily_pnl()

            if daily_pnl < self.min_profit_to_keep:
                logger.warning(f"EOD Protection: Daily P&L is ${daily_pnl:.2f}, closing losing positions")
                self._close_losing_positions()

    def _close_losing_positions(self):
        """Close all losing positions"""
        try:
            positions = self.api.get_positions()
            closed_count = 0

            for pos in positions:
                pnl = float(pos.get('position', {}).get('unrealisedPnL', 0))
                deal_id = pos.get('position', {}).get('dealId')

                if pnl < 0 and deal_id:
                    if self.api.close_position(deal_id):
                        closed_count += 1
                        logger.info(f"EOD: Closed losing position {deal_id}, P&L: ${pnl:.2f}")

            if closed_count > 0:
                notify.send(f"🌙 <b>EOD Protection</b>\n\nClosed {closed_count} losing position(s) to protect daily P&L")

        except Exception as e:
            logger.error(f"Error closing positions: {e}")

    def get_allowed_position_size(self, base_risk_pct: float, entry: float, stop_loss: float) -> float:
        """
        Calculate position size based on compounding (high water mark)
        Only compounds on profits, not losses
        """
        # Use high water mark for compounding, but cap at current balance
        effective_balance = min(self.high_water_mark, self.current_balance)

        # If we're in drawdown, reduce risk
        drawdown_from_hwm = (self.high_water_mark - self.current_balance) / self.high_water_mark * 100

        if drawdown_from_hwm > 2:
            # Reduce risk by 50% when in drawdown > 2%
            base_risk_pct *= 0.5
            logger.info(f"Reduced risk due to {drawdown_from_hwm:.1f}% drawdown from HWM")

        risk_amount = effective_balance * (base_risk_pct / 100)
        risk_per_unit = abs(entry - stop_loss)

        if risk_per_unit == 0:
            return 0.01

        size = risk_amount / risk_per_unit
        return max(0.01, min(size, 10.0))  # Cap between 0.01 and 10 lots

    def get_risk_status(self) -> Dict:
        """Get current risk status"""
        hourly_dd = self.calculate_hourly_drawdown()
        daily_pnl = self.calculate_daily_pnl()

        return {
            'trading_halted': self.trading_halted,
            'halt_reason': self.halt_reason,
            'current_balance': self.current_balance,
            'high_water_mark': self.high_water_mark,
            'drawdown_from_hwm': (self.high_water_mark - self.current_balance) / self.high_water_mark * 100 if self.high_water_mark > 0 else 0,
            'hourly_drawdown_pct': hourly_dd,
            'hourly_limit_pct': self.max_hourly_drawdown_pct,
            'daily_pnl': daily_pnl,
            'timestamp': datetime.now().isoformat()
        }

    def run(self):
        """Main risk monitoring loop"""
        logger.info("Risk Manager starting...")
        logger.info(f"Config: Max hourly DD={self.max_hourly_drawdown_pct}%, EOD={self.eod_close_hour}:{self.eod_close_minute}")

        notify.send(f"🛡️ <b>Risk Manager Active</b>\n\n"
                   f"Max Hourly DD: {self.max_hourly_drawdown_pct}%\n"
                   f"EOD Protection: {self.eod_close_hour}:{self.eod_close_minute}\n"
                   f"Balance: ${self.current_balance:.2f}\n"
                   f"HWM: ${self.high_water_mark:.2f}")

        check_interval = 30  # Check every 30 seconds

        while True:
            try:
                # Update balance
                self.update_balance()

                # Check hourly drawdown
                if not self.trading_halted:
                    self.check_hourly_drawdown()

                # Check EOD protection
                self.check_eod_protection()

                # Publish risk status
                status = self.get_risk_status()
                mq.publish('risk:status', status)
                mq.set('risk_status', status, ttl=120)

                # Auto-resume at new hour if halted due to hourly drawdown
                if self.trading_halted and 'Hourly' in self.halt_reason:
                    current_hour = self._get_hour_key()
                    if current_hour != self.last_hour_check:
                        logger.info("New hour started, checking if safe to resume...")
                        self.resume_trading()

                # Heartbeat
                mq.send_heartbeat('risk-manager', 'running' if not self.trading_halted else 'halted')

                # Log status periodically
                if datetime.now().minute % 5 == 0 and datetime.now().second < 30:
                    logger.info(f"Status: Balance=${self.current_balance:.2f}, "
                              f"HWM=${self.high_water_mark:.2f}, "
                              f"Hourly DD={self.calculate_hourly_drawdown():.2f}%, "
                              f"Daily P&L=${self.calculate_daily_pnl():.2f}")

                time.sleep(check_interval)

            except Exception as e:
                logger.error(f"Risk check error: {e}")
                time.sleep(10)


if __name__ == '__main__':
    manager = RiskManager()
    manager.run()
