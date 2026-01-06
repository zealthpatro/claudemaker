"""
Base Trading Bot
Abstract base class for all trading bot implementations
"""

import abc
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

import sys
sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.capital_api import api
from services.shared.notifications import notifier

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Active position data"""
    trade_id: int
    deal_id: str
    signal_id: int
    symbol: str
    symbol_id: int
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    risk_amount: float
    opened_at: datetime
    current_price: float = 0
    current_pnl: float = 0
    current_r: float = 0
    trailing_stop: float = None
    metadata: Dict = field(default_factory=dict)


class BaseTradingBot(abc.ABC):
    """Base class for all trading bots"""

    def __init__(self, bot_type: str):
        self.bot_type = bot_type
        self.bot_config = config.get_bot_config(bot_type)
        self.risk_config = config.risk_management
        self.account_config = config.accounts.get(self.bot_config.get('account', 'swing'))

        self.running = False
        self.paused = False
        self.positions: Dict[str, Position] = {}  # deal_id -> Position
        self.daily_pnl = 0
        self.daily_trades = 0
        self.consecutive_losses = 0

        # Cooldown tracking
        self.last_trade_time: Dict[str, datetime] = {}  # symbol -> last trade time
        self.cooldown_minutes = self.bot_config.get('cooldown_minutes', 30)

        logger.info(f"Initialized {bot_type} bot")

    @abc.abstractmethod
    def on_signal(self, signal: Dict):
        """Handle incoming signal - implemented by subclasses"""
        pass

    @abc.abstractmethod
    def manage_position(self, position: Position, current_price: float):
        """Manage active position - implemented by subclasses"""
        pass

    def start(self):
        """Start the bot"""
        logger.info(f"Starting {self.bot_type} bot...")

        # Authenticate with broker
        if not api.authenticate():
            raise Exception("Failed to authenticate with broker")

        # Subscribe to command channel
        channel = f'commands:{self.bot_type}'
        mq.subscribe(channel, self._on_message)

        # Load existing positions
        self._load_open_positions()

        self.running = True

        # Start position management thread
        self._start_position_manager()

        logger.info(f"{self.bot_type} bot started")

    def stop(self):
        """Stop the bot"""
        logger.info(f"Stopping {self.bot_type} bot...")
        self.running = False

    def pause(self):
        """Pause trading (stop new trades but manage existing)"""
        logger.info(f"Pausing {self.bot_type} bot")
        self.paused = True

    def resume(self):
        """Resume trading"""
        logger.info(f"Resuming {self.bot_type} bot")
        self.paused = False

    def _on_message(self, channel: str, data: Dict):
        """Handle incoming messages"""
        msg_type = data.get('type', 'signal')

        if msg_type == 'command':
            self._handle_command(data)
        else:
            self.on_signal(data)

    def _handle_command(self, cmd: Dict):
        """Handle control commands"""
        action = cmd.get('action')

        if action == 'pause':
            self.pause()
        elif action == 'resume':
            self.resume()
        elif action == 'close_all':
            self.close_all_positions("Manual close all")
        elif action == 'status':
            self._report_status()

    def _load_open_positions(self):
        """Load open positions from database"""
        trades = db.get_open_trades(bot_type=self.bot_type)

        for trade in trades:
            position = Position(
                trade_id=trade['id'],
                deal_id=trade.get('metadata', {}).get('deal_id', ''),
                signal_id=trade['signal_id'],
                symbol=self._get_symbol_name(trade['symbol_id']),
                symbol_id=trade['symbol_id'],
                direction=trade['direction'],
                entry_price=float(trade['entry_price']),
                stop_loss=float(trade['stop_loss']),
                take_profit=float(trade['take_profit']),
                position_size=float(trade['position_size']),
                risk_amount=float(trade['risk_amount']),
                opened_at=trade['opened_at']
            )
            self.positions[position.deal_id] = position

        logger.info(f"Loaded {len(self.positions)} open positions")

    def _start_position_manager(self):
        """Start background position management thread"""
        def manager():
            while self.running:
                try:
                    self._update_positions()
                    time.sleep(10)  # Check every 10 seconds
                except Exception as e:
                    logger.error(f"Position manager error: {e}")
                    time.sleep(30)

        thread = threading.Thread(target=manager, daemon=True)
        thread.start()

    def _update_positions(self):
        """Update and manage all positions"""
        if not self.positions:
            return

        for deal_id, position in list(self.positions.items()):
            try:
                # Get current price
                current_price = mq.get_cached_price(position.symbol)
                if not current_price:
                    current_price = self._fetch_current_price(position.symbol)

                if current_price:
                    # Update position P/L
                    position.current_price = current_price
                    position.current_pnl = self._calculate_pnl(position, current_price)
                    position.current_r = self._calculate_r(position, current_price)

                    # Let subclass manage the position
                    self.manage_position(position, current_price)

            except Exception as e:
                logger.error(f"Error updating position {deal_id}: {e}")

    def _calculate_pnl(self, position: Position, current_price: float) -> float:
        """Calculate current P/L"""
        if position.direction == 'BUY':
            return (current_price - position.entry_price) * position.position_size
        else:
            return (position.entry_price - current_price) * position.position_size

    def _calculate_r(self, position: Position, current_price: float) -> float:
        """Calculate P/L in R units"""
        risk_per_unit = abs(position.entry_price - position.stop_loss)
        if risk_per_unit == 0:
            return 0

        if position.direction == 'BUY':
            movement = current_price - position.entry_price
        else:
            movement = position.entry_price - current_price

        return movement / risk_per_unit

    # ============= Trading Methods =============

    def can_trade(self, symbol: str) -> Tuple[bool, str]:
        """Check if bot can take a new trade"""
        if self.paused:
            return False, "Bot is paused"

        # CHECK RISK MANAGER FIRST - Global halt check
        try:
            halt_status = mq.get('trading_halted')
            if halt_status and halt_status.get('halted', False):
                return False, f"Trading halted: {halt_status.get('reason', 'Risk limit')}"
        except:
            pass

        # Check max concurrent positions
        max_concurrent = self.bot_config.get('max_concurrent', 4)
        if len(self.positions) >= max_concurrent:
            return False, f"Max positions reached ({max_concurrent})"

        # Check daily drawdown
        account_balance = self._get_account_balance()
        if account_balance > 0:
            daily_dd = abs(min(0, self.daily_pnl)) / account_balance
            max_dd = self.risk_config.get('max_daily_drawdown', 0.15)
            if daily_dd >= max_dd:
                return False, f"Daily drawdown limit reached ({daily_dd:.1%})"

        # Check consecutive losses
        max_losses = self.risk_config.get('pause_on_consecutive_losses', 5)
        if self.consecutive_losses >= max_losses:
            return False, f"Consecutive losses limit reached ({self.consecutive_losses})"

        # Check cooldown
        last_trade = self.last_trade_time.get(symbol)
        if last_trade:
            cooldown = timedelta(minutes=self.cooldown_minutes)
            if datetime.now() - last_trade < cooldown:
                return False, "Symbol on cooldown"

        # Check total exposure
        total_risk = sum(p.risk_amount for p in self.positions.values())
        max_exposure = self.risk_config.get('max_total_exposure', 0.20)
        if account_balance > 0 and total_risk / account_balance >= max_exposure:
            return False, "Max exposure reached"

        return True, "OK"

    def calculate_position_size(self, symbol: str, entry: float,
                                stop_loss: float, risk_override: float = None) -> float:
        """Calculate position size based on risk - USES COMPOUNDING via High Water Mark"""
        # Get risk status from risk manager for compounding
        try:
            risk_status = mq.get('risk_status')
            if risk_status:
                high_water_mark = risk_status.get('high_water_mark', 0)
                current_balance = risk_status.get('current_balance', 0)
                drawdown_from_hwm = risk_status.get('drawdown_from_hwm', 0)

                # Use HIGH WATER MARK for compounding (only compound profits)
                # But cap at current balance for safety
                effective_balance = min(high_water_mark, current_balance) if high_water_mark > 0 else current_balance

                # Reduce risk if in drawdown > 2%
                risk_pct = risk_override or self.bot_config.get('risk_pct', 0.02)
                if drawdown_from_hwm > 2:
                    risk_pct *= 0.5  # Cut risk in half when in drawdown
                    logger.info(f"Reduced risk to {risk_pct:.1%} due to {drawdown_from_hwm:.1f}% drawdown")
            else:
                effective_balance = self._get_account_balance()
                risk_pct = risk_override or self.bot_config.get('risk_pct', 0.02)
        except:
            effective_balance = self._get_account_balance()
            risk_pct = risk_override or self.bot_config.get('risk_pct', 0.02)

        risk_amount = effective_balance * risk_pct
        stop_distance = abs(entry - stop_loss)

        if stop_distance == 0:
            return 0

        position_size = risk_amount / stop_distance

        # Apply min/max lot constraints
        symbol_config = config.get_symbol_config(symbol)
        min_lot = symbol_config.get('min_lot', 0.01)
        max_lot = 100  # Safety limit

        position_size = max(min_lot, min(position_size, max_lot))

        return round(position_size, 2)

    def open_position(self, signal: Dict) -> Optional[Position]:
        """Open a new position"""
        symbol = signal.get('symbol')
        direction = signal.get('direction')
        entry_price = signal.get('entry_price')
        stop_loss = signal.get('stop_loss')
        take_profit = signal.get('take_profit')

        # Calculate position size
        position_size = self.calculate_position_size(symbol, entry_price, stop_loss)

        if position_size <= 0:
            logger.warning(f"Invalid position size for {symbol}")
            return None

        # Place order with broker
        epic = self._get_epic(symbol)
        success, result = api.place_order(
            epic=epic,
            direction=direction,
            size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if not success:
            logger.error(f"Failed to place order: {result}")
            return None

        deal_id = result.get('dealId', result.get('dealReference', ''))

        # Calculate risk amount
        risk_amount = abs(entry_price - stop_loss) * position_size

        # Create position record
        position = Position(
            trade_id=0,  # Will be set after DB insert
            deal_id=deal_id,
            signal_id=signal.get('signal_id', 0),
            symbol=symbol,
            symbol_id=signal.get('symbol_id', 0),
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            risk_amount=risk_amount,
            opened_at=datetime.now()
        )

        # Save to database
        trade_data = {
            'signal_id': position.signal_id,
            'account_id': self.account_config.get('id', ''),
            'bot_type': self.bot_type,
            'symbol_id': position.symbol_id,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_size': position_size,
            'risk_amount': risk_amount,
            'status': 'open',
            'metadata': {'deal_id': deal_id}
        }

        trade_id = db.insert_trade(trade_data)
        position.trade_id = trade_id

        # Track position
        self.positions[deal_id] = position
        self.last_trade_time[symbol] = datetime.now()
        self.daily_trades += 1

        # Update signal status
        db.update_signal_status(signal.get('signal_id', 0), 'executed')

        # Send notification
        notifier.send_trade_opened(
            symbol=symbol,
            direction=direction,
            entry=entry_price,
            size=position_size,
            stop=stop_loss,
            target=take_profit,
            bot_type=self.bot_type,
            account=self.account_config.get('name', '')
        )

        logger.info(f"Opened {direction} position for {symbol} @ {entry_price}")
        return position

    def close_position(self, position: Position, reason: str,
                       exit_price: float = None) -> bool:
        """Close a position"""
        try:
            # Close with broker
            success, result = api.close_position(position.deal_id)

            if not success:
                logger.error(f"Failed to close position: {result}")
                return False

            # Calculate final P/L
            if exit_price is None:
                exit_price = position.current_price

            pnl = self._calculate_pnl(position, exit_price)
            pnl_r = self._calculate_r(position, exit_price)

            # Update database
            db.close_trade(
                trade_id=position.trade_id,
                exit_price=exit_price,
                pnl=pnl,
                pnl_r=pnl_r,
                close_reason=reason
            )

            # Update daily stats
            self.daily_pnl += pnl
            if pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

            # Remove from tracking
            del self.positions[position.deal_id]

            # Send notification
            notifier.send_trade_closed(
                symbol=position.symbol,
                direction=position.direction,
                entry=position.entry_price,
                exit_price=exit_price,
                pnl=pnl,
                pnl_r=pnl_r,
                reason=reason,
                bot_type=self.bot_type
            )

            logger.info(f"Closed {position.symbol} position: {pnl_r:.1f}R ({reason})")
            return True

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    def close_all_positions(self, reason: str):
        """Close all open positions"""
        for deal_id, position in list(self.positions.items()):
            self.close_position(position, reason)

    def update_stop_loss(self, position: Position, new_stop: float) -> bool:
        """Update position stop loss (trailing stop)"""
        try:
            success, result = api.modify_position(
                deal_id=position.deal_id,
                stop_loss=new_stop
            )

            if success:
                position.stop_loss = new_stop
                position.trailing_stop = new_stop
                logger.info(f"Updated stop loss for {position.symbol} to {new_stop}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating stop loss: {e}")
            return False

    # ============= Helper Methods =============

    def _get_account_balance(self) -> float:
        """Get current account balance"""
        account_id = self.account_config.get('id', '')
        balance = api.get_account_balance(account_id)
        return balance.get('balance', 0) if balance else 0

    def _get_symbol_name(self, symbol_id: int) -> str:
        """Get symbol name from ID"""
        result = db.fetch_one("SELECT name FROM symbols WHERE id = %s", (symbol_id,))
        return result['name'] if result else 'UNKNOWN'

    def _get_epic(self, symbol: str) -> str:
        """Get Capital.com epic for symbol"""
        epic_map = {'XAUUSD': 'GOLD', 'XAGUSD': 'SILVER'}
        return epic_map.get(symbol, symbol)

    def _fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current price from API"""
        epic = self._get_epic(symbol)
        price_data = api.get_current_price(epic)
        if price_data:
            return (price_data['bid'] + price_data['ask']) / 2
        return None

    def _report_status(self):
        """Report bot status"""
        status = {
            'bot_type': self.bot_type,
            'running': self.running,
            'paused': self.paused,
            'open_positions': len(self.positions),
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'consecutive_losses': self.consecutive_losses,
            'timestamp': datetime.now().isoformat()
        }
        mq.publish('status:bots', status)

    def _send_heartbeat(self):
        """Send heartbeat"""
        mq.send_heartbeat(f'bot_{self.bot_type}', 'running', {
            'positions': len(self.positions),
            'daily_pnl': self.daily_pnl,
            'paused': self.paused
        })
        db.update_service_state(f'bot_{self.bot_type}', 'running')
