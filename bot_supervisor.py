#!/usr/bin/env python3
"""
Gold Trading Bot Supervisor
Manages bot health, auto-restart, drawdown protection, and coordination.
"""

import os
import sys
import json
import time
import signal
import logging
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
import psutil
import requests

# Configuration
CONFIG_FILE = "/home/trader/supervisor_config.json"
BOT_DIR = "/home/trader"
LOG_FILE = "/home/trader/supervisor.log"

DEFAULT_CONFIG = {
    "bots": {
        "bot1": {
            "name": "Fixed R:R Bot",
            "script": "start_bot1.sh",
            "log": "bot1.log",
            "account_id": "303527589371466014",
            "enabled": True
        },
        "bot2": {
            "name": "Adaptive Bot",
            "script": "start_bot2.sh",
            "log": "bot2.log",
            "account_id": "303621563255902494",
            "enabled": True
        }
    },
    "health_check_interval": 60,
    "max_restart_attempts": 5,
    "restart_cooldown": 300,
    "drawdown_limits": {
        "daily_max": 0.15,
        "weekly_max": 0.25,
        "pause_on_breach": True
    },
    "telegram": {
        "token": "8376345331:AAHWoZzkqT26cyeRPGa8MfcaVZWvTcan9lU",
        "chat_id": "7831118282",
        "notify_on_restart": True,
        "notify_on_drawdown": True
    },
    "capital_api": {
        "base_url": "https://demo-api-capital.backend-capital.com",
        "api_key": "3F3RHbKsBbivSLYe",
        "identifier": "saurav.patr@gmail.com",
        "password": "Cl@ud#123"
    },
    "maintenance": {
        "log_rotation_days": 7,
        "disk_warning_threshold": 0.85,
        "auto_cleanup": True
    }
}

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


class TelegramNotifier:
    """Send notifications via Telegram"""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False


