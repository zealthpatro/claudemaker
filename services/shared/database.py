"""
Database Manager
PostgreSQL connection and query management for trading data
"""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import json

from .config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connections and queries for the trading system"""

    _instance = None
    _pool: ThreadedConnectionPool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._pool is None:
            self._init_pool()

    def _init_pool(self):
        """Initialize connection pool"""
        db_config = config.database
        try:
            self._pool = ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432),
                database=db_config.get('dbname', 'trading_bot'),
                user=db_config.get('user', 'trader'),
                password=db_config.get('password', '')
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get connection from pool"""
        conn = None
        try:
            conn = self._pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self._pool.putconn(conn)

    @contextmanager
    def get_cursor(self, cursor_factory=RealDictCursor):
        """Get cursor with automatic connection management"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()

    def execute(self, query: str, params: Tuple = None) -> int:
        """Execute a query and return affected rows"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def fetch_one(self, query: str, params: Tuple = None) -> Optional[Dict]:
        """Fetch single row"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def fetch_all(self, query: str, params: Tuple = None) -> List[Dict]:
        """Fetch all rows"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def insert_many(self, table: str, columns: List[str], values: List[Tuple]) -> int:
        """Bulk insert with execute_values"""
        if not values:
            return 0
        cols = ', '.join(columns)
        query = f"INSERT INTO {table} ({cols}) VALUES %s"
        with self.get_cursor() as cursor:
            execute_values(cursor, query, values)
            return len(values)

    # ============= Price Data Methods =============

    def insert_price_data(self, symbol_id: int, timeframe: str, timestamp: datetime,
                          open_: float, high: float, low: float, close: float,
                          volume: float = 0) -> int:
        """Insert single candle"""
        query = """
            INSERT INTO price_data (symbol_id, timeframe, timestamp, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol_id, timeframe, timestamp) DO UPDATE
            SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            RETURNING id
        """
        result = self.fetch_one(query, (symbol_id, timeframe, timestamp, open_, high, low, close, volume))
        return result['id'] if result else 0

    def insert_price_data_bulk(self, data: List[Dict]) -> int:
        """Bulk insert price data"""
        if not data:
            return 0
        query = """
            INSERT INTO price_data (symbol_id, timeframe, timestamp, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (symbol_id, timeframe, timestamp) DO UPDATE
            SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
        """
        values = [(d['symbol_id'], d['timeframe'], d['timestamp'],
                   d['open'], d['high'], d['low'], d['close'], d.get('volume', 0))
                  for d in data]
        with self.get_cursor() as cursor:
            execute_values(cursor, query, values)
            return len(values)

    def get_price_data(self, symbol_id: int, timeframe: str,
                       start: datetime = None, end: datetime = None,
                       limit: int = 500) -> List[Dict]:
        """Get price data with optional time range"""
        query = """
            SELECT * FROM price_data
            WHERE symbol_id = %s AND timeframe = %s
        """
        params = [symbol_id, timeframe]

        if start:
            query += " AND timestamp >= %s"
            params.append(start)
        if end:
            query += " AND timestamp <= %s"
            params.append(end)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        return self.fetch_all(query, tuple(params))

    def get_latest_price(self, symbol_id: int, timeframe: str) -> Optional[Dict]:
        """Get most recent candle"""
        query = """
            SELECT * FROM price_data
            WHERE symbol_id = %s AND timeframe = %s
            ORDER BY timestamp DESC LIMIT 1
        """
        return self.fetch_one(query, (symbol_id, timeframe))

    # ============= Signal Methods =============

    def insert_signal(self, signal_data: Dict) -> int:
        """Insert new signal"""
        query = """
            INSERT INTO signals (
                symbol_id, timestamp, timeframe, direction, setup_name,
                conditions, confidence, tier, target_bot, entry_price,
                stop_loss, take_profit, status
            ) VALUES (
                %(symbol_id)s, %(timestamp)s, %(timeframe)s, %(direction)s,
                %(setup_name)s, %(conditions)s, %(confidence)s, %(tier)s,
                %(target_bot)s, %(entry_price)s, %(stop_loss)s, %(take_profit)s,
                %(status)s
            ) RETURNING id
        """
        if isinstance(signal_data.get('conditions'), list):
            signal_data['conditions'] = json.dumps(signal_data['conditions'])
        result = self.fetch_one(query, signal_data)
        return result['id'] if result else 0

    def get_pending_signals(self, bot_type: str = None, symbol_id: int = None,
                            min_confidence: float = 0) -> List[Dict]:
        """Get pending signals for processing"""
        query = """
            SELECT * FROM signals
            WHERE status = 'pending' AND confidence >= %s
        """
        params = [min_confidence]

        if bot_type:
            query += " AND target_bot = %s"
            params.append(bot_type)
        if symbol_id:
            query += " AND symbol_id = %s"
            params.append(symbol_id)

        query += " ORDER BY confidence DESC, created_at ASC"
        return self.fetch_all(query, tuple(params))

    def update_signal_status(self, signal_id: int, status: str) -> int:
        """Update signal status"""
        query = "UPDATE signals SET status = %s WHERE id = %s"
        return self.execute(query, (status, signal_id))

    # ============= Trade Methods =============

    def insert_trade(self, trade_data: Dict) -> int:
        """Insert new trade"""
        query = """
            INSERT INTO trades (
                signal_id, account_id, bot_type, symbol_id, direction,
                entry_price, stop_loss, take_profit, position_size,
                risk_amount, status, metadata
            ) VALUES (
                %(signal_id)s, %(account_id)s, %(bot_type)s, %(symbol_id)s,
                %(direction)s, %(entry_price)s, %(stop_loss)s, %(take_profit)s,
                %(position_size)s, %(risk_amount)s, %(status)s, %(metadata)s
            ) RETURNING id
        """
        if isinstance(trade_data.get('metadata'), dict):
            trade_data['metadata'] = json.dumps(trade_data['metadata'])
        result = self.fetch_one(query, trade_data)
        return result['id'] if result else 0

    def close_trade(self, trade_id: int, exit_price: float, pnl: float,
                    pnl_r: float, close_reason: str) -> int:
        """Close a trade"""
        query = """
            UPDATE trades SET
                exit_price = %s, pnl = %s, pnl_r = %s,
                status = 'closed', closed_at = NOW(), close_reason = %s
            WHERE id = %s
        """
        return self.execute(query, (exit_price, pnl, pnl_r, close_reason, trade_id))

    def get_open_trades(self, bot_type: str = None, symbol_id: int = None) -> List[Dict]:
        """Get open trades"""
        query = "SELECT * FROM trades WHERE status = 'open'"
        params = []

        if bot_type:
            query += " AND bot_type = %s"
            params.append(bot_type)
        if symbol_id:
            query += " AND symbol_id = %s"
            params.append(symbol_id)

        query += " ORDER BY opened_at DESC"
        return self.fetch_all(query, tuple(params) if params else None)

    def get_trade_history(self, days: int = 30, bot_type: str = None) -> List[Dict]:
        """Get trade history"""
        query = """
            SELECT * FROM trades
            WHERE closed_at >= NOW() - INTERVAL '%s days'
        """
        params = [days]

        if bot_type:
            query += " AND bot_type = %s"
            params.append(bot_type)

        query += " ORDER BY closed_at DESC"
        return self.fetch_all(query, tuple(params))

    # ============= Performance Methods =============

    def get_setup_performance(self, setup_name: str = None, days: int = 30) -> List[Dict]:
        """Get performance metrics by setup"""
        query = """
            SELECT
                s.setup_name,
                s.timeframe,
                COUNT(*) as total_trades,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) as losses,
                ROUND(AVG(t.pnl_r)::numeric, 2) as avg_r,
                ROUND((SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)::float /
                       NULLIF(COUNT(*), 0) * 100)::numeric, 1) as win_rate
            FROM trades t
            JOIN signals s ON t.signal_id = s.id
            WHERE t.status = 'closed'
              AND t.closed_at >= NOW() - INTERVAL '%s days'
        """
        params = [days]

        if setup_name:
            query += " AND s.setup_name = %s"
            params.append(setup_name)

        query += " GROUP BY s.setup_name, s.timeframe ORDER BY win_rate DESC"
        return self.fetch_all(query, tuple(params))

    def get_daily_pnl(self, days: int = 30, account_id: str = None) -> List[Dict]:
        """Get daily P/L summary"""
        query = """
            SELECT
                DATE(closed_at) as date,
                COUNT(*) as trades,
                SUM(pnl) as total_pnl,
                SUM(pnl_r) as total_r,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades
            WHERE status = 'closed'
              AND closed_at >= NOW() - INTERVAL '%s days'
        """
        params = [days]

        if account_id:
            query += " AND account_id = %s"
            params.append(account_id)

        query += " GROUP BY DATE(closed_at) ORDER BY date DESC"
        return self.fetch_all(query, tuple(params))

    # ============= Symbol Methods =============

    def get_symbol_id(self, symbol_name: str) -> Optional[int]:
        """Get symbol ID by name"""
        result = self.fetch_one(
            "SELECT id FROM symbols WHERE name = %s",
            (symbol_name,)
        )
        return result['id'] if result else None

    def ensure_symbol(self, symbol_name: str, description: str = None) -> int:
        """Ensure symbol exists, create if not"""
        symbol_id = self.get_symbol_id(symbol_name)
        if symbol_id:
            return symbol_id

        result = self.fetch_one(
            "INSERT INTO symbols (name, description) VALUES (%s, %s) RETURNING id",
            (symbol_name, description or symbol_name)
        )
        return result['id']

    # ============= System State Methods =============

    def update_service_state(self, service_name: str, status: str, config: Dict = None) -> int:
        """Update service heartbeat and status"""
        query = """
            INSERT INTO system_state (service_name, last_heartbeat, status, config, updated_at)
            VALUES (%s, NOW(), %s, %s, NOW())
            ON CONFLICT (service_name) DO UPDATE
            SET last_heartbeat = NOW(), status = EXCLUDED.status,
                config = COALESCE(EXCLUDED.config, system_state.config),
                updated_at = NOW()
        """
        config_json = json.dumps(config) if config else None
        return self.execute(query, (service_name, status, config_json))

    def get_service_states(self) -> List[Dict]:
        """Get all service states"""
        return self.fetch_all(
            "SELECT * FROM system_state ORDER BY service_name"
        )

    def init_schema(self):
        """Initialize database schema if not exists"""
        schema = """
        -- Symbols table
        CREATE TABLE IF NOT EXISTS symbols (
            id SERIAL PRIMARY KEY,
            name VARCHAR(10) UNIQUE NOT NULL,
            description TEXT,
            pip_value DECIMAL DEFAULT 0.01,
            min_lot DECIMAL DEFAULT 0.01,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- Price data table
        CREATE TABLE IF NOT EXISTS price_data (
            id BIGSERIAL,
            symbol_id INTEGER REFERENCES symbols(id),
            timeframe VARCHAR(10) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            open DECIMAL NOT NULL,
            high DECIMAL NOT NULL,
            low DECIMAL NOT NULL,
            close DECIMAL NOT NULL,
            volume DECIMAL DEFAULT 0,
            PRIMARY KEY (id),
            UNIQUE (symbol_id, timeframe, timestamp)
        );

        -- Indicators table
        CREATE TABLE IF NOT EXISTS indicators (
            id BIGSERIAL PRIMARY KEY,
            symbol_id INTEGER REFERENCES symbols(id),
            timeframe VARCHAR(10) NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            rsi DECIMAL,
            stoch_k DECIMAL,
            stoch_d DECIMAL,
            atr DECIMAL,
            ema_9 DECIMAL,
            ema_21 DECIMAL,
            ema_50 DECIMAL,
            ema_200 DECIMAL,
            macd DECIMAL,
            macd_signal DECIMAL,
            macd_hist DECIMAL,
            bb_upper DECIMAL,
            bb_middle DECIMAL,
            bb_lower DECIMAL,
            vwap DECIMAL,
            UNIQUE (symbol_id, timeframe, timestamp)
        );

        -- Signals table
        CREATE TABLE IF NOT EXISTS signals (
            id BIGSERIAL PRIMARY KEY,
            symbol_id INTEGER REFERENCES symbols(id),
            timestamp TIMESTAMP NOT NULL,
            timeframe VARCHAR(10) NOT NULL,
            direction VARCHAR(4) NOT NULL,
            setup_name VARCHAR(100) NOT NULL,
            conditions JSONB,
            confidence DECIMAL NOT NULL,
            tier VARCHAR(1) NOT NULL,
            target_bot VARCHAR(20),
            entry_price DECIMAL,
            stop_loss DECIMAL,
            take_profit DECIMAL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- Trades table
        CREATE TABLE IF NOT EXISTS trades (
            id BIGSERIAL PRIMARY KEY,
            signal_id BIGINT REFERENCES signals(id),
            account_id VARCHAR(50) NOT NULL,
            bot_type VARCHAR(20) NOT NULL,
            symbol_id INTEGER REFERENCES symbols(id),
            direction VARCHAR(4) NOT NULL,
            entry_price DECIMAL NOT NULL,
            exit_price DECIMAL,
            stop_loss DECIMAL NOT NULL,
            take_profit DECIMAL NOT NULL,
            position_size DECIMAL NOT NULL,
            risk_amount DECIMAL NOT NULL,
            pnl DECIMAL,
            pnl_r DECIMAL,
            status VARCHAR(20) DEFAULT 'open',
            opened_at TIMESTAMP DEFAULT NOW(),
            closed_at TIMESTAMP,
            close_reason VARCHAR(50),
            metadata JSONB
        );

        -- Model performance table
        CREATE TABLE IF NOT EXISTS model_performance (
            id BIGSERIAL PRIMARY KEY,
            model_name VARCHAR(50) NOT NULL,
            version VARCHAR(20) NOT NULL,
            trained_at TIMESTAMP NOT NULL,
            train_accuracy DECIMAL,
            test_accuracy DECIMAL,
            live_accuracy DECIMAL,
            predictions_count INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT false,
            metadata JSONB
        );

        -- Setup performance table
        CREATE TABLE IF NOT EXISTS setup_performance (
            id BIGSERIAL PRIMARY KEY,
            setup_name VARCHAR(100) NOT NULL,
            symbol_id INTEGER REFERENCES symbols(id),
            timeframe VARCHAR(10) NOT NULL,
            period_start TIMESTAMP NOT NULL,
            period_end TIMESTAMP NOT NULL,
            total_trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            win_rate DECIMAL,
            avg_r DECIMAL,
            profit_factor DECIMAL,
            max_drawdown DECIMAL,
            is_active BOOLEAN DEFAULT true,
            weight DECIMAL DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        -- System state table
        CREATE TABLE IF NOT EXISTS system_state (
            id SERIAL PRIMARY KEY,
            service_name VARCHAR(50) UNIQUE NOT NULL,
            last_heartbeat TIMESTAMP,
            status VARCHAR(20),
            config JSONB,
            updated_at TIMESTAMP DEFAULT NOW()
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_price_symbol_tf_ts ON price_data (symbol_id, timeframe, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status, opened_at DESC);
        CREATE INDEX IF NOT EXISTS idx_trades_bot ON trades (bot_type, opened_at DESC);
        """
        with self.get_cursor() as cursor:
            cursor.execute(schema)
        logger.info("Database schema initialized")


# Global database instance
db = DatabaseManager()
