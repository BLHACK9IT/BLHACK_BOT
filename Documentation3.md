**Master Feature Specification & Architectural Blueprint**

* **EMA Structure (Trend):** Tracks trend direction, slope, separation, and price positioning relative to fast and slow exponential moving averages across all timeframes (1H bias, 15M regime, 5M setup, 1M entry) to evaluate structural strength rather than relying on basic crossover signals.
* **VWMA (Volume-Weighted Moving Average):** Integrates volume intensity into trend tracking to weight price action by market activity, utilizing true exchange volume for stocks/crypto and tick frequency volume for FX/metals.
* **ATR (Volatility Engine):** Measures market movement intensity to serve as a foundational input for dynamic stop-losses, target distances, position sizing, and underlying volatility regimes.
* **Momentum / Returns:** Directly measures multi-period price returns (1-candle, 3-candle, and 5-candle) adjusted and normalized by ATR to accurately interpret percentage moves relative to current market volatility conditions.
* **RSI (Auxiliary Momentum):** Maintained strictly as an optional secondary tool to gauge momentum strength, exhaustion, or pullback conditions within a higher-timeframe trend without any independent veto or trade execution power.
* **Candle & Price Structure:** Derives structural metrics for every completed candle (body size, range, wick ratios, close location) alongside swing highs/lows and market structure markers (higher highs, lower lows) to evaluate entry quality down to the 1-minute layer.
* **Relative Volume:** Compares current volume against a recent rolling average to spot volume expansions or unusual activity, accounting for the reality that forex and metals rely on tick volume rather than centralized exchange volume.
* **Spread & Cost-to-Volatility Thresholds:** Evaluates current transaction costs against ATR to ensure the system never triggers an entry when market volatility is too compressed relative to transaction costs, preventing instant negative expectancy.
* **Time-of-Day & Session Sessionality Weights:** Encodes temporal phases across London, New York, and Asian liquidity windows to allow downstream strategy engines to automatically filter out low-liquidity chop zones and late-session consolidation.

**Excluded Indicators**
Intentionally omits redundant indicators like MACD, Stochastic, Bollinger Bands, ADX, and Ichimoku to prevent feature duplication and preserve out-of-sample statistical expectancy.

**Architectural Data Flow**
Raw market data feeds directly into `indicators.py` to output raw mathematical metrics, which are then passed downstream to specialized execution layers (`bias_engine.py`, `regime_engine.py`, `setup_engine.py`, `entry_engine.py`, and `edge_engine.py`) for logic validation and statistical edge calculation.

# Scalping Version 1

TREND
├── EMA 9
├── EMA 21
├── EMA separation
├── EMA slope
└── price-to-EMA

VOLATILITY
├── ATR
├── ATR %
└── range / ATR

MOMENTUM
├── 1-candle return
├── 3-candle return
├── 5-candle return
├── 1-candle ATR-normalized momentum
└── 3-candle ATR-normalized momentum

VOLUME — OPTIONAL
├── volume
├── volume_type
└── RVOL

AUXILIARY
└── RSI

PRICE STRUCTURE
├── candle range
├── body size
├── body ratio
├── upper wick
├── lower wick
├── upper wick ratio
├── lower wick ratio
├── close location
├── confirmed swing high
└── confirmed swing low


1. Twelve Data
   ↓
2. DataFetcher
   ↓
3. Normalizer
   ↓
4. Indicators
   ↓
5. Bias → Regime → Setup → Entry
   ↓
6. [DERIV API: READ ACCOUNT DATA] ← DO THIS FIRST
   ↓
7. Risk Manager (uses real account data)
   ↓
8. Order Manager (respects Risk Manager output)
   ↓
9. [DERIV API: PLACE ORDERS]
   ↓
10. Paper Trading Account