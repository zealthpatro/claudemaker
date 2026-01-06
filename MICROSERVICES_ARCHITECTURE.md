# Precious Metals Algo Trading - Microservices Architecture

## System Overview

A self-learning algorithmic trading system for Gold (XAUUSD) and Silver (XAGUSD) with multiple trading strategies operating across different timeframes and investment horizons.

**Target:** 70% win rate for daily trades, optimal entry/exit for investments

---

## ARCHITECTURE DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           PRECIOUS METALS ALGO TRADING SYSTEM                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                              DATA LAYER                                          │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │  │
│   │  │   DATA       │    │   DATA       │    │  TIMEFRAME   │    │  TIMESCALE   │  │  │
│   │  │  COLLECTOR   │───▶│  VALIDATOR   │───▶│  AGGREGATOR  │───▶│   POSTGRES   │  │  │
│   │  │  (1-min)     │    │              │    │  (5m-1D)     │    │   DATABASE   │  │  │
│   │  └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘  │  │
│   │         │                                                            │          │  │
│   │         │              ┌────────────────────────────────────────────┘          │  │
│   │         │              │                                                        │  │
│   │         ▼              ▼                                                        │  │
│   │  ┌──────────────────────────┐                                                   │  │
│   │  │      REDIS CACHE         │ (Real-time candles, latest prices)               │  │
│   │  └──────────────────────────┘                                                   │  │
│   │                                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                           │                                             │
│                                           ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                           SIGNAL GENERATION LAYER                                │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌─────────────────────────────┐      ┌─────────────────────────────┐           │  │
│   │  │   GOLD SIGNAL GENERATOR     │      │  SILVER SIGNAL GENERATOR    │           │  │
│   │  │                             │      │                             │           │  │
│   │  │  • Pattern Detection        │      │  • Pattern Detection        │           │  │
│   │  │  • Indicator Analysis       │      │  • Indicator Analysis       │           │  │
│   │  │  • ICT/SMC Concepts         │      │  • ICT/SMC Concepts         │           │  │
│   │  │  • Multi-timeframe Confirm  │      │  • Multi-timeframe Confirm  │           │  │
│   │  └─────────────────────────────┘      └─────────────────────────────┘           │  │
│   │                  │                                │                              │  │
│   │                  └────────────────┬───────────────┘                              │  │
│   │                                   ▼                                              │  │
│   │                    ┌─────────────────────────────┐                              │  │
│   │                    │   SIGNAL AGGREGATOR         │                              │  │
│   │                    │   • Confidence Scoring      │                              │  │
│   │                    │   • Tier Classification     │                              │  │
│   │                    │   • Correlation Check       │                              │  │
│   │                    └─────────────────────────────┘                              │  │
│   │                                   │                                              │  │
│   └───────────────────────────────────┼──────────────────────────────────────────────┘  │
│                                       ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                              TRADING BOT LAYER                                   │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │  │
│   │  │  SCALPER   │ │ DAY TRADER │ │   SWING    │ │  POSITION  │ │   SNIPER   │    │  │
│   │  │    BOT     │ │    BOT     │ │    BOT     │ │    BOT     │ │    BOT     │    │  │
│   │  ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤ ├────────────┤    │  │
│   │  │ TF: 1m-5m  │ │ TF: 5m-1H  │ │ TF: 1H-4H  │ │ TF: 4H-1D  │ │ Conf: 85%+ │    │  │
│   │  │ Hold: <1hr │ │ Hold: <1day│ │ Hold: days │ │ Hold: weeks│ │ TF: Any    │    │  │
│   │  │ Target: 5R │ │ Target: 3R │ │ Target: 5R │ │ Target: 10R│ │ Target: 20R│    │  │
│   │  │ Risk: 1%   │ │ Risk: 2%   │ │ Risk: 3%   │ │ Risk: 2%   │ │ Risk: 5%   │    │  │
│   │  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘    │  │
│   │                                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                                  │
│                                       ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                            EXECUTION & RISK LAYER                                │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐  │  │
│   │  │  POSITION SIZER  │  │  RISK MANAGER    │  │     EXECUTION ENGINE         │  │  │
│   │  │                  │  │                  │  │                              │  │  │
│   │  │  • Kelly Sizing  │  │  • DD Protection │  │  • Order Routing             │  │  │
│   │  │  • Correlation   │  │  • Daily Limits  │  │  • Slippage Optimization    │  │  │
│   │  │  • Vol Scaling   │  │  • Max Positions │  │  • Partial Exits            │  │  │
│   │  └──────────────────┘  └──────────────────┘  └──────────────────────────────┘  │  │
│   │                                                              │                   │  │
│   │                                                              ▼                   │  │
│   │                                                   ┌──────────────────┐          │  │
│   │                                                   │   CAPITAL.COM    │          │  │
│   │                                                   │      API         │          │  │
│   │                                                   └──────────────────┘          │  │
│   │                                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                       │                                                  │
│                                       ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                            SELF-LEARNING LAYER                                   │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │  │
│   │  │ TRADE ANALYZER  │  │  ML TRAINER     │  │ STRATEGY        │                 │  │
│   │  │                 │  │                 │  │ OPTIMIZER       │                 │  │
│   │  │ • Win/Loss      │  │ • Pattern CNN   │  │                 │                 │  │
│   │  │ • R:R Analysis  │  │ • Entry XGBoost │  │ • Parameter     │                 │  │
│   │  │ • Setup Perf    │  │ • Exit RL Agent │  │   Tuning        │                 │  │
│   │  │ • Time Analysis │  │ • Regime HMM    │  │ • A/B Testing   │                 │  │
│   │  │ • Correlation   │  │ • Meta-Learner  │  │ • Walk-Forward  │                 │  │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │  │
│   │          │                    │                    │                            │  │
│   │          └────────────────────┼────────────────────┘                            │  │
│   │                               ▼                                                  │  │
│   │                    ┌─────────────────────────────┐                              │  │
│   │                    │   FEEDBACK LOOP             │                              │  │
│   │                    │   • Update Signal Weights   │                              │  │
│   │                    │   • Adjust Risk Parameters  │                              │  │
│   │                    │   • Promote Winning Setups  │                              │  │
│   │                    │   • Demote Losing Setups    │                              │  │
│   │                    └─────────────────────────────┘                              │  │
│   │                                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│   │                              INFRASTRUCTURE                                      │  │
│   ├─────────────────────────────────────────────────────────────────────────────────┤  │
│   │                                                                                  │  │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐               │  │
│   │  │  MESSAGE   │  │    API     │  │  TELEGRAM  │  │  GRAFANA   │               │  │
│   │  │   QUEUE    │  │   GATEWAY  │  │ COMMANDER  │  │ DASHBOARD  │               │  │
│   │  │  (Redis)   │  │            │  │            │  │            │               │  │
│   │  └────────────┘  └────────────┘  └────────────┘  └────────────┘               │  │
│   │                                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## MICROSERVICES BREAKDOWN

