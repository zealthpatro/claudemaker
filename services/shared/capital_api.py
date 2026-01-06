"""
Capital.com API Client
Handles authentication, market data, and order execution
"""

import requests
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
import threading

from .config import config

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """API session data"""
    cst: str
    security_token: str
    created_at: datetime
    expires_at: datetime

    def is_valid(self) -> bool:
        return datetime.now() < self.expires_at - timedelta(minutes=5)


class CapitalAPI:
    """Capital.com REST API client with session management"""

    _instance = None
    _session: Optional[Session] = None
    _lock = threading.Lock()

    # API endpoints
    ENDPOINTS = {
        'session': '/api/v1/session',
        'accounts': '/api/v1/accounts',
        'positions': '/api/v1/positions',
        'orders': '/api/v1/workingorders',
        'markets': '/api/v1/markets',
        'prices': '/api/v1/prices',
        'history': '/api/v1/history/activity',
        'deal': '/api/v1/positions',
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        api_config = config.capital_com
        self.base_url = api_config.get('base_url', 'https://demo-api-capital.backend-capital.com')
        self.api_key = api_config.get('api_key', '')
        self.identifier = api_config.get('identifier', '')
        self.password = api_config.get('password', '')
        self._request_count = 0
        self._last_request = 0

    def _get_headers(self, include_auth: bool = True) -> Dict[str, str]:
        """Get request headers"""
        headers = {
            'Content-Type': 'application/json',
            'X-CAP-API-KEY': self.api_key
        }
        if include_auth and self._session:
            headers['CST'] = self._session.cst
            headers['X-SECURITY-TOKEN'] = self._session.security_token
        return headers

    def _rate_limit(self):
        """Simple rate limiting - max 10 requests per second"""
        current = time.time()
        if current - self._last_request < 0.1:
            time.sleep(0.1)
        self._last_request = time.time()
        self._request_count += 1

    def _request(self, method: str, endpoint: str, data: Dict = None,
                 params: Dict = None, retry: int = 3) -> Tuple[bool, Any]:
        """Make API request with retry logic"""
        self._rate_limit()

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(include_auth=endpoint != self.ENDPOINTS['session'])

        for attempt in range(retry):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, params=params, timeout=30)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, json=data, timeout=30)
                elif method.upper() == 'PUT':
                    response = requests.put(url, headers=headers, json=data, timeout=30)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, timeout=30)
                else:
                    return False, f"Unknown method: {method}"

                if response.status_code == 200:
                    return True, response.json()
                elif response.status_code == 401:
                    # Session expired, re-authenticate
                    logger.warning("Session expired, re-authenticating...")
                    self._session = None
                    if self.authenticate():
                        continue
                    return False, "Authentication failed"
                else:
                    error = response.json() if response.text else {'error': response.status_code}
                    logger.error(f"API error: {error}")
                    return False, error

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, attempt {attempt + 1}/{retry}")
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                if attempt < retry - 1:
                    time.sleep(2 ** attempt)
                else:
                    return False, str(e)

        return False, "Max retries exceeded"

    # ============= Authentication =============

    def authenticate(self) -> bool:
        """Authenticate and create session"""
        with self._lock:
            if self._session and self._session.is_valid():
                return True

            data = {
                'identifier': self.identifier,
                'password': self.password
            }

            try:
                response = requests.post(
                    f"{self.base_url}{self.ENDPOINTS['session']}",
                    headers=self._get_headers(include_auth=False),
                    json=data,
                    timeout=30
                )

                if response.status_code == 200:
                    self._session = Session(
                        cst=response.headers.get('CST', ''),
                        security_token=response.headers.get('X-SECURITY-TOKEN', ''),
                        created_at=datetime.now(),
                        expires_at=datetime.now() + timedelta(hours=6)
                    )
                    logger.info("Successfully authenticated with Capital.com")
                    return True
                else:
                    logger.error(f"Authentication failed: {response.text}")
                    return False

            except Exception as e:
                logger.error(f"Authentication error: {e}")
                return False

    def ensure_session(self) -> bool:
        """Ensure valid session exists"""
        if not self._session or not self._session.is_valid():
            return self.authenticate()
        return True

    # ============= Account Methods =============

    def get_accounts(self) -> Tuple[bool, Any]:
        """Get all trading accounts"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('GET', self.ENDPOINTS['accounts'])

    def get_account_balance(self, account_id: str) -> Optional[Dict]:
        """Get account balance info"""
        success, data = self.get_accounts()
        if success and 'accounts' in data:
            for acc in data['accounts']:
                if acc.get('accountId') == account_id:
                    return {
                        'balance': acc.get('balance', {}).get('balance', 0),
                        'available': acc.get('balance', {}).get('available', 0),
                        'profitLoss': acc.get('balance', {}).get('profitLoss', 0),
                        'currency': acc.get('currency', 'USD')
                    }
        return None

    # ============= Market Data Methods =============

    def get_market_info(self, epic: str) -> Tuple[bool, Any]:
        """Get market information"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('GET', f"{self.ENDPOINTS['markets']}/{epic}")

    def get_prices(self, epic: str, resolution: str = 'MINUTE',
                   max_points: int = 100, from_date: str = None,
                   to_date: str = None) -> Tuple[bool, Any]:
        """
        Get historical prices

        Args:
            epic: Market identifier (e.g., 'GOLD', 'SILVER')
            resolution: Timeframe (MINUTE, MINUTE_5, MINUTE_15, HOUR, HOUR_4, DAY, WEEK)
            max_points: Maximum number of candles
            from_date: Start date (ISO format)
            to_date: End date (ISO format)
        """
        if not self.ensure_session():
            return False, "Not authenticated"

        params = {
            'resolution': resolution,
            'max': max_points
        }
        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date

        return self._request('GET', f"{self.ENDPOINTS['prices']}/{epic}", params=params)

    def get_current_price(self, epic: str) -> Optional[Dict]:
        """Get current bid/ask prices"""
        success, data = self.get_prices(epic, resolution='MINUTE', max_points=1)
        if success and 'prices' in data and data['prices']:
            latest = data['prices'][-1]
            return {
                'epic': epic,
                'bid': latest.get('closePrice', {}).get('bid', 0),
                'ask': latest.get('closePrice', {}).get('ask', 0),
                'timestamp': latest.get('snapshotTimeUTC')
            }
        return None

    def fetch_candles(self, symbol: str, timeframe: str,
                      count: int = 200, from_date: datetime = None) -> List[Dict]:
        """
        Fetch candles for a symbol

        Returns list of candles with format:
        {
            'timestamp': datetime,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': float
        }
        """
        # Map symbol to Capital.com epic
        epic_map = {
            'XAUUSD': 'GOLD',
            'XAGUSD': 'SILVER'
        }
        epic = epic_map.get(symbol, symbol)

        params = {}
        if from_date:
            params['from'] = from_date.strftime('%Y-%m-%dT%H:%M:%S')

        success, data = self.get_prices(epic, resolution=timeframe, max_points=count)

        if not success or 'prices' not in data:
            logger.error(f"Failed to fetch candles for {symbol}: {data}")
            return []

        candles = []
        for p in data['prices']:
            try:
                candle = {
                    'timestamp': datetime.fromisoformat(p['snapshotTimeUTC'].replace('Z', '+00:00')),
                    'open': (p['openPrice']['bid'] + p['openPrice']['ask']) / 2,
                    'high': (p['highPrice']['bid'] + p['highPrice']['ask']) / 2,
                    'low': (p['lowPrice']['bid'] + p['lowPrice']['ask']) / 2,
                    'close': (p['closePrice']['bid'] + p['closePrice']['ask']) / 2,
                    'volume': p.get('lastTradedVolume', 0)
                }
                candles.append(candle)
            except (KeyError, TypeError) as e:
                logger.warning(f"Failed to parse candle: {e}")
                continue

        return candles

    # ============= Position Methods =============

    def get_positions(self) -> Tuple[bool, Any]:
        """Get all open positions"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('GET', self.ENDPOINTS['positions'])

    def get_open_position_count(self) -> int:
        """Get count of open positions"""
        success, data = self.get_positions()
        if success and 'positions' in data:
            return len(data['positions'])
        return 0

    # ============= Order Methods =============

    def place_order(self, epic: str, direction: str, size: float,
                    stop_loss: float = None, take_profit: float = None,
                    order_type: str = 'MARKET', limit_price: float = None) -> Tuple[bool, Any]:
        """
        Place a trading order

        Args:
            epic: Market identifier
            direction: 'BUY' or 'SELL'
            size: Position size
            stop_loss: Stop loss price
            take_profit: Take profit price
            order_type: 'MARKET' or 'LIMIT'
            limit_price: Price for limit orders
        """
        if not self.ensure_session():
            return False, "Not authenticated"

        data = {
            'epic': epic,
            'direction': direction.upper(),
            'size': size,
            'guaranteedStop': False,
            'forceOpen': True
        }

        if stop_loss:
            data['stopLevel'] = stop_loss
        if take_profit:
            data['profitLevel'] = take_profit
        if order_type == 'LIMIT' and limit_price:
            data['level'] = limit_price

        return self._request('POST', self.ENDPOINTS['deal'], data=data)

    def close_position(self, deal_id: str) -> Tuple[bool, Any]:
        """Close an open position"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('DELETE', f"{self.ENDPOINTS['positions']}/{deal_id}")

    def modify_position(self, deal_id: str, stop_loss: float = None,
                        take_profit: float = None) -> Tuple[bool, Any]:
        """Modify stop loss or take profit"""
        if not self.ensure_session():
            return False, "Not authenticated"

        data = {}
        if stop_loss:
            data['stopLevel'] = stop_loss
        if take_profit:
            data['profitLevel'] = take_profit

        return self._request('PUT', f"{self.ENDPOINTS['positions']}/{deal_id}", data=data)

    # ============= Working Orders =============

    def get_working_orders(self) -> Tuple[bool, Any]:
        """Get all working (pending) orders"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('GET', self.ENDPOINTS['orders'])

    def place_limit_order(self, epic: str, direction: str, size: float,
                          level: float, stop_distance: float = None,
                          profit_distance: float = None) -> Tuple[bool, Any]:
        """Place a limit order"""
        if not self.ensure_session():
            return False, "Not authenticated"

        data = {
            'epic': epic,
            'direction': direction.upper(),
            'size': size,
            'level': level,
            'type': 'LIMIT',
            'timeInForce': 'GOOD_TILL_CANCELLED'
        }

        if stop_distance:
            data['stopDistance'] = stop_distance
        if profit_distance:
            data['profitDistance'] = profit_distance

        return self._request('POST', self.ENDPOINTS['orders'], data=data)

    def cancel_order(self, deal_id: str) -> Tuple[bool, Any]:
        """Cancel a working order"""
        if not self.ensure_session():
            return False, "Not authenticated"
        return self._request('DELETE', f"{self.ENDPOINTS['orders']}/{deal_id}")

    # ============= Activity History =============

    def get_activity_history(self, from_date: datetime = None,
                             to_date: datetime = None) -> Tuple[bool, Any]:
        """Get trading activity history"""
        if not self.ensure_session():
            return False, "Not authenticated"

        params = {}
        if from_date:
            params['from'] = from_date.strftime('%Y-%m-%dT%H:%M:%S')
        if to_date:
            params['to'] = to_date.strftime('%Y-%m-%dT%H:%M:%S')

        return self._request('GET', self.ENDPOINTS['history'], params=params)


# Global API instance
api = CapitalAPI()
