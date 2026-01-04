#!/usr/bin/env python3
"""
Telegram Command Handler for Trading Bot
Allows remote control via Telegram messages.
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Optional
import requests
import psutil

# Configuration
CONFIG_FILE = "/home/trader/supervisor_config.json"
BOT_DIR = "/home/trader"
LOG_FILE = "/home/trader/telegram_commander.log"

# Telegram config
TELEGRAM_TOKEN = "8376345331:AAHWoZzkqT26cyeRPGa8MfcaVZWvTcan9lU"
CHAT_ID = "7831118282"
ALLOWED_CHAT_IDS = [7831118282]  # Only allow commands from this chat

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for receiving commands"""

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        self.running = False
        self.commands = {
            '/start': self.cmd_help,
            '/help': self.cmd_help,
            '/status': self.cmd_status,
            '/balance': self.cmd_balance,
            '/positions': self.cmd_positions,
            '/pause': self.cmd_pause,
            '/resume': self.cmd_resume,
            '/restart': self.cmd_restart,
            '/stop': self.cmd_stop,
            '/report': self.cmd_report,
            '/drawdown': self.cmd_drawdown,
            '/config': self.cmd_config,
            '/logs': self.cmd_logs,
            '/health': self.cmd_health,
            '/disk': self.cmd_disk,
        }

    def send_message(self, text: str, chat_id: int = None, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram"""
        if chat_id is None:
            chat_id = CHAT_ID

        try:
            url = f"{self.base_url}/sendMessage"
            # Split long messages
            if len(text) > 4000:
                chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for chunk in chunks:
                    payload = {
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode
                    }
                    requests.post(url, json=payload, timeout=10)
                return True

            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Send message failed: {e}")
            return False

    def get_updates(self) -> list:
        """Get new messages from Telegram"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 30
            }
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                return response.json().get("result", [])
            return []
        except Exception as e:
            logger.error(f"Get updates failed: {e}")
            return []

    def load_config(self) -> dict:
        """Load supervisor config"""
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    def save_config(self, config: dict):
        """Save supervisor config"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Save config failed: {e}")

    def get_capital_session(self) -> tuple:
        """Get Capital.com API session"""
        config = self.load_config()
        api_config = config.get("capital_api", {})

        try:
            url = f"{api_config['base_url']}/api/v1/session"
            headers = {
                "X-CAP-API-KEY": api_config['api_key'],
                "Content-Type": "application/json"
            }
            payload = {
                "identifier": api_config['identifier'],
                "password": api_config['password']
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                cst = response.headers.get("CST")
                security_token = response.headers.get("X-SECURITY-TOKEN")
                return (cst, security_token, api_config)
            return (None, None, None)
        except Exception as e:
            logger.error(f"Capital.com auth failed: {e}")
            return (None, None, None)

    # ==================== COMMAND HANDLERS ====================

    def cmd_help(self, chat_id: int, args: list) -> str:
        """Show available commands"""
        return """
<b>🤖 Trading Bot Commands</b>

<b>Status & Info:</b>
/status - Bot status overview
/balance - Account balances
/positions - Open positions
/drawdown - Drawdown levels
/health - System health
/disk - Disk usage

<b>Control:</b>
/pause - Pause all trading
/resume - Resume trading
/restart [bot1|bot2|all] - Restart bots
/stop [bot1|bot2|all] - Stop bots

<b>Reports:</b>
/report [daily|weekly] - Performance report
/logs [bot1|bot2] - Recent log entries

