#!/usr/bin/env python3
"""
Automated Report Generator for Trading Bot
Generates and sends daily/weekly performance reports.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import requests
import schedule
import time
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuration
CONFIG_FILE = "/home/trader/supervisor_config.json"
LOG_FILE = "/home/trader/report_generator.log"

# Database config
DB_CONFIG = {
    "host": "165.227.191.236",
    "database": "trading_bot",
    "user": "trader",
    "password": "TradingBot2026Secure!"
}

# Telegram config
TELEGRAM_TOKEN = "8376345331:AAHWoZzkqT26cyeRPGa8MfcaVZWvTcan9lU"
CHAT_ID = "7831118282"

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


class DatabaseClient:
    """PostgreSQL database client for trade data"""

    def __init__(self):
        self.config = DB_CONFIG
        self.conn = None

    def connect(self) -> bool:
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(**self.config)
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute query and return results"""
        if not self.conn:
            if not self.connect():
                return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    def get_trades(self, start_date: datetime, end_date: datetime = None) -> List[Dict]:
        """Get trades within date range"""
        if end_date is None:
            end_date = datetime.now()

        query = """
            SELECT * FROM trades
            WHERE created_at >= %s AND created_at <= %s
            ORDER BY created_at DESC
        """
        return self.execute_query(query, (start_date, end_date))

    def get_signals(self, start_date: datetime, end_date: datetime = None) -> List[Dict]:
        """Get signals within date range"""
        if end_date is None:
            end_date = datetime.now()

        query = """
            SELECT * FROM signals
            WHERE created_at >= %s AND created_at <= %s
            ORDER BY created_at DESC
        """
        return self.execute_query(query, (start_date, end_date))


