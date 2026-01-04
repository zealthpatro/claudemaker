#!/usr/bin/env python3
"""
Log Analyzer for Trading Bot
Analyzes trade logs for patterns and insights.
"""

import os
import re
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional
import requests

# Configuration
BOT_DIR = "/home/trader"
LOG_FILE = "/home/trader/log_analyzer.log"

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


class LogParser:
    """Parse trading bot logs"""

    # Regex patterns for log parsing
    PATTERNS = {
        'trade_entry': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*TRADE ENTRY.*'
            r'Setup: ([^|]+)\|.*Direction: (BUY|SELL).*'
            r'Entry: ([\d.]+).*Stop: ([\d.]+).*Target: ([\d.]+)'
        ),
        'trade_exit': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*TRADE EXIT.*'
            r'Result: (WIN|LOSS|BREAKEVEN).*P/L: ([+-]?[\d.]+)'
        ),
        'signal': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*SIGNAL.*'
            r'Setup: ([^|]+).*Timeframe: (\w+).*Direction: (BUY|SELL)'
        ),
        'error': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*ERROR.*(.+)'
        ),
        'drawdown': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*DRAWDOWN.*'
            r'Daily: ([\d.]+)%.*Weekly: ([\d.]+)%'
        ),
        'session': re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*SESSION (STARTED|REFRESHED|EXPIRED)'
        )
    }

    def __init__(self, log_file: str):
        self.log_file = log_file
        self.entries = []

    def parse(self) -> List[Dict]:
        """Parse log file and extract entries"""
        if not os.path.exists(self.log_file):
            logger.warning(f"Log file not found: {self.log_file}")
            return []

        entries = []

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    entry = self._parse_line(line)
                    if entry:
                        entries.append(entry)
        except Exception as e:
            logger.error(f"Error parsing log: {e}")

        self.entries = entries
        return entries

    def _parse_line(self, line: str) -> Optional[Dict]:
        """Parse a single log line"""
        for entry_type, pattern in self.PATTERNS.items():
            match = pattern.search(line)
            if match:
                groups = match.groups()
                timestamp = datetime.strptime(groups[0], '%Y-%m-%d %H:%M:%S')

                if entry_type == 'trade_entry':
                    return {
                        'type': 'trade_entry',
                        'timestamp': timestamp,
                        'setup': groups[1].strip(),
                        'direction': groups[2],
                        'entry': float(groups[3]),
                        'stop': float(groups[4]),
                        'target': float(groups[5])
                    }
                elif entry_type == 'trade_exit':
                    return {
                        'type': 'trade_exit',
                        'timestamp': timestamp,
                        'result': groups[1],
                        'profit_loss': float(groups[2])
                    }
                elif entry_type == 'signal':
                    return {
                        'type': 'signal',
                        'timestamp': timestamp,
                        'setup': groups[1].strip(),
                        'timeframe': groups[2],
                        'direction': groups[3]
                    }
                elif entry_type == 'error':
                    return {
                        'type': 'error',
                        'timestamp': timestamp,
                        'message': groups[1].strip()
                    }
                elif entry_type == 'drawdown':
                    return {
                        'type': 'drawdown',
                        'timestamp': timestamp,
                        'daily': float(groups[1]),
                        'weekly': float(groups[2])
                    }
                elif entry_type == 'session':
                    return {
                        'type': 'session',
                        'timestamp': timestamp,
                        'status': groups[1]
                    }

        return None


