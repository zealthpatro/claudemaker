"""
Notification Service
Telegram notifications and alerts
"""

import requests
from typing import List, Optional
from datetime import datetime
import logging

from .config import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram"""

    MAX_MESSAGE_LENGTH = 4000

    def __init__(self):
        tg_config = config.telegram
        self.token = tg_config.get('token', '')
        self.chat_id = tg_config.get('chat_id', '')
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = 'HTML',
                     disable_notification: bool = False) -> bool:
        """Send message to Telegram"""
        if not self.enabled:
            logger.warning("Telegram not configured, skipping notification")
            return False

        # Split long messages
        messages = self._split_message(text)

        success = True
        for msg in messages:
            try:
                response = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        'chat_id': self.chat_id,
                        'text': msg,
                        'parse_mode': parse_mode,
                        'disable_notification': disable_notification
                    },
                    timeout=10
                )
                if response.status_code != 200:
                    logger.error(f"Telegram error: {response.text}")
                    success = False
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
                success = False

        return success

    def _split_message(self, text: str) -> List[str]:
        """Split message if too long"""
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return [text]

        messages = []
        lines = text.split('\n')
        current = ""

        for line in lines:
            if len(current) + len(line) + 1 > self.MAX_MESSAGE_LENGTH:
                if current:
                    messages.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line

        if current:
            messages.append(current)

        return messages

    # ============= Alert Types =============

    def send_signal_alert(self, symbol: str, direction: str, setup: str,
                          confidence: float, tier: str, entry: float,
                          stop: float, target: float) -> bool:
        """Send new signal alert"""
        emoji = "🟢" if direction == "BUY" else "🔴"
        rr = abs(target - entry) / abs(entry - stop) if abs(entry - stop) > 0 else 0

        text = f"""
{emoji} <b>NEW SIGNAL</b> {emoji}

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Setup:</b> {setup}
<b>Tier:</b> {tier}
<b>Confidence:</b> {confidence:.1%}

<b>Entry:</b> {entry:.2f}
<b>Stop Loss:</b> {stop:.2f}
<b>Take Profit:</b> {target:.2f}
<b>R:R:</b> 1:{rr:.1f}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_trade_opened(self, symbol: str, direction: str, entry: float,
                          size: float, stop: float, target: float,
                          bot_type: str, account: str) -> bool:
        """Send trade opened notification"""
        emoji = "📈" if direction == "BUY" else "📉"

        text = f"""
{emoji} <b>TRADE OPENED</b>

<b>Bot:</b> {bot_type.upper()}
<b>Account:</b> {account}
<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Size:</b> {size}

<b>Entry:</b> {entry:.2f}
<b>Stop:</b> {stop:.2f}
<b>Target:</b> {target:.2f}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_trade_closed(self, symbol: str, direction: str, entry: float,
                          exit_price: float, pnl: float, pnl_r: float,
                          reason: str, bot_type: str) -> bool:
        """Send trade closed notification"""
        emoji = "✅" if pnl > 0 else "❌"
        pnl_sign = "+" if pnl > 0 else ""

        text = f"""
{emoji} <b>TRADE CLOSED</b>

<b>Bot:</b> {bot_type.upper()}
<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Reason:</b> {reason}

<b>Entry:</b> {entry:.2f}
<b>Exit:</b> {exit_price:.2f}
<b>P/L:</b> {pnl_sign}${pnl:.2f} ({pnl_sign}{pnl_r:.1f}R)

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_daily_summary(self, trades: int, wins: int, losses: int,
                           pnl: float, pnl_r: float, win_rate: float) -> bool:
        """Send daily trading summary"""
        emoji = "📊"
        pnl_sign = "+" if pnl > 0 else ""

        text = f"""
{emoji} <b>DAILY SUMMARY</b> {emoji}

<b>Total Trades:</b> {trades}
<b>Wins:</b> {wins} | <b>Losses:</b> {losses}
<b>Win Rate:</b> {win_rate:.1%}

<b>Daily P/L:</b> {pnl_sign}${pnl:.2f}
<b>Daily R:</b> {pnl_sign}{pnl_r:.1f}R

<i>{datetime.now().strftime('%Y-%m-%d')} Report</i>
"""
        return self.send_message(text.strip())

    def send_drawdown_alert(self, current_dd: float, limit: float,
                            period: str = 'daily') -> bool:
        """Send drawdown warning"""
        text = f"""
⚠️ <b>DRAWDOWN ALERT</b> ⚠️

<b>{period.upper()} Drawdown:</b> {current_dd:.1%}
<b>Limit:</b> {limit:.1%}

{"🛑 <b>TRADING PAUSED</b>" if current_dd >= limit else "⚡ Approaching limit, reducing risk"}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_system_alert(self, level: str, message: str,
                          service: str = None) -> bool:
        """Send system alert"""
        level_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '🚨',
            'critical': '🆘'
        }
        emoji = level_emoji.get(level.lower(), 'ℹ️')

        text = f"""
{emoji} <b>SYSTEM {level.upper()}</b>

{f"<b>Service:</b> {service}" if service else ""}
<b>Message:</b> {message}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_ml_update(self, model: str, version: str, accuracy: float,
                       improvement: float, promoted: bool) -> bool:
        """Send ML model update notification"""
        emoji = "🤖"

        text = f"""
{emoji} <b>ML MODEL UPDATE</b>

<b>Model:</b> {model}
<b>Version:</b> {version}
<b>Accuracy:</b> {accuracy:.1%}
<b>Improvement:</b> {improvement:+.1%}

<b>Status:</b> {'✅ PROMOTED TO PRODUCTION' if promoted else '⏳ Testing continues'}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>
"""
        return self.send_message(text.strip())

    def send_heartbeat(self, services: dict) -> bool:
        """Send system health heartbeat"""
        status_emoji = {
            'running': '🟢',
            'paused': '🟡',
            'stopped': '🔴',
            'error': '🔴'
        }

        lines = ["💓 <b>SYSTEM HEARTBEAT</b>\n"]
        for service, status in services.items():
            emoji = status_emoji.get(status, '⚪')
            lines.append(f"{emoji} {service}: {status}")

        lines.append(f"\n<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>")

        return self.send_message('\n'.join(lines), disable_notification=True)


# Global notifier instance
notifier = TelegramNotifier()
