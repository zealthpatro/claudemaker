#!/usr/bin/env python3
"""
Trading System Installer - Run this on the target VM
Creates all necessary service files, configs, and scripts
"""

import os
import sys

BASE_DIR = "/home/trader/algo_trading"

def create_file(path, content):
    """Create file with content"""
    full_path = os.path.join(BASE_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)
    print(f"Created: {path}")

def install():
    print("=== Trading System Installer ===\n")

    # Create directory structure
    dirs = ['services/shared', 'services/data', 'services/signals',
            'services/bots', 'services/learning', 'config', 'systemd',
            'scripts', 'logs/data', 'logs/signals', 'logs/bots', 'logs/learning', 'models']
    for d in dirs:
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)
    print("Directories created\n")

    # =================================================================
    # CONFIG - main_config.json (user should modify credentials)
    # =================================================================
    create_file('config/main_config.json', '''{
  "capital_com": {
    "api_key": "3F3RHbKsBbivSLYe",
    "identifier": "saurav.patr@gmail.com",
    "password": "Cl@ud#123",
    "base_url": "https://demo-api-capital.backend-capital.com"
  },
  "telegram": {
    "token": "8376345331:AAHWoZzkqT26cyeRPGa8MfcaVZWvTcan9lU",
    "chat_id": "7831118282"
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "dbname": "trading_bot",
    "user": "trader",
    "password": "TradingBot2026Secure!"
  },
  "redis": {
    "host": "localhost",
    "port": 6379,
    "db": 0
  },
  "symbols": {
    "XAUUSD": {
      "enabled": true,
      "pip_value": 0.01,
      "min_lot": 0.01,
      "description": "Gold"
    },
    "XAGUSD": {
      "enabled": true,
      "pip_value": 0.001,
      "min_lot": 0.01,
      "description": "Silver"
    }
  },
  "timeframes": {
    "MINUTE": {"seconds": 60, "candles_per_day": 1440},
    "MINUTE_5": {"seconds": 300, "candles_per_day": 288},
    "MINUTE_15": {"seconds": 900, "candles_per_day": 96},
    "HOUR": {"seconds": 3600, "candles_per_day": 24},
    "HOUR_4": {"seconds": 14400, "candles_per_day": 6},
    "DAY": {"seconds": 86400, "candles_per_day": 1}
  },
  "bots": {
    "scalper": {
      "enabled": true,
      "risk_percent": 1.0,
      "max_trades_per_day": 20,
      "timeframes": ["MINUTE", "MINUTE_5"],
      "min_confidence": 70,
      "target_r": 5.0
    },
    "day_trader": {
      "enabled": true,
      "risk_percent": 1.5,
      "max_trades_per_day": 8,
      "timeframes": ["MINUTE_15", "HOUR"],
      "min_confidence": 65,
      "target_r": 3.0
    },
    "swing": {
      "enabled": true,
      "risk_percent": 2.0,
      "max_trades_per_day": 3,
      "timeframes": ["HOUR", "HOUR_4"],
      "min_confidence": 60,
      "target_r": 4.0
    },
    "position": {
      "enabled": true,
      "risk_percent": 2.0,
      "max_trades_per_day": 1,
      "timeframes": ["HOUR_4", "DAY"],
      "min_confidence": 75,
      "target_r": 6.0
    },
    "sniper": {
      "enabled": true,
      "risk_percent": 3.0,
      "max_trades_per_day": 5,
      "timeframes": ["MINUTE", "MINUTE_5", "MINUTE_15"],
      "min_confidence": 85,
      "target_r": 20.0
    }
  },
  "risk_management": {
    "max_daily_loss_percent": 5.0,
    "max_drawdown_percent": 10.0,
    "max_correlation": 0.7,
    "max_open_trades": 5
  }
}''')

    # =================================================================
    # SHARED MODULES
    # =================================================================
    create_file('services/__init__.py', '')
    create_file('services/shared/__init__.py', '''from .config import config, ConfigManager
from .database import db, DatabaseManager
from .message_queue import mq, MessageQueue
from .capital_api import CapitalAPI
from .indicators import TechnicalIndicators
from .notifications import notify, TelegramNotifier
''')

    # CONFIG MANAGER
    create_file('services/shared/config.py', '''"""Configuration Manager"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None
    _config: Dict[str, Any] = {}
    _config_path: Path = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._config:
            self.load()

    def load(self, config_path: Optional[str] = None) -> None:
        if config_path:
            self._config_path = Path(config_path)
        else:
            paths = [
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
            logger.info(f"Config loaded from {self._config_path}")
        else:
            logger.warning("No config found, using defaults")
            self._config = self._get_defaults()

    def get(self, key: str, default: Any = None) -> Any:
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

    @property
    def database(self) -> Dict[str, Any]:
        return self._config.get('database', {})

    @property
    def redis(self) -> Dict[str, Any]:
        return self._config.get('redis', {})

    @property
    def capital_com(self) -> Dict[str, Any]:
        return self._config.get('capital_com', {})

    @property
    def telegram(self) -> Dict[str, Any]:
        return self._config.get('telegram', {})

    @property
    def symbols(self) -> Dict[str, Any]:
        return self._config.get('symbols', {})

    @property
    def bots(self) -> Dict[str, Any]:
        return self._config.get('bots', {})

    def get_enabled_symbols(self) -> list:
        return [s for s, cfg in self.symbols.items() if cfg.get('enabled', True)]

    def _get_defaults(self) -> Dict[str, Any]:
        return {
            "database": {"host": "localhost", "port": 5432, "dbname": "trading_bot", "user": "trader"},
            "redis": {"host": "localhost", "port": 6379, "db": 0},
            "symbols": {"XAUUSD": {"enabled": True}, "XAGUSD": {"enabled": True}}
        }

config = ConfigManager()
''')

    # DATABASE MANAGER
    create_file('services/shared/database.py', '''"""Database Manager"""
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple
import logging
import json

from .config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            self._init_pool()

    def _init_pool(self):
        db_config = config.database
        try:
            self._pool = ThreadedConnectionPool(
                minconn=2, maxconn=10,
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432),
                database=db_config.get('dbname', 'trading_bot'),
                user=db_config.get('user', 'trader'),
                password=db_config.get('password', '')
            )
            logger.info("Database pool initialized")
        except Exception as e:
            logger.error(f"DB pool failed: {e}")
            raise

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn: conn.rollback()
            raise
        finally:
            if conn: self._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, cursor_factory=RealDictCursor):
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()

    def execute(self, query: str, params: Tuple = None) -> int:
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def fetch_one(self, query: str, params: Tuple = None) -> Optional[Dict]:
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query: str, params: Tuple = None) -> List[Dict]:
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_symbol_id(self, symbol_name: str) -> Optional[int]:
        result = self.fetch_one("SELECT id FROM symbols WHERE name = %s", (symbol_name,))
        return result['id'] if result else None

    def ensure_symbol(self, symbol_name: str, description: str = None) -> int:
        symbol_id = self.get_symbol_id(symbol_name)
        if symbol_id:
            return symbol_id
        result = self.fetch_one(
            "INSERT INTO symbols (name, description) VALUES (%s, %s) RETURNING id",
            (symbol_name, description or symbol_name)
        )
        return result['id']

    def insert_price_data_bulk(self, data: List[Dict]) -> int:
        if not data: return 0
        query = """INSERT INTO price_data (symbol_id, timeframe, timestamp, open, high, low, close, volume)
                   VALUES %s ON CONFLICT (symbol_id, timeframe, timestamp) DO UPDATE
                   SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close"""
        values = [(d['symbol_id'], d['timeframe'], d['timestamp'], d['open'], d['high'], d['low'], d['close'], d.get('volume',0)) for d in data]
        with self.get_cursor() as cursor:
            execute_values(cursor, query, values)
            return len(values)

    def get_price_data(self, symbol_id: int, timeframe: str, limit: int = 500) -> List[Dict]:
        return self.fetch_all(
            "SELECT * FROM price_data WHERE symbol_id=%s AND timeframe=%s ORDER BY timestamp DESC LIMIT %s",
            (symbol_id, timeframe, limit)
        )

    def insert_signal(self, signal_data: Dict) -> int:
        if isinstance(signal_data.get('conditions'), list):
            signal_data['conditions'] = json.dumps(signal_data['conditions'])
        result = self.fetch_one("""
            INSERT INTO signals (symbol_id, timestamp, timeframe, direction, setup_name, conditions, confidence, tier, target_bot, entry_price, stop_loss, take_profit, status)
            VALUES (%(symbol_id)s, %(timestamp)s, %(timeframe)s, %(direction)s, %(setup_name)s, %(conditions)s, %(confidence)s, %(tier)s, %(target_bot)s, %(entry_price)s, %(stop_loss)s, %(take_profit)s, %(status)s)
            RETURNING id""", signal_data)
        return result['id'] if result else 0

    def get_pending_signals(self, bot_type: str = None, min_confidence: float = 0) -> List[Dict]:
        query = "SELECT * FROM signals WHERE status='pending' AND confidence >= %s"
        params = [min_confidence]
        if bot_type:
            query += " AND target_bot = %s"
            params.append(bot_type)
        query += " ORDER BY confidence DESC"
        return self.fetch_all(query, tuple(params))

    def init_schema(self):
        schema = """
        CREATE TABLE IF NOT EXISTS symbols (id SERIAL PRIMARY KEY, name VARCHAR(10) UNIQUE NOT NULL, description TEXT, pip_value DECIMAL DEFAULT 0.01, created_at TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS price_data (id BIGSERIAL, symbol_id INTEGER REFERENCES symbols(id), timeframe VARCHAR(10) NOT NULL, timestamp TIMESTAMP NOT NULL, open DECIMAL NOT NULL, high DECIMAL NOT NULL, low DECIMAL NOT NULL, close DECIMAL NOT NULL, volume DECIMAL DEFAULT 0, PRIMARY KEY (id), UNIQUE (symbol_id, timeframe, timestamp));
        CREATE TABLE IF NOT EXISTS signals (id BIGSERIAL PRIMARY KEY, symbol_id INTEGER REFERENCES symbols(id), timestamp TIMESTAMP NOT NULL, timeframe VARCHAR(10) NOT NULL, direction VARCHAR(4) NOT NULL, setup_name VARCHAR(100) NOT NULL, conditions JSONB, confidence DECIMAL NOT NULL, tier VARCHAR(1) NOT NULL, target_bot VARCHAR(20), entry_price DECIMAL, stop_loss DECIMAL, take_profit DECIMAL, status VARCHAR(20) DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS trades (id BIGSERIAL PRIMARY KEY, signal_id BIGINT REFERENCES signals(id), account_id VARCHAR(50), bot_type VARCHAR(20), symbol_id INTEGER REFERENCES symbols(id), direction VARCHAR(4), entry_price DECIMAL, exit_price DECIMAL, stop_loss DECIMAL, take_profit DECIMAL, position_size DECIMAL, risk_amount DECIMAL, pnl DECIMAL, pnl_r DECIMAL, status VARCHAR(20) DEFAULT 'open', opened_at TIMESTAMP DEFAULT NOW(), closed_at TIMESTAMP, close_reason VARCHAR(50), metadata JSONB);
        CREATE INDEX IF NOT EXISTS idx_price_ts ON price_data (symbol_id, timeframe, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status, created_at DESC);
        """
        with self.get_cursor() as cursor:
            cursor.execute(schema)
        logger.info("Schema initialized")

db = DatabaseManager()
''')

    # MESSAGE QUEUE
    create_file('services/shared/message_queue.py', '''"""Message Queue Manager - Redis"""
import redis
import json
from typing import Any, Dict, Optional
from datetime import datetime
import logging

from .config import config

logger = logging.getLogger(__name__)

class MessageQueue:
    _instance = None
    _redis = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._redis is None:
            self._connect()

    def _connect(self):
        redis_config = config.redis
        try:
            self._redis = redis.Redis(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                db=redis_config.get('db', 0),
                decode_responses=True
            )
            self._redis.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}, using memory")
            self._redis = MockRedis()

    def publish(self, channel: str, message: Any) -> int:
        if isinstance(message, (dict, list)):
            message = json.dumps(message, default=str)
        try:
            return self._redis.publish(channel, message)
        except: return 0

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str)
        try:
            return self._redis.set(key, value, ex=ttl)
        except: return False

    def get(self, key: str, default: Any = None) -> Any:
        try:
            value = self._redis.get(key)
            if value is None: return default
            try: return json.loads(value)
            except: return value
        except: return default

    def cache_price(self, symbol: str, price: float) -> bool:
        return self.set(f"price:{symbol}", {'price': price, 'ts': datetime.now().isoformat()}, ttl=60)

    def get_cached_price(self, symbol: str) -> Optional[float]:
        data = self.get(f"price:{symbol}")
        return data.get('price') if data else None

    def send_heartbeat(self, service_name: str, status: str = 'running') -> bool:
        msg = {'service': service_name, 'status': status, 'ts': datetime.now().isoformat()}
        self.publish('heartbeat', msg)
        return self.set(f"heartbeat:{service_name}", msg, ttl=120)

class MockRedis:
    def __init__(self): self._data = {}
    def ping(self): return True
    def set(self, k, v, ex=None): self._data[k]=v; return True
    def get(self, k): return self._data.get(k)
    def publish(self, c, m): return 1
    def delete(self, k): return self._data.pop(k, None) is not None

mq = MessageQueue()
''')

    # CAPITAL API
    create_file('services/shared/capital_api.py', '''"""Capital.com API Client"""
import requests
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from .config import config

logger = logging.getLogger(__name__)

class CapitalAPI:
    def __init__(self):
        cfg = config.capital_com
        self.base_url = cfg.get('base_url', 'https://demo-api-capital.backend-capital.com')
        self.api_key = cfg.get('api_key', '')
        self.identifier = cfg.get('identifier', '')
        self.password = cfg.get('password', '')
        self.session_token = None
        self.cst = None
        self._last_auth = None

    def _ensure_session(self):
        if self.session_token and self._last_auth:
            if datetime.now() - self._last_auth < timedelta(minutes=9):
                return True
        return self.authenticate()

    def authenticate(self) -> bool:
        try:
            headers = {'X-CAP-API-KEY': self.api_key, 'Content-Type': 'application/json'}
            data = {'identifier': self.identifier, 'password': self.password}
            resp = requests.post(f"{self.base_url}/api/v1/session", headers=headers, json=data, timeout=30)
            if resp.status_code == 200:
                self.cst = resp.headers.get('CST')
                self.session_token = resp.headers.get('X-SECURITY-TOKEN')
                self._last_auth = datetime.now()
                logger.info("Authenticated with Capital.com")
                return True
            logger.error(f"Auth failed: {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return False

    def _headers(self):
        return {'CST': self.cst, 'X-SECURITY-TOKEN': self.session_token, 'Content-Type': 'application/json'}

    def get_prices(self, epic: str, resolution: str = 'MINUTE', max_candles: int = 100) -> List[Dict]:
        if not self._ensure_session(): return []
        try:
            params = {'resolution': resolution, 'max': max_candles}
            resp = requests.get(f"{self.base_url}/api/v1/prices/{epic}", headers=self._headers(), params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                candles = []
                for p in data.get('prices', []):
                    candles.append({
                        'timestamp': p.get('snapshotTime'),
                        'open': float(p['openPrice']['mid']),
                        'high': float(p['highPrice']['mid']),
                        'low': float(p['lowPrice']['mid']),
                        'close': float(p['closePrice']['mid']),
                        'volume': float(p.get('lastTradedVolume', 0))
                    })
                return candles
            return []
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
            return []

    def get_account_info(self) -> Optional[Dict]:
        if not self._ensure_session(): return None
        try:
            resp = requests.get(f"{self.base_url}/api/v1/accounts", headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                accounts = resp.json().get('accounts', [])
                return accounts[0] if accounts else None
            return None
        except Exception as e:
            logger.error(f"Account error: {e}")
            return None

    def open_position(self, epic: str, direction: str, size: float, stop_distance: float = None, limit_distance: float = None) -> Optional[str]:
        if not self._ensure_session(): return None
        try:
            data = {'epic': epic, 'direction': direction.upper(), 'size': size, 'guaranteedStop': False}
            if stop_distance: data['stopDistance'] = stop_distance
            if limit_distance: data['limitDistance'] = limit_distance
            resp = requests.post(f"{self.base_url}/api/v1/positions", headers=self._headers(), json=data, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('dealReference')
            logger.error(f"Open position failed: {resp.text}")
            return None
        except Exception as e:
            logger.error(f"Open position error: {e}")
            return None

    def close_position(self, deal_id: str) -> bool:
        if not self._ensure_session(): return False
        try:
            resp = requests.delete(f"{self.base_url}/api/v1/positions/{deal_id}", headers=self._headers(), timeout=30)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Close position error: {e}")
            return False

    def get_positions(self) -> List[Dict]:
        if not self._ensure_session(): return []
        try:
            resp = requests.get(f"{self.base_url}/api/v1/positions", headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                return resp.json().get('positions', [])
            return []
        except: return []
''')

    # INDICATORS
    create_file('services/shared/indicators.py', '''"""Technical Indicators"""
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        if len(prices) < period: return None
        return sum(prices[-period:]) / period

    @staticmethod
    def ema(prices: List[float], period: int) -> Optional[float]:
        if len(prices) < period: return None
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema

    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[float]:
        if len(prices) < period + 1: return None
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        if len(highs) < period + 1: return None
        trs = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        return sum(trs[-period:]) / period

    @staticmethod
    def stochastic(highs: List[float], lows: List[float], closes: List[float], k_period: int = 14, d_period: int = 3) -> Dict:
        if len(closes) < k_period: return {}
        lowest = min(lows[-k_period:])
        highest = max(highs[-k_period:])
        if highest == lowest: return {'k': 50, 'd': 50}
        k = ((closes[-1] - lowest) / (highest - lowest)) * 100
        return {'k': k, 'd': k}  # Simplified

    @staticmethod
    def macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        if len(prices) < slow: return {}
        ema_fast = TechnicalIndicators.ema(prices, fast)
        ema_slow = TechnicalIndicators.ema(prices, slow)
        if not ema_fast or not ema_slow: return {}
        macd_line = ema_fast - ema_slow
        return {'macd': macd_line, 'signal': macd_line * 0.9, 'histogram': macd_line * 0.1}

    @staticmethod
    def bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
        if len(prices) < period: return {}
        sma = sum(prices[-period:]) / period
        variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
        std = variance ** 0.5
        return {'upper': sma + std * std_dev, 'middle': sma, 'lower': sma - std * std_dev}
''')

    # NOTIFICATIONS
    create_file('services/shared/notifications.py', '''"""Telegram Notifications"""
import requests
from typing import Optional
import logging

from .config import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        cfg = config.telegram
        self.token = cfg.get('token', '')
        self.chat_id = cfg.get('chat_id', '')
        self.enabled = bool(self.token and self.chat_id)

    def send(self, message: str, parse_mode: str = 'HTML') -> bool:
        if not self.enabled: return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            resp = requests.post(url, json={'chat_id': self.chat_id, 'text': message, 'parse_mode': parse_mode}, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    def send_signal(self, symbol: str, direction: str, tier: str, confidence: float, entry: float, sl: float, tp: float):
        emoji = "🟢" if direction == "BUY" else "🔴"
        msg = f"{emoji} <b>{tier}-Tier Signal</b>\\n\\n"
        msg += f"Symbol: {symbol}\\nDirection: {direction}\\nConfidence: {confidence:.1f}%\\n"
        msg += f"Entry: {entry:.2f}\\nSL: {sl:.2f}\\nTP: {tp:.2f}"
        return self.send(msg)

    def send_trade_opened(self, symbol: str, direction: str, size: float, entry: float, sl: float, tp: float, bot: str):
        emoji = "📈" if direction == "BUY" else "📉"
        msg = f"{emoji} <b>Trade Opened</b>\\n\\n"
        msg += f"Bot: {bot}\\nSymbol: {symbol}\\nDirection: {direction}\\n"
        msg += f"Size: {size}\\nEntry: {entry:.2f}\\nSL: {sl:.2f}\\nTP: {tp:.2f}"
        return self.send(msg)

    def send_trade_closed(self, symbol: str, pnl: float, pnl_r: float, reason: str, bot: str):
        emoji = "✅" if pnl > 0 else "❌"
        msg = f"{emoji} <b>Trade Closed</b>\\n\\n"
        msg += f"Bot: {bot}\\nSymbol: {symbol}\\nP/L: ${pnl:.2f} ({pnl_r:.1f}R)\\nReason: {reason}"
        return self.send(msg)

notify = TelegramNotifier()
''')

    # =================================================================
    # DATA SERVICES
    # =================================================================
    create_file('services/data/data_collector.py', '''#!/usr/bin/env python3
"""Data Collector - Fetches 1-min candles from Capital.com"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.capital_api import CapitalAPI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('data-collector')

class DataCollector:
    def __init__(self):
        self.api = CapitalAPI()
        self.symbols = config.get_enabled_symbols()
        self.symbol_ids = {}

    def init_symbols(self):
        for symbol in self.symbols:
            self.symbol_ids[symbol] = db.ensure_symbol(symbol)
        logger.info(f"Initialized symbols: {self.symbols}")

    def collect_candles(self, symbol: str):
        try:
            candles = self.api.get_prices(symbol, 'MINUTE', 10)
            if not candles:
                logger.warning(f"No candles for {symbol}")
                return 0

            symbol_id = self.symbol_ids[symbol]
            data = []
            for c in candles:
                data.append({
                    'symbol_id': symbol_id,
                    'timeframe': 'MINUTE',
                    'timestamp': c['timestamp'],
                    'open': c['open'],
                    'high': c['high'],
                    'low': c['low'],
                    'close': c['close'],
                    'volume': c.get('volume', 0)
                })

            inserted = db.insert_price_data_bulk(data)

            # Publish latest candle
            if candles:
                latest = candles[-1]
                mq.publish(f'price:{symbol.lower()}:1m', latest)
                mq.cache_price(symbol, latest['close'])

            return inserted
        except Exception as e:
            logger.error(f"Error collecting {symbol}: {e}")
            return 0

    def run(self):
        logger.info("Data Collector starting...")
        self.init_symbols()

        while True:
            try:
                for symbol in self.symbols:
                    count = self.collect_candles(symbol)
                    logger.info(f"Collected {count} candles for {symbol}")

                mq.send_heartbeat('data-collector')
                time.sleep(60)  # Collect every minute
            except Exception as e:
                logger.error(f"Collection cycle error: {e}")
                time.sleep(30)

if __name__ == '__main__':
    collector = DataCollector()
    collector.run()
''')

    create_file('services/data/timeframe_aggregator.py', '''#!/usr/bin/env python3
"""Timeframe Aggregator - Aggregates 1m candles to higher timeframes"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime, timedelta
from services.shared.config import config
from services.shared.database import db
from services.shared.message_queue import mq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('timeframe-aggregator')

TIMEFRAME_MINUTES = {'MINUTE_5': 5, 'MINUTE_15': 15, 'HOUR': 60, 'HOUR_4': 240, 'DAY': 1440}

class TimeframeAggregator:
    def __init__(self):
        self.symbols = config.get_enabled_symbols()
        self.symbol_ids = {s: db.ensure_symbol(s) for s in self.symbols}

    def aggregate(self, symbol: str, timeframe: str, minutes: int):
        try:
            symbol_id = self.symbol_ids[symbol]
            candles = db.get_price_data(symbol_id, 'MINUTE', limit=minutes + 5)
            if len(candles) < minutes:
                return

            candles = sorted(candles, key=lambda x: x['timestamp'])[-minutes:]

            agg = {
                'symbol_id': symbol_id,
                'timeframe': timeframe,
                'timestamp': candles[-1]['timestamp'],
                'open': candles[0]['open'],
                'high': max(c['high'] for c in candles),
                'low': min(c['low'] for c in candles),
                'close': candles[-1]['close'],
                'volume': sum(c.get('volume', 0) for c in candles)
            }

            db.insert_price_data_bulk([agg])
            mq.publish(f'price:{symbol.lower()}:{timeframe.lower()}', agg)
            logger.debug(f"Aggregated {symbol} {timeframe}")
        except Exception as e:
            logger.error(f"Aggregation error {symbol} {timeframe}: {e}")

    def run(self):
        logger.info("Timeframe Aggregator starting...")

        while True:
            try:
                now = datetime.now()

                for symbol in self.symbols:
                    for tf, mins in TIMEFRAME_MINUTES.items():
                        if now.minute % (mins if mins < 60 else 60) == 0:
                            self.aggregate(symbol, tf, mins)

                mq.send_heartbeat('timeframe-aggregator')
                time.sleep(60)
            except Exception as e:
                logger.error(f"Aggregation cycle error: {e}")
                time.sleep(30)

if __name__ == '__main__':
    agg = TimeframeAggregator()
    agg.run()
''')

    # =================================================================
    # SIGNAL SERVICES
    # =================================================================
    create_file('services/signals/base_signal_generator.py', '''"""Base Signal Generator"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import logging
from datetime import datetime
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

class BaseSignalGenerator(ABC):
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.symbol_id = db.ensure_symbol(symbol)
        self.indicators = TechnicalIndicators()

    def get_candles(self, timeframe: str, limit: int = 200) -> List[Dict]:
        return db.get_price_data(self.symbol_id, timeframe, limit=limit)

    def calculate_indicators(self, candles: List[Dict]) -> Dict:
        if not candles:
            return {}

        candles = sorted(candles, key=lambda x: x['timestamp'])
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]

        return {
            'rsi': self.indicators.rsi(closes),
            'stoch': self.indicators.stochastic(highs, lows, closes),
            'atr': self.indicators.atr(highs, lows, closes),
            'macd': self.indicators.macd(closes),
            'bb': self.indicators.bollinger_bands(closes),
            'ema_9': self.indicators.ema(closes, 9),
            'ema_21': self.indicators.ema(closes, 21),
            'ema_50': self.indicators.ema(closes, 50),
            'current_price': closes[-1] if closes else None
        }

    @abstractmethod
    def analyze(self, timeframe: str) -> Optional[Dict]:
        pass

    def generate_signal(self, direction: str, timeframe: str, setup_name: str,
                       confidence: float, entry: float, sl: float, tp: float,
                       conditions: List[str] = None) -> Dict:
        tier = 'A' if confidence >= 80 else 'B' if confidence >= 65 else 'C'

        signal = {
            'symbol_id': self.symbol_id,
            'symbol': self.symbol,
            'timestamp': datetime.now(),
            'timeframe': timeframe,
            'direction': direction,
            'setup_name': setup_name,
            'conditions': conditions or [],
            'confidence': confidence,
            'tier': tier,
            'target_bot': self._get_target_bot(timeframe, confidence),
            'entry_price': entry,
            'stop_loss': sl,
            'take_profit': tp,
            'status': 'pending'
        }

        return signal

    def _get_target_bot(self, timeframe: str, confidence: float) -> str:
        if confidence >= 85:
            return 'sniper'
        if timeframe in ['MINUTE', 'MINUTE_5']:
            return 'scalper'
        if timeframe in ['MINUTE_15', 'HOUR']:
            return 'day_trader'
        if timeframe in ['HOUR', 'HOUR_4']:
            return 'swing'
        return 'position'
''')

    create_file('services/signals/gold_signal_generator.py', '''#!/usr/bin/env python3
"""Gold Signal Generator"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from typing import Optional, Dict, List
from services.signals.base_signal_generator import BaseSignalGenerator
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('gold-signal-generator')

class GoldSignalGenerator(BaseSignalGenerator):
    def __init__(self):
        super().__init__('XAUUSD')
        self.timeframes = ['MINUTE', 'MINUTE_5', 'MINUTE_15', 'HOUR', 'HOUR_4']

    def analyze(self, timeframe: str) -> Optional[Dict]:
        candles = self.get_candles(timeframe, limit=200)
        if len(candles) < 50:
            return None

        ind = self.calculate_indicators(candles)
        if not ind.get('rsi'):
            return None

        conditions = []
        confidence = 50
        direction = None

        rsi = ind['rsi']
        stoch = ind.get('stoch', {})
        macd = ind.get('macd', {})
        bb = ind.get('bb', {})
        price = ind['current_price']

        # RSI Analysis
        if rsi < 30:
            conditions.append('RSI oversold')
            confidence += 15
            direction = 'BUY'
        elif rsi > 70:
            conditions.append('RSI overbought')
            confidence += 15
            direction = 'SELL'

        # Stochastic
        if stoch.get('k', 50) < 20:
            conditions.append('Stoch oversold')
            confidence += 10
            if not direction: direction = 'BUY'
        elif stoch.get('k', 50) > 80:
            conditions.append('Stoch overbought')
            confidence += 10
            if not direction: direction = 'SELL'

        # MACD
        if macd.get('histogram', 0) > 0 and direction == 'BUY':
            conditions.append('MACD bullish')
            confidence += 10
        elif macd.get('histogram', 0) < 0 and direction == 'SELL':
            conditions.append('MACD bearish')
            confidence += 10

        # Bollinger Bands
        if bb and price:
            if price < bb.get('lower', price):
                conditions.append('Below BB lower')
                confidence += 10
                if not direction: direction = 'BUY'
            elif price > bb.get('upper', price):
                conditions.append('Above BB upper')
                confidence += 10
                if not direction: direction = 'SELL'

        if not direction or confidence < 60:
            return None

        # Calculate SL/TP
        atr = ind.get('atr', 2.0) or 2.0
        if direction == 'BUY':
            sl = price - (atr * 2)
            tp = price + (atr * 4)
        else:
            sl = price + (atr * 2)
            tp = price - (atr * 4)

        return self.generate_signal(
            direction=direction,
            timeframe=timeframe,
            setup_name=f"Gold_{direction}_{timeframe}",
            confidence=min(confidence, 95),
            entry=price,
            sl=sl,
            tp=tp,
            conditions=conditions
        )

    def run(self):
        logger.info("Gold Signal Generator starting...")

        while True:
            try:
                for tf in self.timeframes:
                    signal = self.analyze(tf)
                    if signal:
                        signal_id = db.insert_signal(signal)
                        if signal_id:
                            signal['id'] = signal_id
                            mq.publish('signals:gold', signal)
                            logger.info(f"Signal: {signal['direction']} {tf} conf={signal['confidence']:.0f}%")

                            if signal['confidence'] >= 70:
                                notify.send_signal(
                                    self.symbol, signal['direction'], signal['tier'],
                                    signal['confidence'], signal['entry_price'],
                                    signal['stop_loss'], signal['take_profit']
                                )

                mq.send_heartbeat('gold-signal-generator')
                time.sleep(60)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(30)

if __name__ == '__main__':
    gen = GoldSignalGenerator()
    gen.run()
''')

    create_file('services/signals/silver_signal_generator.py', '''#!/usr/bin/env python3
"""Silver Signal Generator"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from typing import Optional, Dict
from services.signals.base_signal_generator import BaseSignalGenerator
from services.shared.database import db
from services.shared.message_queue import mq
from services.shared.notifications import notify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('silver-signal-generator')

class SilverSignalGenerator(BaseSignalGenerator):
    def __init__(self):
        super().__init__('XAGUSD')
        self.timeframes = ['MINUTE', 'MINUTE_5', 'MINUTE_15', 'HOUR', 'HOUR_4']

    def analyze(self, timeframe: str) -> Optional[Dict]:
        candles = self.get_candles(timeframe, limit=200)
        if len(candles) < 50:
            return None

        ind = self.calculate_indicators(candles)
        if not ind.get('rsi'):
            return None

        conditions = []
        confidence = 50
        direction = None

        rsi = ind['rsi']
        stoch = ind.get('stoch', {})
        price = ind['current_price']

        if rsi < 30:
            conditions.append('RSI oversold')
            confidence += 15
            direction = 'BUY'
        elif rsi > 70:
            conditions.append('RSI overbought')
            confidence += 15
            direction = 'SELL'

        if stoch.get('k', 50) < 20:
            conditions.append('Stoch oversold')
            confidence += 10
            if not direction: direction = 'BUY'
        elif stoch.get('k', 50) > 80:
            conditions.append('Stoch overbought')
            confidence += 10
            if not direction: direction = 'SELL'

        if not direction or confidence < 60:
            return None

        atr = ind.get('atr', 0.1) or 0.1
        if direction == 'BUY':
            sl = price - (atr * 2)
            tp = price + (atr * 4)
        else:
            sl = price + (atr * 2)
            tp = price - (atr * 4)

        return self.generate_signal(
            direction=direction,
            timeframe=timeframe,
            setup_name=f"Silver_{direction}_{timeframe}",
            confidence=min(confidence, 95),
            entry=price,
            sl=sl,
            tp=tp,
            conditions=conditions
        )

    def run(self):
        logger.info("Silver Signal Generator starting...")

        while True:
            try:
                for tf in self.timeframes:
                    signal = self.analyze(tf)
                    if signal:
                        signal_id = db.insert_signal(signal)
                        if signal_id:
                            signal['id'] = signal_id
                            mq.publish('signals:silver', signal)
                            logger.info(f"Signal: {signal['direction']} {tf} conf={signal['confidence']:.0f}%")

                mq.send_heartbeat('silver-signal-generator')
                time.sleep(60)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(30)

if __name__ == '__main__':
    gen = SilverSignalGenerator()
    gen.run()
''')

    create_file('services/signals/signal_aggregator.py', '''#!/usr/bin/env python3
"""Signal Aggregator - Routes signals to appropriate bots"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from services.shared.database import db
from services.shared.message_queue import mq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('signal-aggregator')

class SignalAggregator:
    def __init__(self):
        self.bot_channels = {
            'scalper': 'commands:scalper',
            'day_trader': 'commands:day_trader',
            'swing': 'commands:swing',
            'position': 'commands:position',
            'sniper': 'commands:sniper'
        }

    def process_signals(self):
        for bot_type in self.bot_channels.keys():
            signals = db.get_pending_signals(bot_type=bot_type, min_confidence=60)
            for signal in signals:
                channel = self.bot_channels[bot_type]
                mq.publish(channel, dict(signal))
                logger.info(f"Routed signal {signal['id']} to {bot_type}")

    def run(self):
        logger.info("Signal Aggregator starting...")

        while True:
            try:
                self.process_signals()
                mq.send_heartbeat('signal-aggregator')
                time.sleep(30)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(15)

if __name__ == '__main__':
    agg = SignalAggregator()
    agg.run()
''')

    # =================================================================
    # BOT SERVICES
    # =================================================================
    create_file('services/bots/base_trading_bot.py', '''"""Base Trading Bot"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import logging
from datetime import datetime
from services.shared.config import config
from services.shared.database import db
from services.shared.capital_api import CapitalAPI
from services.shared.notifications import notify

logger = logging.getLogger(__name__)

class BaseTradingBot(ABC):
    def __init__(self, bot_type: str):
        self.bot_type = bot_type
        self.api = CapitalAPI()
        self.bot_config = config.bots.get(bot_type, {})
        self.max_trades = self.bot_config.get('max_trades_per_day', 5)
        self.risk_percent = self.bot_config.get('risk_percent', 1.0)
        self.min_confidence = self.bot_config.get('min_confidence', 60)
        self.trades_today = 0
        self.open_trades = []

    def get_account_balance(self) -> float:
        account = self.api.get_account_info()
        return float(account.get('balance', 10000)) if account else 10000

    def calculate_position_size(self, entry: float, stop_loss: float) -> float:
        balance = self.get_account_balance()
        risk_amount = balance * (self.risk_percent / 100)
        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit == 0:
            return 0.01
        size = risk_amount / risk_per_unit
        return max(0.01, min(size, 10.0))

    def open_trade(self, signal: Dict) -> Optional[str]:
        if self.trades_today >= self.max_trades:
            logger.warning(f"{self.bot_type}: Max trades reached")
            return None

        if signal.get('confidence', 0) < self.min_confidence:
            return None

        size = self.calculate_position_size(signal['entry_price'], signal['stop_loss'])
        stop_distance = abs(signal['entry_price'] - signal['stop_loss'])
        limit_distance = abs(signal['take_profit'] - signal['entry_price'])

        deal_ref = self.api.open_position(
            epic=signal.get('symbol', 'XAUUSD'),
            direction=signal['direction'],
            size=size,
            stop_distance=stop_distance,
            limit_distance=limit_distance
        )

        if deal_ref:
            self.trades_today += 1
            self.open_trades.append({
                'deal_ref': deal_ref,
                'signal': signal,
                'size': size,
                'opened_at': datetime.now()
            })

            notify.send_trade_opened(
                signal.get('symbol', 'XAUUSD'),
                signal['direction'],
                size,
                signal['entry_price'],
                signal['stop_loss'],
                signal['take_profit'],
                self.bot_type
            )

            logger.info(f"Opened trade: {deal_ref}")
            return deal_ref

        return None

    @abstractmethod
    def process_signal(self, signal: Dict) -> bool:
        pass

    @abstractmethod
    def manage_positions(self):
        pass
''')

    # Create individual bot files
    for bot_name, bot_class in [
        ('scalper', 'Scalper'),
        ('day_trader', 'DayTrader'),
        ('swing', 'Swing'),
        ('position', 'Position'),
        ('sniper', 'Sniper')
    ]:
        create_file(f'services/bots/bot_{bot_name}.py', f'''#!/usr/bin/env python3
"""{bot_class} Bot"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from typing import Dict
from services.bots.base_trading_bot import BaseTradingBot
from services.shared.database import db
from services.shared.message_queue import mq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('bot-{bot_name}')

class {bot_class}Bot(BaseTradingBot):
    def __init__(self):
        super().__init__('{bot_name}')

    def process_signal(self, signal: Dict) -> bool:
        if signal.get('target_bot') != '{bot_name}':
            return False
        return self.open_trade(signal) is not None

    def manage_positions(self):
        positions = self.api.get_positions()
        # Position management logic here
        pass

    def run(self):
        logger.info("{bot_class} Bot starting...")

        while True:
            try:
                # Get pending signals
                signals = db.get_pending_signals(bot_type='{bot_name}', min_confidence=self.min_confidence)
                for signal in signals:
                    self.process_signal(dict(signal))

                self.manage_positions()
                mq.send_heartbeat('bot-{bot_name}')
                time.sleep(30)
            except Exception as e:
                logger.error(f"Error: {{e}}")
                time.sleep(15)

if __name__ == '__main__':
    bot = {bot_class}Bot()
    bot.run()
''')

    # =================================================================
    # LEARNING SERVICES
    # =================================================================
    create_file('services/learning/trade_analyzer.py', '''#!/usr/bin/env python3
"""Trade Analyzer - Performance analysis"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from services.shared.database import db
from services.shared.message_queue import mq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('trade-analyzer')

class TradeAnalyzer:
    def analyze(self):
        trades = db.fetch_all("SELECT * FROM trades WHERE status='closed' AND closed_at >= NOW() - INTERVAL '7 days'")
        if not trades:
            return

        wins = sum(1 for t in trades if float(t.get('pnl', 0)) > 0)
        total = len(trades)
        win_rate = (wins / total * 100) if total > 0 else 0

        logger.info(f"7-day stats: {total} trades, {win_rate:.1f}% win rate")

    def run(self):
        logger.info("Trade Analyzer starting...")

        while True:
            try:
                self.analyze()
                mq.send_heartbeat('trade-analyzer')
                time.sleep(3600)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(300)

if __name__ == '__main__':
    analyzer = TradeAnalyzer()
    analyzer.run()
''')

    create_file('services/learning/feedback_loop.py', '''#!/usr/bin/env python3
"""Feedback Loop - Self-learning parameter adjustments"""
import sys
sys.path.insert(0, '/home/trader/algo_trading')

import time
import logging
from datetime import datetime
from services.shared.database import db
from services.shared.message_queue import mq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('feedback-loop')

class FeedbackLoop:
    def adjust_weights(self):
        # Analyze setup performance and adjust weights
        logger.info("Analyzing setup performance...")

    def run(self):
        logger.info("Feedback Loop starting...")

        while True:
            try:
                now = datetime.now()
                if now.hour == 20 and now.minute < 5:
                    self.adjust_weights()

                mq.send_heartbeat('feedback-loop')
                time.sleep(300)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(60)

if __name__ == '__main__':
    loop = FeedbackLoop()
    loop.run()
''')

    # =================================================================
    # SYSTEMD SERVICES
    # =================================================================
    services = [
        ('data-collector', 'services/data/data_collector.py'),
        ('timeframe-aggregator', 'services/data/timeframe_aggregator.py'),
        ('gold-signal-generator', 'services/signals/gold_signal_generator.py'),
        ('silver-signal-generator', 'services/signals/silver_signal_generator.py'),
        ('signal-aggregator', 'services/signals/signal_aggregator.py'),
        ('bot-scalper', 'services/bots/bot_scalper.py'),
        ('bot-day-trader', 'services/bots/bot_day_trader.py'),
        ('bot-swing', 'services/bots/bot_swing.py'),
        ('bot-position', 'services/bots/bot_position.py'),
        ('bot-sniper', 'services/bots/bot_sniper.py'),
        ('trade-analyzer', 'services/learning/trade_analyzer.py'),
        ('feedback-loop', 'services/learning/feedback_loop.py'),
    ]

    for svc_name, svc_path in services:
        create_file(f'systemd/{svc_name}.service', f'''[Unit]
Description=Trading System - {svc_name}
After=network.target redis-server.service postgresql.service

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/algo_trading
ExecStart=/usr/bin/python3 /home/trader/algo_trading/{svc_path}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
''')

    # =================================================================
    # SCRIPTS
    # =================================================================
    create_file('scripts/status.sh', '''#!/bin/bash
SERVICES="data-collector timeframe-aggregator gold-signal-generator silver-signal-generator signal-aggregator bot-scalper bot-day-trader bot-swing bot-position bot-sniper trade-analyzer feedback-loop"
echo "=== Trading System Status ==="
for s in $SERVICES; do
    status=$(systemctl is-active $s 2>/dev/null || echo "unknown")
    printf "%-30s %s\\n" "$s" "$status"
done
''')

    create_file('scripts/start_all.sh', '''#!/bin/bash
SERVICES="data-collector timeframe-aggregator gold-signal-generator silver-signal-generator signal-aggregator bot-scalper bot-day-trader bot-swing bot-position bot-sniper trade-analyzer feedback-loop"
for s in $SERVICES; do
    echo "Starting $s..."
    sudo systemctl start $s
done
echo "Done!"
''')

    create_file('scripts/stop_all.sh', '''#!/bin/bash
SERVICES="data-collector timeframe-aggregator gold-signal-generator silver-signal-generator signal-aggregator bot-scalper bot-day-trader bot-swing bot-position bot-sniper trade-analyzer feedback-loop"
for s in $SERVICES; do
    echo "Stopping $s..."
    sudo systemctl stop $s
done
echo "Done!"
''')

    create_file('scripts/install_services.sh', '''#!/bin/bash
echo "Installing systemd services..."
sudo cp /home/trader/algo_trading/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
for svc in /home/trader/algo_trading/systemd/*.service; do
    name=$(basename $svc .service)
    sudo systemctl enable $name
    echo "Enabled $name"
done
echo "Done! Use './scripts/start_all.sh' to start services."
''')

    # Make scripts executable
    import subprocess
    subprocess.run(['chmod', '+x', f'{BASE_DIR}/scripts/status.sh'])
    subprocess.run(['chmod', '+x', f'{BASE_DIR}/scripts/start_all.sh'])
    subprocess.run(['chmod', '+x', f'{BASE_DIR}/scripts/stop_all.sh'])
    subprocess.run(['chmod', '+x', f'{BASE_DIR}/scripts/install_services.sh'])

    print("\n=== Installation Complete ===")
    print("\nNext steps:")
    print("1. Initialize database:")
    print("   python3 -c \"from services.shared.database import db; db.init_schema()\"")
    print("\n2. Install systemd services:")
    print("   ./scripts/install_services.sh")
    print("\n3. Start all services:")
    print("   ./scripts/start_all.sh")
    print("\n4. Check status:")
    print("   ./scripts/status.sh")

if __name__ == '__main__':
    install()