### 1. DATA PIPELINE MICROSERVICES

#### 1.1 Data Collector (`data_collector.py`)
- **Purpose:** Fetch real-time price data for XAUUSD and XAGUSD
- **Frequency:** Every 1 minute
- **Source:** Capital.com API
- **Output:** Raw OHLCV data to Redis + PostgreSQL

#### 1.2 Timeframe Aggregator (`timeframe_aggregator.py`)
- **Purpose:** Aggregate 1-minute data into higher timeframes
- **Timeframes:** 5m, 15m, 1H, 4H, 1D
- **Output:** Aggregated candles with indicators pre-calculated

#### 1.3 Indicator Calculator (`indicator_calculator.py`)
- **Purpose:** Calculate all technical indicators
- **Indicators:**
  - RSI (14)
  - Stochastic (14, 3, 3)
  - ATR (14)
  - VWAP
  - EMAs (9, 21, 50, 200)
  - MACD (12, 26, 9)
  - Bollinger Bands
  - Volume Profile

---

### 2. SIGNAL GENERATION MICROSERVICES

#### 2.1 Gold Signal Generator (`gold_signal_generator.py`)
- **Asset:** XAUUSD
- **Setups:** All backtested + new ML-discovered patterns
- **Output:** Signal with confidence score, tier, direction

