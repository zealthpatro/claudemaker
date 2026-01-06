"""
Configuration Manager
Loads and provides access to all configuration settings
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Singleton configuration manager for the trading system"""

    _instance = None
    _config: Dict[str, Any] = {}
    _config_path: Path = None
    _last_loaded: datetime = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self.load()

    def load(self, config_path: Optional[str] = None) -> None:
        """Load configuration from JSON file"""
        if config_path:
            self._config_path = Path(config_path)
        else:
            # Default paths to check
            paths = [
                Path("/home/user/claudemaker/config/main_config.json"),
                Path("/home/trader/algo_trading/config/main_config.json"),
                Path("config/main_config.json"),
            ]
            for p in paths:
                if p.exists():
                    self._config_path = p
                    break

        if self._config_path and self._config_path.exists():
            with open(self._config_path, 'r') as f:
                self._config = json.load(f)
            self._last_loaded = datetime.now()
            logger.info(f"Configuration loaded from {self._config_path}")
        else:
            logger.warning("No configuration file found, using defaults")
            self._config = self._get_defaults()

    def reload(self) -> None:
        """Reload configuration from file"""
        self.load(str(self._config_path) if self._config_path else None)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'database.host')"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value (in memory only)"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def save(self) -> None:
        """Save current configuration to file"""
        if self._config_path:
            with open(self._config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Configuration saved to {self._config_path}")

    @property
    def database(self) -> Dict[str, Any]:
        """Database configuration"""
        return self._config.get('database', {})

    @property
    def redis(self) -> Dict[str, Any]:
        """Redis configuration"""
        return self._config.get('redis', {})

    @property
    def capital_com(self) -> Dict[str, Any]:
        """Capital.com API configuration"""
        return self._config.get('capital_com', {})

    @property
    def telegram(self) -> Dict[str, Any]:
        """Telegram configuration"""
        return self._config.get('telegram', {})

    @property
    def symbols(self) -> Dict[str, Any]:
        """Trading symbols configuration"""
        return self._config.get('symbols', {})

    @property
    def timeframes(self) -> Dict[str, Any]:
        """Timeframe configurations"""
        return self._config.get('timeframes', {})

    @property
    def bots(self) -> Dict[str, Any]:
        """Bot configurations"""
        return self._config.get('bots', {})

    @property
    def risk_management(self) -> Dict[str, Any]:
        """Risk management settings"""
        return self._config.get('risk_management', {})

    @property
    def setups(self) -> Dict[str, Any]:
        """Trading setups by tier"""
        return self._config.get('setups', {})

    @property
    def accounts(self) -> Dict[str, Any]:
        """Trading accounts"""
        return self._config.get('accounts', {})

    def get_enabled_symbols(self) -> list:
        """Get list of enabled symbols"""
        return [s for s, cfg in self.symbols.items() if cfg.get('enabled', True)]

    def get_enabled_bots(self) -> list:
        """Get list of enabled bots"""
        return [b for b, cfg in self.bots.items() if cfg.get('enabled', True)]

    def get_bot_config(self, bot_name: str) -> Dict[str, Any]:
        """Get configuration for specific bot"""
        return self.bots.get(bot_name, {})

    def get_symbol_config(self, symbol: str) -> Dict[str, Any]:
        """Get configuration for specific symbol"""
        return self.symbols.get(symbol, {})

    def get_timeframe_config(self, timeframe: str) -> Dict[str, Any]:
        """Get configuration for specific timeframe"""
        return self.timeframes.get(timeframe, {})

    def get_all_setups(self) -> list:
        """Get all trading setups as flat list"""
        all_setups = []
        for tier, setups in self.setups.items():
            for setup in setups:
                setup_copy = setup.copy()
                setup_copy['tier'] = tier.replace('tier_', '').upper()
                all_setups.append(setup_copy)
        return all_setups

    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "database": {
                "host": "localhost",
                "port": 5432,
                "dbname": "trading_bot",
                "user": "trader",
                "password": ""
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": 0
            },
            "symbols": {
                "XAUUSD": {"enabled": True, "pip_value": 0.01},
                "XAGUSD": {"enabled": True, "pip_value": 0.001}
            },
            "timeframes": {
                "MINUTE": {"seconds": 60},
                "MINUTE_5": {"seconds": 300},
                "MINUTE_15": {"seconds": 900},
                "HOUR": {"seconds": 3600},
                "HOUR_4": {"seconds": 14400},
                "DAY": {"seconds": 86400}
            }
        }


# Global config instance
config = ConfigManager()