<b>Config:</b>
/config - View current config
/config set <key> <value> - Update config
"""

    def cmd_status(self, chat_id: int, args: list) -> str:
        """Get overall status"""
        status_lines = ["<b>📊 System Status</b>\n"]

        # Check supervisor
        supervisor_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'bot_supervisor.py' in cmdline:
                    supervisor_running = True
                    break
            except:
                continue

        status_lines.append(f"Supervisor: {'🟢 Running' if supervisor_running else '🔴 Stopped'}")

        # Check bots
        config = self.load_config()
        for bot_id, bot_config in config.get("bots", {}).items():
            running = False
            account_id = bot_config.get("account_id", "")
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'ultimate_trading_system' in cmdline and account_id in cmdline:
                        running = True
                        break
                except:
                    continue

            status_emoji = "🟢" if running else "🔴"
            status_lines.append(f"{bot_config['name']}: {status_emoji} {'Running' if running else 'Stopped'}")

        # Add timestamp
        status_lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(status_lines)

    def cmd_balance(self, chat_id: int, args: list) -> str:
        """Get account balances"""
        cst, token, api_config = self.get_capital_session()
        if not cst:
            return "❌ Failed to connect to Capital.com"

        try:
            url = f"{api_config['base_url']}/api/v1/accounts"
            headers = {
                "X-CAP-API-KEY": api_config['api_key'],
                "CST": cst,
                "X-SECURITY-TOKEN": token
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                accounts = response.json().get("accounts", [])
                lines = ["<b>💰 Account Balances</b>\n"]

                for acc in accounts:
                    balance = acc.get("balance", {})
                    lines.append(
                        f"<b>{acc.get('accountName', 'Unknown')}</b>\n"
                        f"  Balance: {balance.get('balance', 0):,.2f} {acc.get('currency', 'AED')}\n"
                        f"  Equity: {balance.get('equity', 0):,.2f} {acc.get('currency', 'AED')}\n"
                        f"  P/L: {balance.get('profitLoss', 0):+,.2f}\n"
                    )

                return "\n".join(lines)
            return "❌ Failed to fetch balances"
        except Exception as e:
            return f"❌ Error: {e}"

    def cmd_positions(self, chat_id: int, args: list) -> str:
        """Get open positions"""
        cst, token, api_config = self.get_capital_session()
        if not cst:
            return "❌ Failed to connect to Capital.com"

        try:
            url = f"{api_config['base_url']}/api/v1/positions"
            headers = {
                "X-CAP-API-KEY": api_config['api_key'],
                "CST": cst,
                "X-SECURITY-TOKEN": token
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                positions = response.json().get("positions", [])

                if not positions:
                    return "📭 No open positions"

                lines = ["<b>📈 Open Positions</b>\n"]

                for pos in positions:
                    market = pos.get("market", {})
                    position = pos.get("position", {})
                    direction = position.get("direction", "UNKNOWN")
                    emoji = "🟢" if direction == "BUY" else "🔴"

                    lines.append(
                        f"{emoji} <b>{market.get('instrumentName', 'XAUUSD')}</b>\n"
                        f"  Direction: {direction}\n"
                        f"  Size: {position.get('size', 0)}\n"
                        f"  Entry: {position.get('level', 0)}\n"
                        f"  Current: {market.get('bid', 0)}\n"
                        f"  P/L: {position.get('profit', 0):+.2f}\n"
                    )

                return "\n".join(lines)
            return "❌ Failed to fetch positions"
        except Exception as e:
            return f"❌ Error: {e}"

    def cmd_pause(self, chat_id: int, args: list) -> str:
        """Pause trading"""
        # Signal supervisor to pause
        config = self.load_config()
        config["paused"] = True
        self.save_config(config)

        # Stop bot processes
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'ultimate_trading_system' in cmdline:
                    psutil.Process(proc.info['pid']).terminate()
            except:
                continue

        return "⏸️ <b>Trading Paused</b>\n\nAll bots stopped. Use /resume to restart."

    def cmd_resume(self, chat_id: int, args: list) -> str:
        """Resume trading"""
        config = self.load_config()
        config["paused"] = False
        self.save_config(config)

        # Restart supervisor will handle starting bots
        return "▶️ <b>Trading Resumed</b>\n\nSupervisor will restart bots."

    def cmd_restart(self, chat_id: int, args: list) -> str:
        """Restart bots"""
        target = args[0] if args else "all"
        config = self.load_config()

        restarted = []

        for bot_id, bot_config in config.get("bots", {}).items():
            if target != "all" and target != bot_id:
                continue

            account_id = bot_config.get("account_id", "")
            script_path = os.path.join(BOT_DIR, bot_config.get("script", ""))

            # Kill existing process
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'ultimate_trading_system' in cmdline and account_id in cmdline:
                        psutil.Process(proc.info['pid']).terminate()
                        time.sleep(1)
                except:
                    continue

            # Start new process
            if os.path.exists(script_path):
                import subprocess
                log_path = os.path.join(BOT_DIR, bot_config.get("log", f"{bot_id}.log"))
                with open(log_path, 'a') as log_file:
                    subprocess.Popen(
                        ['bash', script_path],
                        cwd=BOT_DIR,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        start_new_session=True
                    )
                restarted.append(bot_config['name'])

        if restarted:
            return f"🔄 <b>Restarted:</b>\n" + "\n".join(f"  • {name}" for name in restarted)
        return "❌ No bots restarted"

    def cmd_stop(self, chat_id: int, args: list) -> str:
        """Stop bots"""
        target = args[0] if args else "all"
        config = self.load_config()

        stopped = []

        for bot_id, bot_config in config.get("bots", {}).items():
            if target != "all" and target != bot_id:
                continue

            account_id = bot_config.get("account_id", "")

            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'ultimate_trading_system' in cmdline and account_id in cmdline:
                        psutil.Process(proc.info['pid']).terminate()
                        stopped.append(bot_config['name'])
                except:
                    continue

        if stopped:
            return f"🛑 <b>Stopped:</b>\n" + "\n".join(f"  • {name}" for name in stopped)
        return "ℹ️ No running bots found"

    def cmd_report(self, chat_id: int, args: list) -> str:
        """Get performance report"""
        period = args[0] if args else "daily"

        cst, token, api_config = self.get_capital_session()
        if not cst:
            return "❌ Failed to connect to Capital.com"

        try:
            # Get account info
            url = f"{api_config['base_url']}/api/v1/accounts"
            headers = {
                "X-CAP-API-KEY": api_config['api_key'],
                "CST": cst,
                "X-SECURITY-TOKEN": token
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return "❌ Failed to fetch account data"

            accounts = response.json().get("accounts", [])

            # Get positions for trade count
            pos_url = f"{api_config['base_url']}/api/v1/positions"
            pos_response = requests.get(pos_url, headers=headers, timeout=10)
            positions = pos_response.json().get("positions", []) if pos_response.status_code == 200 else []

            lines = [f"<b>📊 {'Daily' if period == 'daily' else 'Weekly'} Report</b>\n"]
            lines.append(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

            total_balance = 0
            total_pl = 0

            for acc in accounts:
                balance = acc.get("balance", {})
                acc_balance = balance.get("balance", 0)
                acc_pl = balance.get("profitLoss", 0)
                total_balance += acc_balance
                total_pl += acc_pl

                lines.append(
                    f"<b>{acc.get('accountName', 'Unknown')}</b>\n"
                    f"  Balance: {acc_balance:,.2f} AED\n"
                    f"  P/L: {acc_pl:+,.2f}\n"
                )

            lines.append(f"\n<b>Summary:</b>")
            lines.append(f"  Total Balance: {total_balance:,.2f} AED")
            lines.append(f"  Total P/L: {total_pl:+,.2f}")
            lines.append(f"  Open Positions: {len(positions)}")

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error: {e}"

    def cmd_drawdown(self, chat_id: int, args: list) -> str:
        """Get drawdown levels"""
        cst, token, api_config = self.get_capital_session()
        if not cst:
            return "❌ Failed to connect to Capital.com"

        config = self.load_config()
        dd_config = config.get("drawdown_limits", {})

        try:
            url = f"{api_config['base_url']}/api/v1/accounts"
            headers = {
                "X-CAP-API-KEY": api_config['api_key'],
                "CST": cst,
                "X-SECURITY-TOKEN": token
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return "❌ Failed to fetch account data"

            accounts = response.json().get("accounts", [])

            lines = ["<b>📉 Drawdown Monitor</b>\n"]
            lines.append(f"Daily Limit: {dd_config.get('daily_max', 0.15)*100:.0f}%")
            lines.append(f"Weekly Limit: {dd_config.get('weekly_max', 0.25)*100:.0f}%\n")

            for acc in accounts:
                balance = acc.get("balance", {})
                equity = balance.get("equity", 0)
                starting = balance.get("balance", equity)

                if starting > 0:
                    dd = (starting - equity) / starting * 100
                    status = "🟢" if dd < dd_config.get('daily_max', 0.15) * 100 else "🔴"

                    lines.append(
                        f"<b>{acc.get('accountName', 'Unknown')}</b>\n"
                        f"  Current DD: {status} {dd:.1f}%\n"
                    )

            return "\n".join(lines)
        except Exception as e:
            return f"❌ Error: {e}"

    def cmd_config(self, chat_id: int, args: list) -> str:
        """View or update config"""
        config = self.load_config()

        if not args:
            # Show config summary (hide sensitive data)
            lines = ["<b>⚙️ Configuration</b>\n"]
            lines.append(f"Health Check Interval: {config.get('health_check_interval', 60)}s")
            lines.append(f"Max Restart Attempts: {config.get('max_restart_attempts', 5)}")
            lines.append(f"Daily DD Limit: {config.get('drawdown_limits', {}).get('daily_max', 0.15)*100:.0f}%")
            lines.append(f"Weekly DD Limit: {config.get('drawdown_limits', {}).get('weekly_max', 0.25)*100:.0f}%")
            lines.append(f"Auto Pause on DD: {config.get('drawdown_limits', {}).get('pause_on_breach', True)}")
            lines.append(f"\nBots Enabled:")
            for bot_id, bot_config in config.get("bots", {}).items():
                status = "✅" if bot_config.get("enabled", True) else "❌"
                lines.append(f"  {status} {bot_config.get('name', bot_id)}")

            return "\n".join(lines)

        if args[0] == "set" and len(args) >= 3:
            key = args[1]
            value = args[2]

            # Handle specific config updates
            if key == "daily_dd":
                config.setdefault("drawdown_limits", {})["daily_max"] = float(value) / 100
            elif key == "weekly_dd":
                config.setdefault("drawdown_limits", {})["weekly_max"] = float(value) / 100
            elif key == "health_interval":
                config["health_check_interval"] = int(value)
            elif key in ["bot1_enabled", "bot2_enabled"]:
                bot_id = key.replace("_enabled", "")
                if bot_id in config.get("bots", {}):
                    config["bots"][bot_id]["enabled"] = value.lower() == "true"
            else:
                return f"❌ Unknown config key: {key}"

            self.save_config(config)
            return f"✅ Config updated: {key} = {value}"

        return "Usage: /config or /config set <key> <value>"

    def cmd_logs(self, chat_id: int, args: list) -> str:
        """Get recent log entries"""
        target = args[0] if args else "bot1"
        lines_count = 20

        log_files = {
            "bot1": "bot1.log",
            "bot2": "bot2.log",
            "supervisor": "supervisor.log"
        }

        log_file = log_files.get(target, "bot1.log")
        log_path = os.path.join(BOT_DIR, log_file)

        if not os.path.exists(log_path):
            return f"❌ Log file not found: {log_file}"

        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()
                recent = lines[-lines_count:] if len(lines) >= lines_count else lines

            return f"<b>📜 {log_file} (last {len(recent)} lines)</b>\n\n<pre>" + "".join(recent) + "</pre>"
        except Exception as e:
            return f"❌ Error reading logs: {e}"

    def cmd_health(self, chat_id: int, args: list) -> str:
        """System health check"""
        lines = ["<b>🏥 System Health</b>\n"]

        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = "🟢" if cpu_percent < 80 else "🟡" if cpu_percent < 95 else "🔴"
        lines.append(f"{cpu_status} CPU: {cpu_percent}%")

        # Memory
        mem = psutil.virtual_memory()
        mem_status = "🟢" if mem.percent < 80 else "🟡" if mem.percent < 95 else "🔴"
        lines.append(f"{mem_status} Memory: {mem.percent}% ({mem.used/1024/1024/1024:.1f}GB / {mem.total/1024/1024/1024:.1f}GB)")

        # Disk
        disk = psutil.disk_usage('/')
        disk_status = "🟢" if disk.percent < 80 else "🟡" if disk.percent < 95 else "🔴"
        lines.append(f"{disk_status} Disk: {disk.percent}% ({disk.used/1024/1024/1024:.1f}GB / {disk.total/1024/1024/1024:.1f}GB)")

        # Network
        try:
            response = requests.get("https://api.telegram.org", timeout=5)
            net_status = "🟢" if response.status_code == 200 else "🟡"
        except:
            net_status = "🔴"
        lines.append(f"{net_status} Network: {'OK' if net_status == '🟢' else 'Issues'}")

        # Uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        lines.append(f"\n⏱️ Uptime: {str(uptime).split('.')[0]}")

        return "\n".join(lines)

    def cmd_disk(self, chat_id: int, args: list) -> str:
        """Disk usage details"""
        lines = ["<b>💾 Disk Usage</b>\n"]

        disk = psutil.disk_usage('/')
        lines.append(f"Total: {disk.total/1024/1024/1024:.1f} GB")
        lines.append(f"Used: {disk.used/1024/1024/1024:.1f} GB ({disk.percent}%)")
        lines.append(f"Free: {disk.free/1024/1024/1024:.1f} GB")

        # Log file sizes
        lines.append("\n<b>Log Files:</b>")
        log_files = ["bot1.log", "bot2.log", "supervisor.log", "fixed_rr_detailed.log", "adaptive_detailed.log"]

        for log_file in log_files:
            log_path = os.path.join(BOT_DIR, log_file)
            if os.path.exists(log_path):
                size = os.path.getsize(log_path) / 1024 / 1024
                lines.append(f"  {log_file}: {size:.1f} MB")

        return "\n".join(lines)

    def process_message(self, message: dict):
        """Process incoming message"""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        # Security check
        if chat_id not in ALLOWED_CHAT_IDS:
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return

        if not text.startswith('/'):
            return

        # Parse command and args
        parts = text.split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Handle command
        handler = self.commands.get(command)
        if handler:
            try:
                response = handler(chat_id, args)
                self.send_message(response, chat_id)
            except Exception as e:
                logger.error(f"Command error: {e}")
                self.send_message(f"❌ Error: {e}", chat_id)
        else:
            self.send_message("❓ Unknown command. Use /help for available commands.", chat_id)

    def run(self):
        """Main bot loop"""
        self.running = True
        logger.info("Telegram Commander starting...")

        self.send_message(
            "🟢 <b>Telegram Commander Online</b>\n\n"
            "Use /help to see available commands."
        )

        while self.running:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.last_update_id = update["update_id"]

                    if "message" in update:
                        self.process_message(update["message"])

                time.sleep(1)

            except Exception as e:
                logger.error(f"Bot loop error: {e}")
                time.sleep(5)

        logger.info("Telegram Commander stopped")


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