#### 2.2 Silver Signal Generator (`silver_signal_generator.py`)
- **Asset:** XAGUSD
- **Setups:** Adapted gold setups + silver-specific patterns
- **Note:** Silver often leads/lags gold - use for confirmation

#### 2.3 Signal Aggregator (`signal_aggregator.py`)
- **Purpose:** Combine signals, calculate confidence, route to bots
- **Logic:**
  - Multi-timeframe confluence scoring
  - Cross-commodity confirmation (gold/silver correlation)
  - Final tier assignment and bot routing

---

### 3. TRADING BOT MICROSERVICES

#### 3.1 Scalper Bot (`bot_scalper.py`)
| Parameter | Value |
|-----------|-------|
| Timeframes | 1m, 5m |
| Hold Duration | < 1 hour |
| Target R:R | 3-5R |
| Risk per Trade | 1% |
| Max Concurrent | 3 |
| Sessions | London, NY open |

#### 3.2 Day Trader Bot (`bot_day_trader.py`)
| Parameter | Value |
|-----------|-------|
| Timeframes | 5m, 15m, 1H |
| Hold Duration | < 1 day |
| Target R:R | 2-3R |
| Risk per Trade | 2% |
| Max Concurrent | 4 |
| Close Before | Market close |

#### 3.3 Swing Trader Bot (`bot_swing.py`)
| Parameter | Value |
|-----------|-------|
| Timeframes | 1H, 4H |
| Hold Duration | 2-5 days |
| Target R:R | 5R |
| Risk per Trade | 3% |
| Max Concurrent | 3 |
| Trailing Stop | Yes (2 ATR) |

#### 3.4 Position Trader Bot (`bot_position.py`)
| Parameter | Value |
|-----------|-------|
| Timeframes | 4H, 1D |
| Hold Duration | 1-4 weeks |
| Target R:R | 10R |
| Risk per Trade | 2% |
| Max Concurrent | 2 |
| Entry Method | Scale-in allowed |

#### 3.5 Sniper Bot (`bot_sniper.py`)
| Parameter | Value |
|-----------|-------|
| Timeframes | Any |
| Confidence Required | 85%+ |
| Target R:R | 15-20R |
| Risk per Trade | 5% (high conviction) |
| Max Concurrent | 1 |
| Entry Method | Limit orders only |

---

### 4. EXECUTION & RISK MICROSERVICES

#### 4.1 Position Sizer (`position_sizer.py`)
- **Kelly Criterion** for optimal sizing
- **Correlation check** (no >70% correlated positions)
- **Volatility adjustment** (reduce size in high ATR)

#### 4.2 Risk Manager (`risk_manager.py`)
- **Daily drawdown limit:** 15%
- **Weekly drawdown limit:** 25%
- **Max single trade:** 5%
- **Max open positions:** 8 total (across all bots)
- **Pause triggers:** Auto-pause on limits

#### 4.3 Execution Engine (`execution_engine.py`)
- **Order types:** Market, Limit, Stop
- **Slippage protection:** Max 0.5 ATR
- **Partial exits:** Take 50% at 2R, trail rest
- **Session handling:** Token refresh, retry logic

---

### 5. SELF-LEARNING MICROSERVICES

#### 5.1 Trade Analyzer (`trade_analyzer.py`)
- Analyze every closed trade
- Track metrics by: setup, day, hour, session, market condition
- Identify degrading and improving setups

#### 5.2 ML Model Trainer (`ml_trainer.py`)
- **Pattern Model:** CNN for candlestick patterns
- **Entry Model:** XGBoost for entry probability
- **Exit Model:** RL agent for dynamic TP/SL
- **Regime Model:** HMM for market state detection
- **Training:** Weekly retraining with new data

#### 5.3 Strategy Optimizer (`strategy_optimizer.py`)
- **Parameter tuning:** Walk-forward optimization
- **A/B testing:** Compare old vs new parameters
- **Promotion logic:** Auto-update if 20% improvement
- **Demotion logic:** Disable setup if win rate drops 20%

#### 5.4 Feedback Loop (`feedback_loop.py`)
- Continuous learning controller
- Updates signal weights based on recent performance
- Adjusts risk parameters dynamically
- Weekly performance reports with recommendations

---

