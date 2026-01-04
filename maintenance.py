#!/usr/bin/env python3
"""
VPS Maintenance Automation
Handles log rotation, disk cleanup, updates, and health monitoring.
"""

import os
import sys
import shutil
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import requests
import psutil

# Configuration
BOT_DIR = "/home/trader"
LOG_DIR = "/home/trader"
BACKUP_DIR = "/home/trader/backups"
LOG_FILE = "/home/trader/maintenance.log"

# Retention settings
LOG_RETENTION_DAYS = 7
BACKUP_RETENTION_DAYS = 30

# Disk thresholds
DISK_WARNING_THRESHOLD = 0.80  # 80%
DISK_CRITICAL_THRESHOLD = 0.90  # 90%

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
            logger.error(f"Telegram send failed: {e}")
            return False


class LogRotator:
    """Handle log rotation and compression"""

    def __init__(self, log_dir: str = LOG_DIR):
        self.log_dir = Path(log_dir)
        self.retention_days = LOG_RETENTION_DAYS

    def get_log_files(self) -> list:
        """Get all log files"""
        log_patterns = ['*.log', '*.log.*']
        files = []
        for pattern in log_patterns:
            files.extend(self.log_dir.glob(pattern))
        return files

    def rotate_log(self, log_file: Path) -> bool:
        """Rotate a single log file"""
        if not log_file.exists():
            return False

        try:
            # Get file size
            size = log_file.stat().st_size

            # Only rotate if > 10MB
            if size < 10 * 1024 * 1024:
                return False

            # Create rotated filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            rotated_name = f"{log_file.stem}.{timestamp}{log_file.suffix}"
            rotated_path = log_file.parent / rotated_name

            # Rename current log
            shutil.move(str(log_file), str(rotated_path))

            # Create new empty log
            log_file.touch()

            # Compress rotated log
            self.compress_file(rotated_path)

            logger.info(f"Rotated: {log_file.name} ({size / 1024 / 1024:.1f}MB)")
            return True

        except Exception as e:
            logger.error(f"Failed to rotate {log_file}: {e}")
            return False

    def compress_file(self, file_path: Path) -> bool:
        """Compress a file with gzip"""
        try:
            gz_path = file_path.with_suffix(file_path.suffix + '.gz')

            with open(file_path, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove original
            file_path.unlink()
            logger.info(f"Compressed: {file_path.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to compress {file_path}: {e}")
            return False

    def cleanup_old_logs(self) -> int:
        """Remove logs older than retention period"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        removed = 0

        for log_file in self.log_dir.glob('*.log.*'):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    logger.info(f"Removed old log: {log_file.name}")
                    removed += 1
            except Exception as e:
                logger.error(f"Failed to remove {log_file}: {e}")

        return removed

    def run(self) -> dict:
        """Run full log rotation"""
        results = {
            'rotated': 0,
            'cleaned': 0,
            'errors': 0
        }

        # Rotate large logs
        for log_file in self.get_log_files():
            if log_file.suffix == '.log':
                if self.rotate_log(log_file):
                    results['rotated'] += 1

        # Clean old logs
        results['cleaned'] = self.cleanup_old_logs()

        return results


class DiskCleaner:
    """Clean up disk space"""

    def __init__(self):
        self.notifier = TelegramNotifier()

    def get_disk_usage(self) -> dict:
        """Get disk usage statistics"""
        disk = psutil.disk_usage('/')
        return {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent / 100
        }

    def check_disk_space(self) -> bool:
        """Check if disk space is okay"""
        usage = self.get_disk_usage()

        if usage['percent'] >= DISK_CRITICAL_THRESHOLD:
            self.notifier.send(
                f"🚨 <b>CRITICAL: Disk Space Low!</b>\n\n"
                f"Usage: {usage['percent']*100:.1f}%\n"
                f"Free: {usage['free']/1024/1024/1024:.1f}GB\n\n"
                f"Immediate action required!"
            )
            return False

        elif usage['percent'] >= DISK_WARNING_THRESHOLD:
            self.notifier.send(
                f"⚠️ <b>Warning: Disk Space Low</b>\n\n"
                f"Usage: {usage['percent']*100:.1f}%\n"
                f"Free: {usage['free']/1024/1024/1024:.1f}GB\n\n"
                f"Running cleanup..."
            )
            self.cleanup()
            return True

        return True

    def get_large_files(self, directory: str, min_size_mb: int = 50) -> list:
        """Find large files"""
        large_files = []
        min_size = min_size_mb * 1024 * 1024

        for root, dirs, files in os.walk(directory):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    size = os.path.getsize(filepath)
                    if size >= min_size:
                        large_files.append({
                            'path': filepath,
                            'size': size,
                            'mtime': datetime.fromtimestamp(os.path.getmtime(filepath))
                        })
                except:
                    continue

        return sorted(large_files, key=lambda x: x['size'], reverse=True)

    def cleanup_temp_files(self) -> int:
        """Clean temporary files"""
        cleaned = 0
        temp_patterns = [
            '/tmp/*',
            '/var/tmp/*',
            f'{BOT_DIR}/*.tmp',
            f'{BOT_DIR}/*.pyc',
            f'{BOT_DIR}/__pycache__/*'
        ]

        for pattern in temp_patterns:
            try:
                import glob
                for filepath in glob.glob(pattern):
                    try:
                        if os.path.isfile(filepath):
                            os.remove(filepath)
                            cleaned += 1
                        elif os.path.isdir(filepath):
                            shutil.rmtree(filepath)
                            cleaned += 1
                    except:
                        continue
            except:
                continue

        return cleaned

    def cleanup_old_backups(self) -> int:
        """Remove old backups"""
        if not os.path.exists(BACKUP_DIR):
            return 0

        cutoff = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        removed = 0

        for filepath in Path(BACKUP_DIR).glob('*'):
            try:
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                if mtime < cutoff:
                    if filepath.is_file():
                        filepath.unlink()
                    else:
                        shutil.rmtree(str(filepath))
                    logger.info(f"Removed old backup: {filepath.name}")
                    removed += 1
            except Exception as e:
                logger.error(f"Failed to remove backup {filepath}: {e}")

        return removed

    def cleanup(self) -> dict:
        """Run full cleanup"""
        results = {
            'temp_cleaned': 0,
            'backups_cleaned': 0,
            'space_freed_mb': 0
        }

        before = self.get_disk_usage()

        # Clean temp files
        results['temp_cleaned'] = self.cleanup_temp_files()

        # Clean old backups
        results['backups_cleaned'] = self.cleanup_old_backups()

        # Run log rotation
        rotator = LogRotator()
        rotator.run()

        after = self.get_disk_usage()
        results['space_freed_mb'] = (before['used'] - after['used']) / 1024 / 1024

        logger.info(f"Cleanup complete: freed {results['space_freed_mb']:.1f}MB")
        return results


class SystemUpdater:
    """Handle system updates"""

    def __init__(self):
        self.notifier = TelegramNotifier()

    def check_updates(self) -> dict:
        """Check for available updates"""
        try:
            # Update package lists
            subprocess.run(
                ['apt-get', 'update'],
                capture_output=True,
                timeout=120
            )

            # Check upgradable packages
            result = subprocess.run(
                ['apt', 'list', '--upgradable'],
                capture_output=True,
                text=True,
                timeout=60
            )

            packages = []
            for line in result.stdout.split('\n'):
                if '/' in line and 'upgradable' in line:
                    packages.append(line.split('/')[0])

            return {
                'available': len(packages),
                'packages': packages[:10]  # First 10
            }

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return {'available': 0, 'packages': [], 'error': str(e)}

    def apply_security_updates(self) -> bool:
        """Apply security updates only"""
        try:
            result = subprocess.run(
                ['unattended-upgrades', '--dry-run'],
                capture_output=True,
                timeout=300
            )

            if result.returncode == 0:
                subprocess.run(
                    ['unattended-upgrades'],
                    timeout=600
                )
                logger.info("Security updates applied")
                return True

            return False

        except Exception as e:
            logger.error(f"Security updates failed: {e}")
            return False

    def update_pip_packages(self) -> dict:
        """Update Python packages"""
        try:
            # Get outdated packages
            result = subprocess.run(
                ['pip3', 'list', '--outdated', '--format=json'],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                return {'updated': 0, 'error': 'Failed to check packages'}

            import json
            outdated = json.loads(result.stdout) if result.stdout else []

            updated = 0
            for pkg in outdated:
                name = pkg.get('name')
                # Only update specific packages
                if name in ['requests', 'psutil', 'schedule', 'psycopg2-binary']:
                    try:
                        subprocess.run(
                            ['pip3', 'install', '--upgrade', name],
                            capture_output=True,
                            timeout=120
                        )
                        updated += 1
                        logger.info(f"Updated pip package: {name}")
                    except:
                        continue

            return {'updated': updated, 'available': len(outdated)}

        except Exception as e:
            logger.error(f"Pip update failed: {e}")
            return {'updated': 0, 'error': str(e)}


class BackupManager:
    """Manage configuration and data backups"""

    def __init__(self):
        self.backup_dir = Path(BACKUP_DIR)
        self.backup_dir.mkdir(exist_ok=True)

    def backup_configs(self) -> bool:
        """Backup configuration files"""
        configs = [
            'supervisor_config.json',
            'capital_both_accounts.json',
            'telegram_config.json',
            'ultimate_trading_system.py'
        ]

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"config_backup_{timestamp}"
        backup_path.mkdir(exist_ok=True)

        backed_up = 0
        for config in configs:
            src = Path(BOT_DIR) / config
            if src.exists():
                shutil.copy2(str(src), str(backup_path / config))
                backed_up += 1

        if backed_up > 0:
            # Compress backup
            shutil.make_archive(
                str(backup_path),
                'gztar',
                str(backup_path)
            )
            shutil.rmtree(str(backup_path))
            logger.info(f"Config backup created: {backup_path}.tar.gz")
            return True

        return False

    def list_backups(self) -> list:
        """List available backups"""
        backups = []
        for backup in self.backup_dir.glob('*.tar.gz'):
            backups.append({
                'name': backup.name,
                'size': backup.stat().st_size,
                'date': datetime.fromtimestamp(backup.stat().st_mtime)
            })
        return sorted(backups, key=lambda x: x['date'], reverse=True)


class HealthChecker:
    """System health checks"""

    def __init__(self):
        self.notifier = TelegramNotifier()

    def check_all(self) -> dict:
        """Run all health checks"""
        results = {
            'cpu': self.check_cpu(),
            'memory': self.check_memory(),
            'disk': self.check_disk(),
            'network': self.check_network(),
            'processes': self.check_processes()
        }

        # Send alert if any critical issues
        critical = [k for k, v in results.items() if v.get('status') == 'critical']
        if critical:
            self.notifier.send(
                f"🚨 <b>System Health Alert</b>\n\n"
                f"Critical issues: {', '.join(critical)}\n\n"
                f"Check system immediately!"
            )

        return results

    def check_cpu(self) -> dict:
        """Check CPU usage"""
        cpu_percent = psutil.cpu_percent(interval=1)
        status = 'ok' if cpu_percent < 80 else 'warning' if cpu_percent < 95 else 'critical'
        return {
            'usage': cpu_percent,
            'status': status
        }

    def check_memory(self) -> dict:
        """Check memory usage"""
        mem = psutil.virtual_memory()
        status = 'ok' if mem.percent < 80 else 'warning' if mem.percent < 95 else 'critical'
        return {
            'usage': mem.percent,
            'available_gb': mem.available / 1024 / 1024 / 1024,
            'status': status
        }

    def check_disk(self) -> dict:
        """Check disk usage"""
        disk = psutil.disk_usage('/')
        status = 'ok' if disk.percent < 80 else 'warning' if disk.percent < 95 else 'critical'
        return {
            'usage': disk.percent,
            'free_gb': disk.free / 1024 / 1024 / 1024,
            'status': status
        }

    def check_network(self) -> dict:
        """Check network connectivity"""
        try:
            response = requests.get('https://api.telegram.org', timeout=5)
            return {
                'status': 'ok' if response.status_code == 200 else 'warning',
                'latency_ms': response.elapsed.total_seconds() * 1000
            }
        except:
            return {'status': 'critical', 'error': 'No connectivity'}

    def check_processes(self) -> dict:
        """Check bot processes"""
        bots_running = 0
        supervisor_running = False

        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'ultimate_trading_system' in cmdline:
                    bots_running += 1
                if 'bot_supervisor' in cmdline:
                    supervisor_running = True
            except:
                continue

        status = 'ok' if bots_running >= 2 and supervisor_running else 'warning'
        return {
            'bots_running': bots_running,
            'supervisor_running': supervisor_running,
            'status': status
        }


def run_maintenance():
    """Run full maintenance routine"""
    logger.info("Starting maintenance routine...")
    notifier = TelegramNotifier()

    results = {}

    # Health check
    health = HealthChecker()
    results['health'] = health.check_all()

    # Log rotation
    rotator = LogRotator()
    results['logs'] = rotator.run()

    # Disk cleanup
    cleaner = DiskCleaner()
    cleaner.check_disk_space()
    results['cleanup'] = cleaner.cleanup()

    # Backup
    backup = BackupManager()
    results['backup'] = backup.backup_configs()

    # Summary
    logger.info("Maintenance complete")
    logger.info(f"Results: {results}")

    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "full":
            run_maintenance()
        elif cmd == "health":
            checker = HealthChecker()
            print(checker.check_all())
        elif cmd == "rotate":
            rotator = LogRotator()
            print(rotator.run())
        elif cmd == "cleanup":
            cleaner = DiskCleaner()
            print(cleaner.cleanup())
        elif cmd == "backup":
            backup = BackupManager()
            print(backup.backup_configs())
        elif cmd == "disk":
            cleaner = DiskCleaner()
            print(cleaner.get_disk_usage())
        else:
            print("Usage: maintenance.py [full|health|rotate|cleanup|backup|disk]")
    else:
        run_maintenance()
