"""
Message Queue Manager
Redis-based pub/sub and caching for inter-service communication
"""

import redis
import json
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timedelta
import threading
import logging

from .config import config

logger = logging.getLogger(__name__)


class MessageQueue:
    """Redis-based message queue for microservice communication"""

    _instance = None
    _redis: redis.Redis = None
    _pubsub: redis.client.PubSub = None
    _subscribers: Dict[str, List[Callable]] = {}
    _listener_thread: threading.Thread = None

    # Channel definitions
    CHANNELS = {
        # Price data channels
        'price:xauusd:1m': 'Real-time 1-min candles for Gold',
        'price:xagusd:1m': 'Real-time 1-min candles for Silver',

        # Signal channels
        'signals:gold': 'New gold signals',
        'signals:silver': 'New silver signals',
        'signals:aggregated': 'Aggregated signals for bots',

        # Bot command channels
        'commands:scalper': 'Commands for scalper bot',
        'commands:day_trader': 'Commands for day trader',
        'commands:swing': 'Commands for swing trader',
        'commands:position': 'Commands for position trader',
        'commands:sniper': 'Commands for sniper bot',

        # System channels
        'heartbeat': 'Service heartbeats',
        'alerts': 'System alerts',
        'control': 'System control commands'
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._redis is None:
            self._connect()

    def _connect(self):
        """Connect to Redis"""
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
            logger.error(f"Failed to connect to Redis: {e}")
            # Create a mock redis for development without Redis
            self._redis = MockRedis()
            logger.warning("Using mock Redis - install Redis for production")

    @property
    def redis(self) -> redis.Redis:
        """Get Redis client"""
        return self._redis

    # ============= Pub/Sub Methods =============

    def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
        if isinstance(message, (dict, list)):
            message = json.dumps(message, default=str)
        try:
            return self._redis.publish(channel, message)
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")
            return 0

    def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to channel with callback"""
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)

        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()

        self._pubsub.subscribe(**{channel: self._message_handler})
        logger.info(f"Subscribed to {channel}")

        # Start listener thread if not running
        if self._listener_thread is None or not self._listener_thread.is_alive():
            self._start_listener()

    def _message_handler(self, message):
        """Handle incoming pub/sub messages"""
        if message['type'] == 'message':
            channel = message['channel']
            data = message['data']

            # Parse JSON if applicable
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                pass

            # Call all subscribers for this channel
            for callback in self._subscribers.get(channel, []):
                try:
                    callback(channel, data)
                except Exception as e:
                    logger.error(f"Callback error for {channel}: {e}")

    def _start_listener(self):
        """Start background listener thread"""
        def listener():
            try:
                for message in self._pubsub.listen():
                    if message['type'] == 'message':
                        self._message_handler(message)
            except Exception as e:
                logger.error(f"Listener error: {e}")

        self._listener_thread = threading.Thread(target=listener, daemon=True)
        self._listener_thread.start()
        logger.info("Started message listener thread")

    def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from channel"""
        if self._pubsub:
            self._pubsub.unsubscribe(channel)
        if channel in self._subscribers:
            del self._subscribers[channel]

    # ============= Cache Methods =============

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Set value with optional TTL in seconds"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            return self._redis.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set {key}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache"""
        try:
            value = self._redis.get(key)
            if value is None:
                return default
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logger.error(f"Failed to get {key}: {e}")
            return default

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self._redis.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self._redis.exists(key))
        except Exception as e:
            logger.error(f"Failed to check {key}: {e}")
            return False

    # ============= Price Data Caching =============

    def cache_candle(self, symbol: str, timeframe: str, candle: Dict) -> bool:
        """Cache latest candle data"""
        key = f"candle:{symbol}:{timeframe}"
        return self.set(key, candle, ttl=3600)  # 1 hour TTL

    def get_cached_candle(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """Get cached candle"""
        key = f"candle:{symbol}:{timeframe}"
        return self.get(key)

    def cache_price(self, symbol: str, price: float) -> bool:
        """Cache current price"""
        key = f"price:{symbol}"
        data = {
            'price': price,
            'timestamp': datetime.now().isoformat()
        }
        return self.set(key, data, ttl=60)  # 1 minute TTL

    def get_cached_price(self, symbol: str) -> Optional[float]:
        """Get cached price"""
        data = self.get(f"price:{symbol}")
        return data.get('price') if data else None

    # ============= Signal Queue =============

    def queue_signal(self, signal: Dict) -> bool:
        """Add signal to processing queue"""
        try:
            signal['queued_at'] = datetime.now().isoformat()
            self._redis.lpush('signal_queue', json.dumps(signal, default=str))
            return True
        except Exception as e:
            logger.error(f"Failed to queue signal: {e}")
            return False

    def get_next_signal(self, timeout: int = 0) -> Optional[Dict]:
        """Get next signal from queue (blocking)"""
        try:
            result = self._redis.brpop('signal_queue', timeout=timeout)
            if result:
                return json.loads(result[1])
            return None
        except Exception as e:
            logger.error(f"Failed to get signal: {e}")
            return None

    # ============= Heartbeat Methods =============

    def send_heartbeat(self, service_name: str, status: str = 'running', data: Dict = None) -> bool:
        """Send service heartbeat"""
        message = {
            'service': service_name,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'data': data or {}
        }
        # Publish and cache
        self.publish('heartbeat', message)
        return self.set(f"heartbeat:{service_name}", message, ttl=120)

    def get_heartbeat(self, service_name: str) -> Optional[Dict]:
        """Get service heartbeat"""
        return self.get(f"heartbeat:{service_name}")

    def get_all_heartbeats(self) -> Dict[str, Dict]:
        """Get all service heartbeats"""
        pattern = "heartbeat:*"
        heartbeats = {}
        try:
            for key in self._redis.scan_iter(pattern):
                service = key.replace("heartbeat:", "")
                heartbeats[service] = self.get(key)
        except Exception as e:
            logger.error(f"Failed to get heartbeats: {e}")
        return heartbeats

    # ============= Alert Methods =============

    def send_alert(self, level: str, message: str, data: Dict = None) -> bool:
        """Send system alert"""
        alert = {
            'level': level,  # info, warning, error, critical
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'data': data or {}
        }
        return bool(self.publish('alerts', alert))

    # ============= Lock Methods =============

    def acquire_lock(self, name: str, timeout: int = 30) -> bool:
        """Acquire distributed lock"""
        lock_key = f"lock:{name}"
        try:
            return bool(self._redis.set(lock_key, '1', nx=True, ex=timeout))
        except Exception as e:
            logger.error(f"Failed to acquire lock {name}: {e}")
            return False

    def release_lock(self, name: str) -> bool:
        """Release distributed lock"""
        return self.delete(f"lock:{name}")


class MockRedis:
    """Mock Redis for development without Redis server"""

    def __init__(self):
        self._data = {}
        self._subscribers = {}

    def ping(self):
        return True

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self._data:
            return False
        self._data[key] = value
        return True

    def get(self, key):
        return self._data.get(key)

    def delete(self, key):
        return self._data.pop(key, None) is not None

    def exists(self, key):
        return key in self._data

    def publish(self, channel, message):
        return 1

    def lpush(self, key, value):
        if key not in self._data:
            self._data[key] = []
        self._data[key].insert(0, value)
        return len(self._data[key])

    def brpop(self, key, timeout=0):
        if key in self._data and self._data[key]:
            return (key, self._data[key].pop())
        return None

    def scan_iter(self, pattern):
        import fnmatch
        pattern = pattern.replace('*', '.*')
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]

    def pubsub(self):
        return MockPubSub()


class MockPubSub:
    """Mock PubSub for development"""

    def subscribe(self, **kwargs):
        pass

    def unsubscribe(self, channel):
        pass

    def listen(self):
        while True:
            import time
            time.sleep(1)
            yield {'type': 'ping'}


# Global message queue instance
mq = MessageQueue()