## DATABASE SCHEMA

```sql
-- Symbols table
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    name VARCHAR(10) UNIQUE NOT NULL,  -- XAUUSD, XAGUSD
    description TEXT,
    pip_value DECIMAL,
    min_lot DECIMAL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- OHLCV Data (partitioned by timeframe)
CREATE TABLE price_data (
    id BIGSERIAL,
    symbol_id INTEGER REFERENCES symbols(id),
    timeframe VARCHAR(10) NOT NULL,  -- MINUTE, MINUTE_5, MINUTE_15, HOUR, HOUR_4, DAY
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL NOT NULL,
    high DECIMAL NOT NULL,
    low DECIMAL NOT NULL,
    close DECIMAL NOT NULL,
    volume DECIMAL,
    PRIMARY KEY (id, timeframe)
) PARTITION BY LIST (timeframe);

-- Create partitions for each timeframe
CREATE TABLE price_data_1m PARTITION OF price_data FOR VALUES IN ('MINUTE');
CREATE TABLE price_data_5m PARTITION OF price_data FOR VALUES IN ('MINUTE_5');
CREATE TABLE price_data_15m PARTITION OF price_data FOR VALUES IN ('MINUTE_15');
CREATE TABLE price_data_1h PARTITION OF price_data FOR VALUES IN ('HOUR');
CREATE TABLE price_data_4h PARTITION OF price_data FOR VALUES IN ('HOUR_4');
CREATE TABLE price_data_1d PARTITION OF price_data FOR VALUES IN ('DAY');

-- Indicators (calculated)
CREATE TABLE indicators (
    id BIGSERIAL PRIMARY KEY,
    price_data_id BIGINT NOT NULL,
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
    vwap DECIMAL
);

-- Signals table
CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER REFERENCES symbols(id),
    timestamp TIMESTAMP NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    direction VARCHAR(4) NOT NULL,  -- BUY, SELL
    setup_name VARCHAR(100) NOT NULL,
    conditions JSONB,
    confidence DECIMAL NOT NULL,
    tier VARCHAR(1) NOT NULL,  -- A, B, C
    target_bot VARCHAR(20),  -- scalper, day_trader, swing, position, sniper
    entry_price DECIMAL,
    stop_loss DECIMAL,
    take_profit DECIMAL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, active, executed, expired, cancelled
    created_at TIMESTAMP DEFAULT NOW()
);

-- Trades table
CREATE TABLE trades (
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
    pnl_r DECIMAL,  -- P/L in R units
    status VARCHAR(20) DEFAULT 'open',  -- open, closed, cancelled
    opened_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    close_reason VARCHAR(50),  -- tp_hit, sl_hit, manual, trailing, time_exit
    metadata JSONB
);

-- ML Model Performance
CREATE TABLE model_performance (
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

-- Setup Performance Tracking
CREATE TABLE setup_performance (
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
    weight DECIMAL DEFAULT 1.0,  -- Signal weight multiplier
    updated_at TIMESTAMP DEFAULT NOW()
);

-- System State (for resilience)
CREATE TABLE system_state (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(50) UNIQUE NOT NULL,
    last_heartbeat TIMESTAMP,
    status VARCHAR(20),  -- running, paused, stopped, error
    config JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_price_data_symbol_tf_ts ON price_data (symbol_id, timeframe, timestamp DESC);
CREATE INDEX idx_signals_status ON signals (status, timestamp DESC);
CREATE INDEX idx_trades_status ON trades (status, opened_at DESC);
CREATE INDEX idx_trades_bot ON trades (bot_type, opened_at DESC);
```

---

## MESSAGE QUEUE CHANNELS (Redis)

```python
REDIS_CHANNELS = {
    # Real-time price data
    "price:xauusd:1m": "Latest 1-minute candle for gold",
    "price:xagusd:1m": "Latest 1-minute candle for silver",

    # Aggregated candles
    "candles:xauusd:{tf}": "Latest candle for each timeframe",
    "candles:xagusd:{tf}": "Latest candle for each timeframe",

    # Signals
    "signals:gold": "New gold signals",
    "signals:silver": "New silver signals",
    "signals:aggregated": "Final aggregated signals for bots",

    # Bot commands
    "commands:scalper": "Commands for scalper bot",
    "commands:day_trader": "Commands for day trader",
    "commands:swing": "Commands for swing trader",
    "commands:position": "Commands for position trader",
    "commands:sniper": "Commands for sniper bot",

    # System
    "heartbeat:{service}": "Service health heartbeats",
    "alerts": "System alerts and notifications"
}
```