class CapitalAPIClient:
    """Capital.com API client"""

    def __init__(self):
        self.config = self.load_config()
        self.api_config = self.config.get("capital_api", {})
        self.cst = None
        self.security_token = None

    def load_config(self) -> dict:
        """Load supervisor config"""
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    def authenticate(self) -> bool:
        """Authenticate with Capital.com"""
        try:
            url = f"{self.api_config['base_url']}/api/v1/session"
            headers = {
                "X-CAP-API-KEY": self.api_config['api_key'],
                "Content-Type": "application/json"
            }
            payload = {
                "identifier": self.api_config['identifier'],
                "password": self.api_config['password']
            }
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 200:
                self.cst = response.headers.get("CST")
                self.security_token = response.headers.get("X-SECURITY-TOKEN")
                return True
            return False
        except Exception as e:
            logger.error(f"Auth failed: {e}")
            return False

    def get_headers(self) -> dict:
        """Get authenticated headers"""
        return {
            "X-CAP-API-KEY": self.api_config['api_key'],
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.security_token
        }

    def get_accounts(self) -> List[Dict]:
        """Get all accounts"""
        if not self.cst and not self.authenticate():
            return []

        try:
            url = f"{self.api_config['base_url']}/api/v1/accounts"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                return response.json().get("accounts", [])
            return []
        except Exception as e:
            logger.error(f"Get accounts failed: {e}")
            return []

    def get_positions(self) -> List[Dict]:
        """Get open positions"""
        if not self.cst and not self.authenticate():
            return []

        try:
            url = f"{self.api_config['base_url']}/api/v1/positions"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                return response.json().get("positions", [])
            return []
        except Exception as e:
            logger.error(f"Get positions failed: {e}")
            return []

    def get_activity(self, from_date: datetime, to_date: datetime = None) -> List[Dict]:
        """Get account activity/history"""
        if not self.cst and not self.authenticate():
            return []

        if to_date is None:
            to_date = datetime.now()

        try:
            url = f"{self.api_config['base_url']}/api/v1/history/activity"
            params = {
                "from": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": to_date.strftime("%Y-%m-%dT%H:%M:%S")
            }
            response = requests.get(url, headers=self.get_headers(), params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("activities", [])
            return []
        except Exception as e:
            logger.error(f"Get activity failed: {e}")
            return []


class TelegramNotifier:
    """Telegram notification sender"""

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send message to Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"

            # Split long messages
            if len(message) > 4000:
                chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                for chunk in chunks:
                    payload = {
                        "chat_id": self.chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode
                    }
                    requests.post(url, json=payload, timeout=10)
                return True

            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False


class ReportGenerator:
    """Generate trading performance reports"""

    def __init__(self):
        self.db = DatabaseClient()
        self.api = CapitalAPIClient()
        self.notifier = TelegramNotifier()

    def generate_daily_report(self) -> str:
        """Generate daily performance report"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        lines = []
        lines.append("📊 <b>DAILY REPORT</b>")
        lines.append(f"📅 {today.strftime('%A, %B %d, %Y')}")
        lines.append("")

        # Get account data
        accounts = self.api.get_accounts()
        total_balance = 0
        total_pl = 0

        lines.append("<b>💰 Account Balances:</b>")
        for acc in accounts:
            balance = acc.get("balance", {})
            acc_balance = balance.get("balance", 0)
            acc_equity = balance.get("equity", 0)
            acc_pl = balance.get("profitLoss", 0)
            total_balance += acc_balance
            total_pl += acc_pl

            pl_emoji = "📈" if acc_pl >= 0 else "📉"

            lines.append(f"\n<b>{acc.get('accountName', 'Unknown')}</b>")
            lines.append(f"  Balance: {acc_balance:,.2f} AED")
            lines.append(f"  Equity: {acc_equity:,.2f} AED")
            lines.append(f"  {pl_emoji} P/L: {acc_pl:+,.2f} AED")

        lines.append("")
        lines.append("<b>📊 Summary:</b>")
        lines.append(f"  Total Balance: {total_balance:,.2f} AED")
        total_pl_emoji = "📈" if total_pl >= 0 else "📉"
        lines.append(f"  {total_pl_emoji} Total P/L: {total_pl:+,.2f} AED")

        # Get open positions
        positions = self.api.get_positions()
        lines.append(f"\n<b>📈 Open Positions:</b> {len(positions)}")

        if positions:
            for pos in positions[:5]:  # Show max 5
                market = pos.get("market", {})
                position = pos.get("position", {})
                direction = position.get("direction", "?")
                profit = position.get("profit", 0)
                emoji = "🟢" if direction == "BUY" else "🔴"
                pl_emoji = "+" if profit >= 0 else ""
                lines.append(f"  {emoji} {direction} @ {position.get('level', 0):.2f} ({pl_emoji}{profit:.2f})")

        # Get today's activity
        activity = self.api.get_activity(yesterday, today)
        trades_today = [a for a in activity if a.get("type") in ["POSITION", "ORDER"]]

        lines.append(f"\n<b>📝 Today's Activity:</b> {len(trades_today)} trades")

        # Calculate win rate from recent trades
        if trades_today:
            wins = sum(1 for t in trades_today if t.get("details", {}).get("profit", 0) > 0)
            total = len([t for t in trades_today if "profit" in t.get("details", {})])
            if total > 0:
                win_rate = wins / total * 100
                lines.append(f"  Win Rate: {win_rate:.0f}% ({wins}/{total})")

        # Add performance vs target
        # Target: 4X in 30 days = ~5% daily growth needed
        starting_balance = 50838 + 54000  # Initial combined balance
        target_daily_growth = 0.05
        expected_balance = starting_balance * (1 + target_daily_growth)
        progress = (total_balance / expected_balance) * 100 if expected_balance > 0 else 0

        lines.append(f"\n<b>🎯 Progress vs Target:</b>")
        lines.append(f"  Current: {total_balance:,.0f} AED")
        lines.append(f"  Target: {expected_balance:,.0f} AED")
        progress_emoji = "✅" if progress >= 100 else "⏳"
        lines.append(f"  {progress_emoji} Progress: {progress:.1f}%")

        lines.append(f"\n⏰ Report generated: {datetime.now().strftime('%H:%M:%S')}")

        return "\n".join(lines)

    def generate_weekly_report(self) -> str:
        """Generate weekly performance report"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        lines = []
        lines.append("📊 <b>WEEKLY REPORT</b>")
        lines.append(f"📅 Week of {week_start.strftime('%B %d, %Y')}")
        lines.append("")

        # Get account data
        accounts = self.api.get_accounts()
        total_balance = 0
        total_pl = 0

        lines.append("<b>💰 Account Status:</b>")
        for acc in accounts:
            balance = acc.get("balance", {})
            acc_balance = balance.get("balance", 0)
            acc_pl = balance.get("profitLoss", 0)
            total_balance += acc_balance
            total_pl += acc_pl

            pl_pct = (acc_pl / acc_balance * 100) if acc_balance > 0 else 0
            pl_emoji = "📈" if acc_pl >= 0 else "📉"

            lines.append(f"\n<b>{acc.get('accountName', 'Unknown')}</b>")
            lines.append(f"  Balance: {acc_balance:,.2f} AED")
            lines.append(f"  {pl_emoji} P/L: {acc_pl:+,.2f} ({pl_pct:+.1f}%)")

        # Get week's activity
        activity = self.api.get_activity(week_start)
        trades = [a for a in activity if a.get("type") in ["POSITION", "ORDER"]]

        # Analyze trades
        wins = 0
        losses = 0
        total_profit = 0
        total_loss = 0

        for trade in trades:
            profit = trade.get("details", {}).get("profit", 0)
            if profit > 0:
                wins += 1
                total_profit += profit
            elif profit < 0:
                losses += 1
                total_loss += abs(profit)

        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf')

        lines.append("")
        lines.append("<b>📈 Trading Statistics:</b>")
        lines.append(f"  Total Trades: {total_trades}")
        lines.append(f"  Wins: {wins} | Losses: {losses}")
        lines.append(f"  Win Rate: {win_rate:.1f}%")
        lines.append(f"  Gross Profit: +{total_profit:,.2f} AED")
        lines.append(f"  Gross Loss: -{total_loss:,.2f} AED")
        lines.append(f"  Net P/L: {total_profit - total_loss:+,.2f} AED")
        if profit_factor != float('inf'):
            lines.append(f"  Profit Factor: {profit_factor:.2f}")

        # Weekly target progress
        # Target: 4X in 30 days = ~35% weekly growth
        starting_balance = 50838 + 54000
        weekly_target_growth = 0.35
        expected_weekly = starting_balance * (1 + weekly_target_growth)
        progress = (total_balance / expected_weekly) * 100 if expected_weekly > 0 else 0

        lines.append("")
        lines.append("<b>🎯 Weekly Target Progress:</b>")
        lines.append(f"  Starting: {starting_balance:,.0f} AED")
        lines.append(f"  Current: {total_balance:,.0f} AED")
        lines.append(f"  Target: {expected_weekly:,.0f} AED")

        growth_pct = ((total_balance - starting_balance) / starting_balance * 100) if starting_balance > 0 else 0
        growth_emoji = "🚀" if growth_pct >= weekly_target_growth * 100 else "📈" if growth_pct > 0 else "📉"
        lines.append(f"  {growth_emoji} Growth: {growth_pct:+.1f}%")

        # Insights
        lines.append("")
        lines.append("<b>💡 Insights:</b>")

        if win_rate >= 40:
            lines.append("  ✅ Win rate on track (target: 39%)")
        else:
            lines.append("  ⚠️ Win rate below target (need 39%)")

        if profit_factor >= 1.5:
            lines.append("  ✅ Good profit factor")
        else:
            lines.append("  ⚠️ Profit factor needs improvement")

        # Best/worst days (simplified)
        lines.append("")
        lines.append(f"⏰ Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def generate_trade_summary(self, hours: int = 24) -> str:
        """Generate trade summary for last N hours"""
        from_time = datetime.now() - timedelta(hours=hours)

        activity = self.api.get_activity(from_time)
        trades = [a for a in activity if a.get("type") in ["POSITION"]]

        if not trades:
            return f"📭 No trades in the last {hours} hours"

        lines = [f"<b>📊 Last {hours}h Trade Summary</b>", ""]

        for trade in trades[:10]:  # Show max 10
            details = trade.get("details", {})
            profit = details.get("profit", 0)
            status = trade.get("status", "")
            direction = details.get("direction", "?")

            emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
            dir_emoji = "📈" if direction == "BUY" else "📉"

            lines.append(
                f"{emoji} {dir_emoji} {details.get('marketName', 'XAUUSD')}: "
                f"{profit:+.2f} AED"
            )

        return "\n".join(lines)

    def send_daily_report(self):
        """Generate and send daily report"""
        logger.info("Generating daily report...")
        try:
            report = self.generate_daily_report()
            self.notifier.send(report)
            logger.info("Daily report sent")
        except Exception as e:
            logger.error(f"Daily report failed: {e}")

    def send_weekly_report(self):
        """Generate and send weekly report"""
        logger.info("Generating weekly report...")
        try:
            report = self.generate_weekly_report()
            self.notifier.send(report)
            logger.info("Weekly report sent")
        except Exception as e:
            logger.error(f"Weekly report failed: {e}")


def run_scheduler():
    """Run the report scheduler"""
    generator = ReportGenerator()

    # Schedule daily report at 20:00 (8 PM local time)
    schedule.every().day.at("20:00").do(generator.send_daily_report)

    # Schedule weekly report on Sunday at 21:00
    schedule.every().sunday.at("21:00").do(generator.send_weekly_report)

    logger.info("Report scheduler started")
    logger.info("Daily report: 20:00 every day")
    logger.info("Weekly report: 21:00 every Sunday")

    # Send startup notification
    generator.notifier.send(
        "📊 <b>Report Generator Started</b>\n\n"
        "Daily reports: 8:00 PM\n"
        "Weekly reports: Sunday 9:00 PM"
    )

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        generator = ReportGenerator()

        if sys.argv[1] == "daily":
            print(generator.generate_daily_report())
        elif sys.argv[1] == "weekly":
            print(generator.generate_weekly_report())
        elif sys.argv[1] == "send-daily":
            generator.send_daily_report()
        elif sys.argv[1] == "send-weekly":
            generator.send_weekly_report()
        else:
            print("Usage: report_generator.py [daily|weekly|send-daily|send-weekly]")
    else:
        run_scheduler()
