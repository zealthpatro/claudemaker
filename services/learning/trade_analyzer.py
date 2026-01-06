#!/usr/bin/env python3
"""
Trade Analyzer
Analyzes trade outcomes and identifies patterns in performance
"""

import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import json
import logging

sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/learning/analyzer.log')
    ]
)
logger = logging.getLogger('trade_analyzer')


class TradeAnalyzer:
    """
    Analyzes trade performance to identify:
    - Best/worst setups
    - Best/worst times and days
    - Performance by market conditions
    - Degrading and improving setups
    """

    def __init__(self):
        self.analysis_window_days = 30
        self.min_trades_for_analysis = 10
        self.degradation_threshold = -0.20  # 20% decline triggers alert
        self.improvement_threshold = 0.20  # 20% improvement noted

    def run_daily_analysis(self) -> Dict:
        """Run comprehensive daily analysis"""
        logger.info("Running daily trade analysis...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'setup_performance': self.analyze_setups(),
            'time_performance': self.analyze_by_time(),
            'bot_performance': self.analyze_by_bot(),
            'streak_analysis': self.analyze_streaks(),
            'recommendations': []
        }

        # Generate recommendations
        results['recommendations'] = self._generate_recommendations(results)

        # Store analysis results
        self._store_analysis(results)

        # Check for alerts
        self._check_for_alerts(results)

        logger.info("Daily analysis complete")
        return results

    def analyze_setups(self) -> List[Dict]:
        """Analyze performance by setup"""
        trades = self._get_recent_trades()

        if not trades:
            return []

        # Group by setup
        setup_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'losses': 0,
            'total_r': 0, 'total_pnl': 0,
            'win_r': 0, 'loss_r': 0
        })

        for trade in trades:
            setup = trade.get('setup_name', 'unknown')
            pnl = float(trade.get('pnl', 0) or 0)
            pnl_r = float(trade.get('pnl_r', 0) or 0)

            stats = setup_stats[setup]
            stats['trades'] += 1
            stats['total_r'] += pnl_r
            stats['total_pnl'] += pnl

            if pnl > 0:
                stats['wins'] += 1
                stats['win_r'] += pnl_r
            else:
                stats['losses'] += 1
                stats['loss_r'] += abs(pnl_r)

        # Calculate metrics
        results = []
        for setup, stats in setup_stats.items():
            if stats['trades'] >= self.min_trades_for_analysis:
                win_rate = stats['wins'] / stats['trades'] if stats['trades'] > 0 else 0
                avg_r = stats['total_r'] / stats['trades'] if stats['trades'] > 0 else 0
                avg_win = stats['win_r'] / stats['wins'] if stats['wins'] > 0 else 0
                avg_loss = stats['loss_r'] / stats['losses'] if stats['losses'] > 0 else 0
                profit_factor = stats['win_r'] / stats['loss_r'] if stats['loss_r'] > 0 else float('inf')

                results.append({
                    'setup': setup,
                    'trades': stats['trades'],
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'win_rate': round(win_rate, 3),
                    'avg_r': round(avg_r, 2),
                    'avg_win_r': round(avg_win, 2),
                    'avg_loss_r': round(avg_loss, 2),
                    'profit_factor': round(profit_factor, 2),
                    'total_r': round(stats['total_r'], 2),
                    'total_pnl': round(stats['total_pnl'], 2)
                })

        # Sort by profit factor
        results.sort(key=lambda x: x['profit_factor'], reverse=True)
        return results

    def analyze_by_time(self) -> Dict:
        """Analyze performance by day and hour"""
        trades = self._get_recent_trades()

        if not trades:
            return {'by_day': [], 'by_hour': []}

        # By day of week
        day_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_r': 0})
        hour_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_r': 0})

        for trade in trades:
            opened_at = trade.get('opened_at')
            if not opened_at:
                continue

            day = opened_at.strftime('%A')
            hour = opened_at.hour
            pnl = float(trade.get('pnl', 0) or 0)
            pnl_r = float(trade.get('pnl_r', 0) or 0)

            day_stats[day]['trades'] += 1
            day_stats[day]['total_r'] += pnl_r
            if pnl > 0:
                day_stats[day]['wins'] += 1

            hour_stats[hour]['trades'] += 1
            hour_stats[hour]['total_r'] += pnl_r
            if pnl > 0:
                hour_stats[hour]['wins'] += 1

        # Convert to lists
        by_day = []
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            stats = day_stats[day]
            if stats['trades'] > 0:
                by_day.append({
                    'day': day,
                    'trades': stats['trades'],
                    'win_rate': round(stats['wins'] / stats['trades'], 3),
                    'total_r': round(stats['total_r'], 2)
                })

        by_hour = []
        for hour in sorted(hour_stats.keys()):
            stats = hour_stats[hour]
            if stats['trades'] > 0:
                by_hour.append({
                    'hour': hour,
                    'trades': stats['trades'],
                    'win_rate': round(stats['wins'] / stats['trades'], 3),
                    'total_r': round(stats['total_r'], 2)
                })

        return {'by_day': by_day, 'by_hour': by_hour}

    def analyze_by_bot(self) -> List[Dict]:
        """Analyze performance by bot type"""
        trades = self._get_recent_trades()

        if not trades:
            return []

        bot_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'total_r': 0, 'total_pnl': 0
        })

        for trade in trades:
            bot = trade.get('bot_type', 'unknown')
            pnl = float(trade.get('pnl', 0) or 0)
            pnl_r = float(trade.get('pnl_r', 0) or 0)

            bot_stats[bot]['trades'] += 1
            bot_stats[bot]['total_r'] += pnl_r
            bot_stats[bot]['total_pnl'] += pnl
            if pnl > 0:
                bot_stats[bot]['wins'] += 1

        results = []
        for bot, stats in bot_stats.items():
            if stats['trades'] > 0:
                results.append({
                    'bot': bot,
                    'trades': stats['trades'],
                    'win_rate': round(stats['wins'] / stats['trades'], 3),
                    'avg_r': round(stats['total_r'] / stats['trades'], 2),
                    'total_r': round(stats['total_r'], 2),
                    'total_pnl': round(stats['total_pnl'], 2)
                })

        results.sort(key=lambda x: x['total_r'], reverse=True)
        return results

    def analyze_streaks(self) -> Dict:
        """Analyze winning and losing streaks"""
        trades = self._get_recent_trades()

        if not trades:
            return {'max_win_streak': 0, 'max_loss_streak': 0, 'current_streak': 0}

        # Sort by close time
        trades = sorted(trades, key=lambda x: x.get('closed_at') or datetime.min)

        max_win = 0
        max_loss = 0
        current = 0
        current_type = None

        for trade in trades:
            pnl = float(trade.get('pnl', 0) or 0)

            if pnl > 0:
                if current_type == 'win':
                    current += 1
                else:
                    current = 1
                    current_type = 'win'
                max_win = max(max_win, current)
            else:
                if current_type == 'loss':
                    current += 1
                else:
                    current = 1
                    current_type = 'loss'
                max_loss = max(max_loss, current)

        return {
            'max_win_streak': max_win,
            'max_loss_streak': max_loss,
            'current_streak': current,
            'current_type': current_type
        }

    def compare_periods(self, current_days: int = 7, previous_days: int = 7) -> Dict:
        """Compare recent period to previous period"""
        now = datetime.now()
        current_start = now - timedelta(days=current_days)
        previous_start = current_start - timedelta(days=previous_days)

        # Get trades for both periods
        current_trades = db.fetch_all("""
            SELECT s.setup_name, t.pnl, t.pnl_r
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.status = 'closed' AND t.closed_at >= %s
        """, (current_start,))

        previous_trades = db.fetch_all("""
            SELECT s.setup_name, t.pnl, t.pnl_r
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.status = 'closed' AND t.closed_at >= %s AND t.closed_at < %s
        """, (previous_start, current_start))

        def calc_stats(trades):
            if not trades:
                return {'trades': 0, 'win_rate': 0, 'avg_r': 0}
            wins = sum(1 for t in trades if float(t.get('pnl', 0) or 0) > 0)
            total_r = sum(float(t.get('pnl_r', 0) or 0) for t in trades)
            return {
                'trades': len(trades),
                'win_rate': wins / len(trades) if trades else 0,
                'avg_r': total_r / len(trades) if trades else 0
            }

        current_stats = calc_stats(current_trades)
        previous_stats = calc_stats(previous_trades)

        # Calculate changes
        if previous_stats['trades'] > 0:
            wr_change = current_stats['win_rate'] - previous_stats['win_rate']
            r_change = current_stats['avg_r'] - previous_stats['avg_r']
        else:
            wr_change = 0
            r_change = 0

        return {
            'current': current_stats,
            'previous': previous_stats,
            'win_rate_change': round(wr_change, 3),
            'avg_r_change': round(r_change, 2)
        }

    def _get_recent_trades(self) -> List[Dict]:
        """Get trades from analysis window"""
        return db.fetch_all("""
            SELECT t.*, s.setup_name, s.timeframe
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.status = 'closed'
              AND t.closed_at >= NOW() - INTERVAL '%s days'
            ORDER BY t.closed_at DESC
        """, (self.analysis_window_days,))

    def _generate_recommendations(self, results: Dict) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        # Setup recommendations
        setup_perf = results.get('setup_performance', [])
        if setup_perf:
            best = setup_perf[0]
            worst = setup_perf[-1]

            if best['profit_factor'] > 2.0:
                recommendations.append(
                    f"INCREASE weight for '{best['setup']}' - "
                    f"PF={best['profit_factor']}, WR={best['win_rate']:.1%}"
                )

            if worst['profit_factor'] < 1.0 and worst['trades'] >= 20:
                recommendations.append(
                    f"CONSIDER DISABLING '{worst['setup']}' - "
                    f"PF={worst['profit_factor']}, losing setup"
                )

        # Time recommendations
        time_perf = results.get('time_performance', {})
        by_day = time_perf.get('by_day', [])
        if by_day:
            best_day = max(by_day, key=lambda x: x['total_r'])
            worst_day = min(by_day, key=lambda x: x['total_r'])

            if best_day['total_r'] > worst_day['total_r'] * 2:
                recommendations.append(
                    f"FOCUS trading on {best_day['day']} (+{best_day['total_r']:.1f}R), "
                    f"reduce {worst_day['day']} ({worst_day['total_r']:.1f}R)"
                )

        # Streak alerts
        streaks = results.get('streak_analysis', {})
        if streaks.get('current_type') == 'loss' and streaks.get('current_streak', 0) >= 4:
            recommendations.append(
                f"CAUTION: {streaks['current_streak']} consecutive losses - "
                "consider reducing position sizes"
            )

        return recommendations

    def _store_analysis(self, results: Dict):
        """Store analysis results in database"""
        db.execute("""
            INSERT INTO setup_performance (
                setup_name, symbol_id, timeframe, period_start, period_end,
                total_trades, wins, losses, win_rate, avg_r, profit_factor, updated_at
            )
            SELECT
                %(setup)s, 1, 'ALL', NOW() - INTERVAL '30 days', NOW(),
                %(trades)s, %(wins)s, %(losses)s, %(win_rate)s, %(avg_r)s, %(profit_factor)s, NOW()
            ON CONFLICT DO NOTHING
        """, results.get('setup_performance', [{}])[0] if results.get('setup_performance') else {
            'setup': 'none', 'trades': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0, 'avg_r': 0, 'profit_factor': 0
        })

    def _check_for_alerts(self, results: Dict):
        """Send alerts for significant findings"""
        recommendations = results.get('recommendations', [])

        if recommendations:
            msg = "TRADE ANALYSIS RECOMMENDATIONS:\n\n"
            for i, rec in enumerate(recommendations, 1):
                msg += f"{i}. {rec}\n"

            notifier.send_message(msg)


class AnalyzerService:
    def __init__(self):
        self.analyzer = TradeAnalyzer()
        self.running = False
        self.analysis_hour = 19  # Run at 7 PM UTC

    def start(self):
        logger.info("Starting Trade Analyzer Service...")
        self.running = True
        last_analysis = None

        while self.running:
            try:
                now = datetime.now()

                # Run daily at specified hour
                if now.hour == self.analysis_hour:
                    if last_analysis is None or last_analysis.date() < now.date():
                        results = self.analyzer.run_daily_analysis()
                        last_analysis = now
                        logger.info(f"Analysis complete: {len(results.get('setup_performance', []))} setups analyzed")

                # Heartbeat
                mq.send_heartbeat('trade_analyzer', 'running')
                time.sleep(300)  # Check every 5 minutes

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Analysis error: {e}")
                time.sleep(60)

    def stop(self):
        self.running = False


def main():
    service = AnalyzerService()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