---

## CONFIGURATION

```python
CONFIG = {
    "symbols": {
        "XAUUSD": {
            "name": "Gold",
            "capital_epic": "GOLD",
            "pip_value": 0.01,
            "min_lot": 0.01,
            "typical_spread": 0.30,
            "trading_hours": "24/5"
        },
        "XAGUSD": {
            "name": "Silver",
            "capital_epic": "SILVER",
            "pip_value": 0.001,
            "min_lot": 0.1,
            "typical_spread": 0.02,
            "trading_hours": "24/5"
        }
    },

    "timeframes": {
        "MINUTE": {"seconds": 60, "retention_days": 7},
        "MINUTE_5": {"seconds": 300, "retention_days": 30},
        "MINUTE_15": {"seconds": 900, "retention_days": 60},
        "HOUR": {"seconds": 3600, "retention_days": 180},
        "HOUR_4": {"seconds": 14400, "retention_days": 365},
        "DAY": {"seconds": 86400, "retention_days": 1095}
    },

    "bots": {
        "scalper": {
            "enabled": True,
            "timeframes": ["MINUTE", "MINUTE_5"],
            "min_confidence": 0.60,
            "risk_pct": 0.01,
            "max_concurrent": 3,
            "target_rr": 5.0,
            "max_hold_minutes": 60
        },
        "day_trader": {
            "enabled": True,
            "timeframes": ["MINUTE_5", "MINUTE_15", "HOUR"],
            "min_confidence": 0.55,
            "risk_pct": 0.02,
            "max_concurrent": 4,
            "target_rr": 3.0,
            "close_before_day_end": True
        },
        "swing": {
            "enabled": True,
            "timeframes": ["HOUR", "HOUR_4"],
            "min_confidence": 0.50,
            "risk_pct": 0.03,
            "max_concurrent": 3,
            "target_rr": 5.0,
            "trailing_stop": True
        },
        "position": {
            "enabled": True,
            "timeframes": ["HOUR_4", "DAY"],
            "min_confidence": 0.55,
            "risk_pct": 0.02,
            "max_concurrent": 2,
            "target_rr": 10.0,
            "scale_in": True
        },
        "sniper": {
            "enabled": True,
            "timeframes": ["ALL"],
            "min_confidence": 0.85,
            "risk_pct": 0.05,
            "max_concurrent": 1,
            "target_rr": 20.0,
            "limit_orders_only": True
        }
    },

    "risk": {
        "max_daily_drawdown": 0.15,
        "max_weekly_drawdown": 0.25,
        "max_total_exposure": 0.20,
        "max_correlation": 0.70,
        "pause_on_consecutive_losses": 5
    },

    "ml": {
        "retrain_frequency": "weekly",
        "min_trades_for_update": 50,
        "ab_test_duration_days": 14,
        "promotion_threshold": 0.20,
        "demotion_threshold": -0.20
    }
}
```

---

## SELF-LEARNING SYSTEM WORKFLOW