class TradeAnalyzer:
    """Analyze trading patterns and performance"""

    def __init__(self):
        self.trades = []
        self.signals = []
        self.errors = []

    def load_logs(self, log_files: List[str] = None):
        """Load and parse log files"""
        if log_files is None:
            log_files = [
                os.path.join(BOT_DIR, "fixed_rr_detailed.log"),
                os.path.join(BOT_DIR, "adaptive_detailed.log"),
                os.path.join(BOT_DIR, "bot1.log"),
                os.path.join(BOT_DIR, "bot2.log")
            ]

        for log_file in log_files:
            parser = LogParser(log_file)
            entries = parser.parse()

            for entry in entries:
                if entry['type'] in ['trade_entry', 'trade_exit']:
                    self.trades.append(entry)
                elif entry['type'] == 'signal':
                    self.signals.append(entry)
                elif entry['type'] == 'error':
                    self.errors.append(entry)

    def get_performance_by_setup(self) -> Dict:
        """Analyze performance by trading setup"""
        setup_stats = defaultdict(lambda: {
            'wins': 0,
            'losses': 0,
            'total_profit': 0,
            'total_loss': 0,
            'trades': []
        })

        current_setup = None

        for entry in sorted(self.trades, key=lambda x: x['timestamp']):
            if entry['type'] == 'trade_entry':
                current_setup = entry.get('setup')
            elif entry['type'] == 'trade_exit' and current_setup:
                stats = setup_stats[current_setup]
                pl = entry['profit_loss']

                if entry['result'] == 'WIN':
                    stats['wins'] += 1
                    stats['total_profit'] += pl
                else:
                    stats['losses'] += 1
                    stats['total_loss'] += abs(pl)

                stats['trades'].append(entry)
                current_setup = None

        # Calculate win rates
        results = {}
        for setup, stats in setup_stats.items():
            total = stats['wins'] + stats['losses']
            results[setup] = {
                'wins': stats['wins'],
                'losses': stats['losses'],
                'win_rate': (stats['wins'] / total * 100) if total > 0 else 0,
                'total_profit': stats['total_profit'],
                'total_loss': stats['total_loss'],
                'net_pl': stats['total_profit'] - stats['total_loss'],
                'profit_factor': (stats['total_profit'] / stats['total_loss'])
                    if stats['total_loss'] > 0 else float('inf')
            }

        return results

    def get_performance_by_day(self) -> Dict:
        """Analyze performance by day of week"""
        day_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0})

        for entry in self.trades:
            if entry['type'] == 'trade_exit':
                day = entry['timestamp'].strftime('%A')
                if entry['result'] == 'WIN':
                    day_stats[day]['wins'] += 1
                else:
                    day_stats[day]['losses'] += 1
                day_stats[day]['profit'] += entry['profit_loss']

        return dict(day_stats)

    def get_performance_by_hour(self) -> Dict:
        """Analyze performance by hour of day"""
        hour_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'profit': 0})

        for entry in self.trades:
            if entry['type'] == 'trade_exit':
                hour = entry['timestamp'].hour
                if entry['result'] == 'WIN':
                    hour_stats[hour]['wins'] += 1
                else:
                    hour_stats[hour]['losses'] += 1
                hour_stats[hour]['profit'] += entry['profit_loss']

        return dict(hour_stats)

    def get_error_analysis(self) -> Dict:
        """Analyze error patterns"""
        error_counts = defaultdict(int)
        recent_errors = []

        for error in self.errors:
            # Categorize errors
            msg = error['message'].lower()
            if 'connection' in msg or 'timeout' in msg:
                error_counts['connection'] += 1
            elif 'auth' in msg or 'session' in msg:
                error_counts['authentication'] += 1
            elif 'order' in msg or 'position' in msg:
                error_counts['trading'] += 1
            else:
                error_counts['other'] += 1

            # Track recent errors (last 24h)
            if error['timestamp'] > datetime.now() - timedelta(hours=24):
                recent_errors.append(error)

        return {
            'counts': dict(error_counts),
            'recent': recent_errors[-10:],  # Last 10
            'total': sum(error_counts.values())
        }

    def get_streak_analysis(self) -> Dict:
        """Analyze winning/losing streaks"""
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        current_type = None

        for entry in sorted(self.trades, key=lambda x: x['timestamp']):
            if entry['type'] == 'trade_exit':
                if entry['result'] == 'WIN':
                    if current_type == 'WIN':
                        current_streak += 1
                    else:
                        current_streak = 1
                        current_type = 'WIN'
                    max_win_streak = max(max_win_streak, current_streak)
                else:
                    if current_type == 'LOSS':
                        current_streak += 1
                    else:
                        current_streak = 1
                        current_type = 'LOSS'
                    max_loss_streak = max(max_loss_streak, current_streak)

        return {
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak,
            'current_streak': current_streak,
            'current_type': current_type
        }

    def generate_insights(self) -> str:
        """Generate actionable insights from analysis"""
        lines = ["<b>💡 TRADING INSIGHTS</b>", ""]

        # Setup performance
        setup_perf = self.get_performance_by_setup()
        if setup_perf:
            lines.append("<b>📊 Setup Performance:</b>")

            # Sort by net P/L
            sorted_setups = sorted(
                setup_perf.items(),
                key=lambda x: x[1]['net_pl'],
                reverse=True
            )

            for setup, stats in sorted_setups[:5]:  # Top 5
                emoji = "🟢" if stats['net_pl'] > 0 else "🔴"
                lines.append(
                    f"{emoji} {setup}: {stats['win_rate']:.0f}% WR, "
                    f"{stats['net_pl']:+.2f} P/L"
                )

            lines.append("")

        # Best trading days
        day_perf = self.get_performance_by_day()
        if day_perf:
            lines.append("<b>📅 Best Days:</b>")
            sorted_days = sorted(
                day_perf.items(),
                key=lambda x: x[1]['profit'],
                reverse=True
            )
            for day, stats in sorted_days[:3]:
                total = stats['wins'] + stats['losses']
                wr = (stats['wins'] / total * 100) if total > 0 else 0
                lines.append(f"  {day}: {wr:.0f}% WR, {stats['profit']:+.2f}")

            lines.append("")

        # Best hours
        hour_perf = self.get_performance_by_hour()
        if hour_perf:
            lines.append("<b>🕐 Best Hours:</b>")
            sorted_hours = sorted(
                hour_perf.items(),
                key=lambda x: x[1]['profit'],
                reverse=True
            )
            for hour, stats in sorted_hours[:3]:
                total = stats['wins'] + stats['losses']
                wr = (stats['wins'] / total * 100) if total > 0 else 0
                lines.append(f"  {hour:02d}:00: {wr:.0f}% WR, {stats['profit']:+.2f}")

            lines.append("")

        # Streaks
        streaks = self.get_streak_analysis()
        lines.append("<b>🔥 Streaks:</b>")
        lines.append(f"  Max Win Streak: {streaks['max_win_streak']}")
        lines.append(f"  Max Loss Streak: {streaks['max_loss_streak']}")
        if streaks['current_type']:
            emoji = "🟢" if streaks['current_type'] == 'WIN' else "🔴"
            lines.append(f"  Current: {emoji} {streaks['current_streak']} {streaks['current_type']}s")

        lines.append("")

        # Errors
        errors = self.get_error_analysis()
        if errors['total'] > 0:
            lines.append("<b>⚠️ Errors (24h):</b>")
            for category, count in errors['counts'].items():
                if count > 0:
                    lines.append(f"  {category.title()}: {count}")

        # Recommendations
        lines.append("")
        lines.append("<b>💡 Recommendations:</b>")

        if setup_perf:
            best_setup = max(setup_perf.items(), key=lambda x: x[1]['net_pl'])
            worst_setup = min(setup_perf.items(), key=lambda x: x[1]['net_pl'])

            if best_setup[1]['net_pl'] > 0:
                lines.append(f"  ✅ Focus on: {best_setup[0]}")

            if worst_setup[1]['net_pl'] < 0:
                lines.append(f"  ⚠️ Review: {worst_setup[0]}")

        if day_perf:
            best_day = max(day_perf.items(), key=lambda x: x[1]['profit'])
            lines.append(f"  📅 Best results on: {best_day[0]}")

        lines.append(f"\n⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)


class TelegramNotifier:
    """Send notifications to Telegram"""

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def send(self, message: str) -> bool:
        """Send message"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False


def analyze_and_report():
    """Run analysis and send report"""
    analyzer = TradeAnalyzer()
    analyzer.load_logs()

    insights = analyzer.generate_insights()

    notifier = TelegramNotifier()
    notifier.send(insights)

    logger.info("Analysis report sent")


if __name__ == "__main__":
    import sys

    analyzer = TradeAnalyzer()
    analyzer.load_logs()

    if len(sys.argv) > 1:
        if sys.argv[1] == "insights":
            print(analyzer.generate_insights())
        elif sys.argv[1] == "send":
            analyze_and_report()
        elif sys.argv[1] == "setups":
            perf = analyzer.get_performance_by_setup()
            print(json.dumps(perf, indent=2, default=str))
        elif sys.argv[1] == "days":
            perf = analyzer.get_performance_by_day()
            print(json.dumps(perf, indent=2, default=str))
        elif sys.argv[1] == "errors":
            errors = analyzer.get_error_analysis()
            print(json.dumps(errors, indent=2, default=str))
    else:
        print("Usage: log_analyzer.py [insights|send|setups|days|errors]")