class CapitalAPIClient:
    """Capital.com API client for account data"""

    def __init__(self, config: dict):
        self.base_url = config["base_url"]
        self.api_key = config["api_key"]
        self.identifier = config["identifier"]
        self.password = config["password"]
        self.session_token = None
        self.cst = None

    def authenticate(self) -> bool:
        """Authenticate with Capital.com"""
        try:
            url = f"{self.base_url}/api/v1/session"
            headers = {
                "X-CAP-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "identifier": self.identifier,
                "password": self.password
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                self.cst = response.headers.get("CST")
                self.session_token = response.headers.get("X-SECURITY-TOKEN")
                return True
            return False
        except Exception as e:
            logger.error(f"Capital.com auth failed: {e}")
            return False

    def get_account_balance(self, account_id: str) -> dict:
        """Get account balance and equity"""
        if not self.session_token:
            if not self.authenticate():
                return None

        try:
            url = f"{self.base_url}/api/v1/accounts"
            headers = {
                "X-CAP-API-KEY": self.api_key,
                "CST": self.cst,
                "X-SECURITY-TOKEN": self.session_token
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                accounts = response.json().get("accounts", [])
                for acc in accounts:
                    if acc.get("accountId") == account_id:
                        return {
                            "balance": acc.get("balance", {}).get("balance", 0),
                            "equity": acc.get("balance", {}).get("equity", 0),
                            "profit_loss": acc.get("balance", {}).get("profitLoss", 0),
                            "currency": acc.get("currency", "AED")
                        }
            return None
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return None

    def get_open_positions(self, account_id: str = None) -> list:
        """Get open positions"""
        if not self.session_token:
            if not self.authenticate():
                return []

        try:
            url = f"{self.base_url}/api/v1/positions"
            headers = {
                "X-CAP-API-KEY": self.api_key,
                "CST": self.cst,
                "X-SECURITY-TOKEN": self.session_token
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("positions", [])
            return []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []


class DrawdownMonitor:
    """Monitor and track drawdown"""

    def __init__(self, config: dict, api_client: CapitalAPIClient, notifier: TelegramNotifier):
        self.config = config
        self.api = api_client
        self.notifier = notifier
        self.daily_start_balance = {}
        self.weekly_start_balance = {}
        self.paused = False
        self.last_check = None

    def initialize_balances(self, account_id: str):
        """Initialize starting balances for drawdown tracking"""
        balance_data = self.api.get_account_balance(account_id)
        if balance_data:
            equity = balance_data["equity"]
            now = datetime.now()

            # Set daily start if not set or new day
            if account_id not in self.daily_start_balance:
                self.daily_start_balance[account_id] = {
                    "value": equity,
                    "date": now.date()
                }
            elif self.daily_start_balance[account_id]["date"] != now.date():
                self.daily_start_balance[account_id] = {
                    "value": equity,
                    "date": now.date()
                }

            # Set weekly start if not set or new week
            week_start = now.date() - timedelta(days=now.weekday())
            if account_id not in self.weekly_start_balance:
                self.weekly_start_balance[account_id] = {
                    "value": equity,
                    "week_start": week_start
                }
            elif self.weekly_start_balance[account_id]["week_start"] != week_start:
                self.weekly_start_balance[account_id] = {
                    "value": equity,
                    "week_start": week_start
                }

    def check_drawdown(self, account_id: str) -> dict:
        """Check current drawdown levels"""
        self.initialize_balances(account_id)
        balance_data = self.api.get_account_balance(account_id)

        if not balance_data:
            return {"error": "Could not fetch balance"}

        equity = balance_data["equity"]
        daily_start = self.daily_start_balance.get(account_id, {}).get("value", equity)
        weekly_start = self.weekly_start_balance.get(account_id, {}).get("value", equity)

        daily_dd = (daily_start - equity) / daily_start if daily_start > 0 else 0
        weekly_dd = (weekly_start - equity) / weekly_start if weekly_start > 0 else 0

        result = {
            "equity": equity,
            "daily_start": daily_start,
            "weekly_start": weekly_start,
            "daily_drawdown": daily_dd,
            "weekly_drawdown": weekly_dd,
            "daily_limit": self.config["daily_max"],
            "weekly_limit": self.config["weekly_max"],
            "daily_breached": daily_dd >= self.config["daily_max"],
            "weekly_breached": weekly_dd >= self.config["weekly_max"]
        }

        # Check for limit breach
        if result["daily_breached"] or result["weekly_breached"]:
            if self.config["pause_on_breach"] and not self.paused:
                self.paused = True
                breach_type = "DAILY" if result["daily_breached"] else "WEEKLY"
                dd_pct = daily_dd if result["daily_breached"] else weekly_dd

                msg = (
                    f"🚨 <b>DRAWDOWN LIMIT BREACHED</b>\n\n"
                    f"Type: {breach_type}\n"
                    f"Drawdown: {dd_pct*100:.1f}%\n"
                    f"Limit: {self.config['daily_max' if result['daily_breached'] else 'weekly_max']*100:.0f}%\n\n"
                    f"⏸️ <b>Trading PAUSED</b>\n"
                    f"Use /resume to restart"
                )
                self.notifier.send(msg)
                logger.warning(f"Drawdown limit breached: {breach_type} at {dd_pct*100:.1f}%")

        self.last_check = datetime.now()
        return result


class BotProcess:
    """Manage a single bot process"""

    def __init__(self, bot_id: str, config: dict, notifier: TelegramNotifier):
        self.bot_id = bot_id
        self.config = config
        self.notifier = notifier
        self.process = None
        self.pid = None
        self.restart_count = 0
        self.last_restart = None
        self.start_time = None

    def is_running(self) -> bool:
        """Check if bot process is running"""
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Check by process name
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'ultimate_trading_system' in cmdline and self.config['account_id'] in cmdline:
                    self.pid = proc.info['pid']
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False

    def start(self) -> bool:
        """Start the bot"""
        if self.is_running():
            logger.info(f"{self.bot_id}: Already running (PID: {self.pid})")
            return True

        try:
            script_path = os.path.join(BOT_DIR, self.config['script'])
            if not os.path.exists(script_path):
                logger.error(f"{self.bot_id}: Script not found: {script_path}")
                return False

            log_path = os.path.join(BOT_DIR, self.config['log'])
            with open(log_path, 'a') as log_file:
                self.process = subprocess.Popen(
                    ['bash', script_path],
                    cwd=BOT_DIR,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )

            time.sleep(2)  # Wait for process to start

            if self.is_running():
                self.start_time = datetime.now()
                logger.info(f"{self.bot_id}: Started successfully (PID: {self.pid})")
                return True
            else:
                logger.error(f"{self.bot_id}: Failed to start")
                return False

        except Exception as e:
            logger.error(f"{self.bot_id}: Start error: {e}")
            return False

    def stop(self) -> bool:
        """Stop the bot"""
        if not self.is_running():
            logger.info(f"{self.bot_id}: Not running")
            return True

        try:
            proc = psutil.Process(self.pid)
            proc.terminate()
            proc.wait(timeout=10)
            self.pid = None
            self.process = None
            logger.info(f"{self.bot_id}: Stopped")
            return True
        except psutil.TimeoutExpired:
            proc.kill()
            self.pid = None
            return True
        except Exception as e:
            logger.error(f"{self.bot_id}: Stop error: {e}")
            return False

    def restart(self, notify: bool = True) -> bool:
        """Restart the bot with cooldown protection"""
        now = datetime.now()

        # Check restart cooldown
        if self.last_restart:
            cooldown = 300  # 5 minutes
            elapsed = (now - self.last_restart).total_seconds()
            if elapsed < cooldown:
                logger.warning(f"{self.bot_id}: Restart cooldown active ({cooldown - elapsed:.0f}s remaining)")
                return False

        # Check max restart attempts
        if self.restart_count >= 5:
            logger.error(f"{self.bot_id}: Max restart attempts reached")
            if notify:
                self.notifier.send(
                    f"🚨 <b>{self.config['name']}</b>\n\n"
                    f"Max restart attempts (5) reached!\n"
                    f"Manual intervention required."
                )
            return False

        self.stop()
        time.sleep(2)
        success = self.start()

        if success:
            self.restart_count += 1
            self.last_restart = now
            if notify:
                self.notifier.send(
                    f"🔄 <b>{self.config['name']}</b>\n\n"
                    f"Bot restarted automatically\n"
                    f"Restart count: {self.restart_count}/5"
                )

        return success

    def get_status(self) -> dict:
        """Get bot status"""
        running = self.is_running()
        uptime = None
        if running and self.start_time:
            uptime = str(datetime.now() - self.start_time).split('.')[0]

        return {
            "bot_id": self.bot_id,
            "name": self.config["name"],
            "running": running,
            "pid": self.pid if running else None,
            "uptime": uptime,
            "restart_count": self.restart_count,
            "enabled": self.config.get("enabled", True)
        }


class BotSupervisor:
    """Main supervisor that coordinates all bot management"""

    def __init__(self):
        self.config = self.load_config()
        self.notifier = TelegramNotifier(
            self.config["telegram"]["token"],
            self.config["telegram"]["chat_id"]
        )
        self.api = CapitalAPIClient(self.config["capital_api"])
        self.drawdown_monitor = DrawdownMonitor(
            self.config["drawdown_limits"],
            self.api,
            self.notifier
        )
        self.bots = {}
        self.running = False
        self.paused = False

        # Initialize bot processes
        for bot_id, bot_config in self.config["bots"].items():
            self.bots[bot_id] = BotProcess(bot_id, bot_config, self.notifier)

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

    def load_config(self) -> dict:
        """Load configuration from file or create default"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults for any missing keys
                    return {**DEFAULT_CONFIG, **config}
            except Exception as e:
                logger.error(f"Error loading config: {e}")

        # Save default config
        self.save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    def save_config(self, config: dict = None):
        """Save configuration to file"""
        if config is None:
            config = self.config
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Shutdown signal received")
        self.running = False
        for bot in self.bots.values():
            bot.stop()

    def health_check(self):
        """Check health of all bots and restart if needed"""
        for bot_id, bot in self.bots.items():
            if not bot.config.get("enabled", True):
                continue

            if self.paused or self.drawdown_monitor.paused:
                continue

            if not bot.is_running():
                logger.warning(f"{bot_id}: Not running, attempting restart")
                bot.restart(notify=self.config["telegram"]["notify_on_restart"])

    def check_all_drawdowns(self):
        """Check drawdown for all accounts"""
        for bot_id, bot in self.bots.items():
            account_id = bot.config.get("account_id")
            if account_id:
                self.drawdown_monitor.check_drawdown(account_id)

    def get_status(self) -> dict:
        """Get overall system status"""
        bot_statuses = {bot_id: bot.get_status() for bot_id, bot in self.bots.items()}

        # Get account balances
        accounts = {}
        for bot_id, bot in self.bots.items():
            account_id = bot.config.get("account_id")
            if account_id:
                balance = self.api.get_account_balance(account_id)
                if balance:
                    accounts[bot_id] = balance

        return {
            "supervisor_running": self.running,
            "paused": self.paused or self.drawdown_monitor.paused,
            "bots": bot_statuses,
            "accounts": accounts,
            "timestamp": datetime.now().isoformat()
        }

    def start_all(self):
        """Start all enabled bots"""
        for bot_id, bot in self.bots.items():
            if bot.config.get("enabled", True):
                bot.start()

    def stop_all(self):
        """Stop all bots"""
        for bot in self.bots.values():
            bot.stop()

    def pause_trading(self):
        """Pause all trading"""
        self.paused = True
        self.stop_all()
        logger.info("Trading paused")
        self.notifier.send("⏸️ <b>Trading Paused</b>\n\nAll bots stopped. Use /resume to restart.")

    def resume_trading(self):
        """Resume trading"""
        self.paused = False
        self.drawdown_monitor.paused = False
        self.start_all()
        logger.info("Trading resumed")
        self.notifier.send("▶️ <b>Trading Resumed</b>\n\nAll bots restarted.")

    def run(self):
        """Main supervisor loop"""
        self.running = True
        logger.info("Bot Supervisor starting...")

        # Initial notification
        self.notifier.send(
            "🟢 <b>Bot Supervisor Started</b>\n\n"
            "Monitoring bots for health and drawdown.\n"
            "Use Telegram commands to control."
        )

        # Start all bots
        self.start_all()

        last_health_check = datetime.now()
        last_drawdown_check = datetime.now()
        health_interval = self.config.get("health_check_interval", 60)

        while self.running:
            try:
                now = datetime.now()

                # Health check
                if (now - last_health_check).total_seconds() >= health_interval:
                    self.health_check()
                    last_health_check = now

                # Drawdown check every 5 minutes
                if (now - last_drawdown_check).total_seconds() >= 300:
                    self.check_all_drawdowns()
                    last_drawdown_check = now

                time.sleep(10)

            except Exception as e:
                logger.error(f"Supervisor error: {e}")
                time.sleep(30)

        logger.info("Bot Supervisor stopped")


if __name__ == "__main__":
    supervisor = BotSupervisor()
    supervisor.run()