### How It Works on Your VM

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SELF-LEARNING FEEDBACK LOOP                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   1. TRADE EXECUTION                                                │
│      └─▶ Bot executes trade based on signal                        │
│                                                                      │
│   2. OUTCOME RECORDING                                              │
│      └─▶ Trade result stored with full context                     │
│          • Entry conditions, market state, indicators               │
│          • Exit reason, P/L, hold time, R multiple                  │
│                                                                      │
│   3. DAILY ANALYSIS (7 PM UTC)                                      │
│      └─▶ Trade Analyzer runs:                                       │
│          • Win rate by setup, day, hour, session                    │
│          • Degrading setup detection                                │
│          • Improving setup identification                           │
│                                                                      │
│   4. WEEKLY ML TRAINING (Sunday 2 AM UTC)                           │
│      └─▶ ML Trainer runs:                                           │
│          • Retrain pattern recognition model                        │
│          • Update entry probability model                           │
│          • Fine-tune exit RL agent                                  │
│          • Recalibrate regime detector                              │
│                                                                      │
│   5. A/B TESTING (Continuous)                                       │
│      └─▶ Strategy Optimizer:                                        │
│          • New model runs on 30% of signals                         │
│          • Compare against production model                         │
│          • Promote if 20%+ improvement over 2 weeks                 │
│                                                                      │
│   6. WEIGHT UPDATES (Weekly)                                        │
│      └─▶ Feedback Loop Controller:                                  │
│          • Increase weights for setups with improved win rate       │
│          • Decrease weights for degrading setups                    │
│          • Disable setups below 30% win rate                        │
│          • Re-enable previously disabled if improved                │
│                                                                      │
│   7. PARAMETER ADJUSTMENT (Monthly)                                 │
│      └─▶ Walk-forward optimization:                                 │
│          • Test new R:R ratios, stop distances                      │
│          • Validate with out-of-sample data                         │
│          • Update config if significant improvement                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Continuous Improvement Metrics

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| Overall Win Rate | 70% | Increase min confidence threshold |
| Profit Factor | 2.0+ | Adjust R:R ratios |
| Max Drawdown | <15% | Reduce position sizes |
| Sharpe Ratio | >2.0 | Review volatility adjustments |
| Recovery Factor | >3.0 | Tighten stop losses |

---

## VM DEPLOYMENT ARCHITECTURE

```
/home/trader/algo_trading/
├── config/
│   ├── main_config.json       # Main configuration
│   ├── symbols.json           # Symbol definitions
│   └── secrets.json           # API keys (gitignored)
│
├── services/
│   ├── data/
│   │   ├── data_collector.py
│   │   ├── timeframe_aggregator.py
│   │   └── indicator_calculator.py
│   │
│   ├── signals/
│   │   ├── base_signal_generator.py
│   │   ├── gold_signal_generator.py
│   │   ├── silver_signal_generator.py
│   │   └── signal_aggregator.py
│   │
│   ├── bots/
│   │   ├── base_trading_bot.py
│   │   ├── bot_scalper.py
│   │   ├── bot_day_trader.py
│   │   ├── bot_swing.py
│   │   ├── bot_position.py
│   │   └── bot_sniper.py
│   │
│   ├── execution/
│   │   ├── position_sizer.py
│   │   ├── risk_manager.py
│   │   └── execution_engine.py
│   │
│   ├── learning/
│   │   ├── trade_analyzer.py
│   │   ├── ml_trainer.py
│   │   ├── strategy_optimizer.py
│   │   └── feedback_loop.py
│   │
│   └── infrastructure/
│       ├── message_queue.py
│       ├── api_gateway.py
│       ├── telegram_commander.py
│       └── monitoring.py
│
├── models/
│   ├── pattern_cnn/
│   ├── entry_xgboost/
│   ├── exit_rl/
│   └── regime_hmm/
│
├── systemd/
│   ├── data-collector.service
│   ├── signal-generator.service
│   ├── bot-scalper.service
│   ├── bot-day-trader.service
│   ├── bot-swing.service
│   ├── bot-position.service
│   ├── bot-sniper.service
│   ├── ml-trainer.service
│   └── ml-trainer.timer
│
├── scripts/
│   ├── deploy.sh
│   ├── start_all.sh
│   ├── stop_all.sh
│   └── health_check.sh
│
└── logs/
    ├── data/
    ├── signals/
    ├── bots/
    └── learning/
```

---

## NEXT STEPS

1. **Phase 1:** Build Data Pipeline (data collector, aggregator, indicators)
2. **Phase 2:** Build Signal Generators (gold, silver, aggregator)
3. **Phase 3:** Build Trading Bots (scalper first, then others)
4. **Phase 4:** Build Risk & Execution Layer
5. **Phase 5:** Build Self-Learning System
6. **Phase 6:** Integration Testing
7. **Phase 7:** Deploy to VM with systemd services
8. **Phase 8:** Monitor and refine daily

---

*"The market is a device for transferring money from the impatient to the patient." - Warren Buffett*
