#!/usr/bin/env python3
"""
Feedback Loop Controller
The core of the self-learning system - updates signal weights,
adjusts parameters, and promotes/demotes setups based on performance
"""

import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import logging

sys.path.insert(0, '/home/user/claudemaker')

from services.shared.config import config, ConfigManager
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notifier
from services.learning.trade_analyzer import TradeAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/user/claudemaker/logs/learning/feedback.log')
    ]
)
logger = logging.getLogger('feedback_loop')


class FeedbackLoopController:
    """
    Manages the self-reinforcing learning loop:
    1. Analyze trade outcomes
    2. Update setup weights
    3. Adjust risk parameters
    4. Enable/disable setups
    5. Log all changes for auditability
    """

    def __init__(self):
        self.analyzer = TradeAnalyzer()
        self.config_manager = ConfigManager()

        # Thresholds for decisions
        self.min_trades_for_decision = 20
        self.promotion_threshold = 0.20  # 20% improvement
        self.demotion_threshold = -0.20  # 20% decline
        self.disable_threshold = 0.30  # 30% win rate minimum
        self.reenable_improvement = 0.15  # 15% improvement to re-enable

        # Weight adjustment factors
        self.weight_increase = 0.1  # Increase by 10%
        self.weight_decrease = 0.1  # Decrease by 10%
        self.min_weight = 0.3
        self.max_weight = 2.0

        # Current state
        self.setup_weights: Dict[str, float] = {}
        self.disabled_setups: set = set()
        self.last_update: datetime = None

        self._load_state()

    def _load_state(self):
        """Load current state from database"""
        # Load setup weights
        results = db.fetch_all("""
            SELECT setup_name, weight, is_active
            FROM setup_performance
            WHERE period_end >= NOW() - INTERVAL '7 days'
        """)

        for row in results:
            self.setup_weights[row['setup_name']] = float(row.get('weight', 1.0))
            if not row.get('is_active', True):
                self.disabled_setups.add(row['setup_name'])

        logger.info(f"Loaded {len(self.setup_weights)} setup weights")

    def run_feedback_cycle(self) -> Dict:
        """Run a complete feedback cycle"""
        logger.info("Running feedback cycle...")

        # Get current performance
        analysis = self.analyzer.run_daily_analysis()

        # Compare to historical baseline
        comparison = self.analyzer.compare_periods(7, 7)

        changes = {
            'timestamp': datetime.now().isoformat(),
            'weight_updates': [],
            'status_changes': [],
            'parameter_updates': [],
            'recommendations': []
        }

        # Process each setup
        for setup_data in analysis.get('setup_performance', []):
            setup_changes = self._evaluate_setup(setup_data, comparison)
            if setup_changes:
                changes['weight_updates'].extend(setup_changes.get('weight_updates', []))
                changes['status_changes'].extend(setup_changes.get('status_changes', []))

        # Adjust global parameters if needed
        param_changes = self._adjust_risk_parameters(analysis, comparison)
        changes['parameter_updates'] = param_changes

        # Generate recommendations
        changes['recommendations'] = analysis.get('recommendations', [])

        # Apply changes
        self._apply_changes(changes)

        # Store and notify
        self._log_changes(changes)
        self._send_update_notification(changes)

        self.last_update = datetime.now()
        return changes

    def _evaluate_setup(self, setup_data: Dict, comparison: Dict) -> Optional[Dict]:
        """Evaluate a single setup and determine changes"""
        setup_name = setup_data.get('setup', '')
        win_rate = setup_data.get('win_rate', 0)
        profit_factor = setup_data.get('profit_factor', 0)
        trades = setup_data.get('trades', 0)

        if trades < self.min_trades_for_decision:
            return None

        changes = {'weight_updates': [], 'status_changes': []}
        current_weight = self.setup_weights.get(setup_name, 1.0)
        is_disabled = setup_name in self.disabled_setups

        # Calculate performance score
        # Higher is better: combines win rate and profit factor
        score = (win_rate * 0.4) + (min(profit_factor / 3, 1) * 0.6)

        # Check if should disable
        if win_rate < self.disable_threshold and not is_disabled:
            self.disabled_setups.add(setup_name)
            changes['status_changes'].append({
                'setup': setup_name,
                'action': 'DISABLED',
                'reason': f'Win rate too low: {win_rate:.1%}'
            })
            logger.warning(f"Disabling setup '{setup_name}' - WR={win_rate:.1%}")

        # Check if should re-enable
        elif is_disabled and win_rate > self.disable_threshold + self.reenable_improvement:
            self.disabled_setups.discard(setup_name)
            changes['status_changes'].append({
                'setup': setup_name,
                'action': 'RE-ENABLED',
                'reason': f'Win rate improved: {win_rate:.1%}'
            })
            logger.info(f"Re-enabling setup '{setup_name}' - WR={win_rate:.1%}")

        # Adjust weight based on performance
        if score > 0.6:  # Good performance
            new_weight = min(current_weight * (1 + self.weight_increase), self.max_weight)
            if new_weight != current_weight:
                changes['weight_updates'].append({
                    'setup': setup_name,
                    'old_weight': current_weight,
                    'new_weight': round(new_weight, 2),
                    'reason': f'Strong performance (score={score:.2f})'
                })
                self.setup_weights[setup_name] = new_weight

        elif score < 0.4:  # Poor performance
            new_weight = max(current_weight * (1 - self.weight_decrease), self.min_weight)
            if new_weight != current_weight:
                changes['weight_updates'].append({
                    'setup': setup_name,
                    'old_weight': current_weight,
                    'new_weight': round(new_weight, 2),
                    'reason': f'Weak performance (score={score:.2f})'
                })
                self.setup_weights[setup_name] = new_weight

        return changes if (changes['weight_updates'] or changes['status_changes']) else None

    def _adjust_risk_parameters(self, analysis: Dict, comparison: Dict) -> List[Dict]:
        """Adjust global risk parameters based on performance"""
        param_changes = []

        # Get overall performance
        bot_perf = analysis.get('bot_performance', [])
        streaks = analysis.get('streak_analysis', {})

        # Calculate overall win rate
        total_trades = sum(b.get('trades', 0) for b in bot_perf)
        total_wins = sum(b.get('trades', 0) * b.get('win_rate', 0) for b in bot_perf)
        overall_wr = total_wins / total_trades if total_trades > 0 else 0

        # Check period comparison
        wr_change = comparison.get('win_rate_change', 0)
        r_change = comparison.get('avg_r_change', 0)

        # If performance degrading, reduce risk
        if wr_change < -0.10 or r_change < -1.0:
            current_risk = self.config_manager.get('risk_management.default_risk_pct', 0.03)
            new_risk = max(0.01, current_risk * 0.8)  # Reduce by 20%

            param_changes.append({
                'parameter': 'default_risk_pct',
                'old_value': current_risk,
                'new_value': round(new_risk, 3),
                'reason': f'Performance declining (WR: {wr_change:+.1%}, R: {r_change:+.1f})'
            })

        # If performance improving, can increase risk (carefully)
        elif wr_change > 0.10 and r_change > 1.0:
            current_risk = self.config_manager.get('risk_management.default_risk_pct', 0.03)
            max_risk = self.config_manager.get('risk_management.max_single_trade_risk', 0.05)
            new_risk = min(max_risk, current_risk * 1.1)  # Increase by 10%

            if new_risk > current_risk:
                param_changes.append({
                    'parameter': 'default_risk_pct',
                    'old_value': current_risk,
                    'new_value': round(new_risk, 3),
                    'reason': f'Performance improving (WR: {wr_change:+.1%}, R: {r_change:+.1f})'
                })

        # Check losing streaks
        if streaks.get('current_type') == 'loss' and streaks.get('current_streak', 0) >= 5:
            param_changes.append({
                'parameter': 'trading_pause',
                'old_value': False,
                'new_value': True,
                'reason': f"{streaks['current_streak']} consecutive losses"
            })

        return param_changes

    def _apply_changes(self, changes: Dict):
        """Apply the determined changes"""
        # Update setup weights in database
        for weight_change in changes.get('weight_updates', []):
            db.execute("""
                UPDATE setup_performance
                SET weight = %s, updated_at = NOW()
                WHERE setup_name = %s
            """, (weight_change['new_weight'], weight_change['setup']))

        # Update setup status
        for status_change in changes.get('status_changes', []):
            is_active = status_change['action'] != 'DISABLED'
            db.execute("""
                UPDATE setup_performance
                SET is_active = %s, updated_at = NOW()
                WHERE setup_name = %s
            """, (is_active, status_change['setup']))

        # Apply parameter changes
        for param_change in changes.get('parameter_updates', []):
            param = param_change['parameter']
            value = param_change['new_value']

            if param == 'default_risk_pct':
                self.config_manager.set('risk_management.default_risk_pct', value)
            elif param == 'trading_pause':
                # Publish pause command to all bots
                if value:
                    mq.publish('control', {'action': 'pause', 'reason': param_change['reason']})

        # Save config if changed
        if changes.get('parameter_updates'):
            self.config_manager.save()

    def _log_changes(self, changes: Dict):
        """Log all changes for audit trail"""
        log_entry = {
            'timestamp': changes['timestamp'],
            'changes': changes
        }

        db.execute("""
            INSERT INTO system_state (service_name, status, config, updated_at)
            VALUES ('feedback_loop', 'update', %s, NOW())
            ON CONFLICT (service_name) DO UPDATE
            SET status = 'update', config = EXCLUDED.config, updated_at = NOW()
        """, (json.dumps(log_entry),))

    def _send_update_notification(self, changes: Dict):
        """Send notification about changes"""
        if not any([
            changes.get('weight_updates'),
            changes.get('status_changes'),
            changes.get('parameter_updates')
        ]):
            return  # No changes to report

        msg = "🤖 <b>SELF-LEARNING UPDATE</b>\n\n"

        if changes.get('weight_updates'):
            msg += "<b>Weight Adjustments:</b>\n"
            for wu in changes['weight_updates'][:5]:
                direction = "📈" if wu['new_weight'] > wu['old_weight'] else "📉"
                msg += f"{direction} {wu['setup']}: {wu['old_weight']} → {wu['new_weight']}\n"
            msg += "\n"

        if changes.get('status_changes'):
            msg += "<b>Status Changes:</b>\n"
            for sc in changes['status_changes']:
                emoji = "🔴" if sc['action'] == 'DISABLED' else "🟢"
                msg += f"{emoji} {sc['setup']}: {sc['action']}\n"
            msg += "\n"

        if changes.get('parameter_updates'):
            msg += "<b>Parameter Updates:</b>\n"
            for pu in changes['parameter_updates']:
                msg += f"• {pu['parameter']}: {pu['old_value']} → {pu['new_value']}\n"

        notifier.send_message(msg)

    def get_setup_weight(self, setup_name: str) -> float:
        """Get current weight for a setup"""
        return self.setup_weights.get(setup_name, 1.0)

    def is_setup_enabled(self, setup_name: str) -> bool:
        """Check if setup is enabled"""
        return setup_name not in self.disabled_setups


class FeedbackService:
    def __init__(self):
        self.controller = FeedbackLoopController()
        self.running = False
        self.update_hour = 20  # 8 PM UTC

    def start(self):
        logger.info("Starting Feedback Loop Service...")
        self.running = True
        last_run = None

        while self.running:
            try:
                now = datetime.now()

                # Run at specified hour
                if now.hour == self.update_hour:
                    if last_run is None or last_run.date() < now.date():
                        changes = self.controller.run_feedback_cycle()
                        last_run = now

                        weight_count = len(changes.get('weight_updates', []))
                        status_count = len(changes.get('status_changes', []))
                        logger.info(f"Feedback cycle complete: {weight_count} weight updates, {status_count} status changes")

                mq.send_heartbeat('feedback_loop', 'running')
                time.sleep(300)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"Feedback loop error: {e}")
                time.sleep(60)

    def stop(self):
        self.running = False


def main():
    service = FeedbackService()

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
