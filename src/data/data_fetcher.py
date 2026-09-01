# src/data_fetcher.py

import time
import os
import logging
import pandas as pd

from datetime import datetime, timezone, timedelta
from twelvedata import TDClient

from src.config import MARKET_CATEGORIES

# ============================================================
# LOGGING
# ============================================================

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("TradingBotMaster")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(
        "logs/trading_bot.log", mode="w", encoding="utf-8"
    )

    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)


# ============================================================
# MULTI-ASSET DATA FETCHER
# ============================================================


class MultiAssetDataFetcher:

    def __init__(self, data_api_keys: dict = None):
        """
        Initializes the market data fetcher.

        Responsibilities:
        - Connect to Twelve Data
        - Normalize symbols
        - Fetch OHLCV data
        - Track candle timing
        - Avoid unnecessary API requests
        - Handle volume correctly
        - Maintain candle state
        """

        self.data_api_keys = data_api_keys or {}

        twelve_data_config = self.data_api_keys.get("twelve_data", {})

        self.api_key = twelve_data_config.get("api_key", "")

        # ----------------------------------------------------
        # Twelve Data Client
        # ----------------------------------------------------

        if self.api_key:
            try:
                self.td_client = TDClient(apikey=self.api_key)

                logger.info("✅ Twelve Data client initialized successfully.")

            except Exception as e:
                self.td_client = None

                logger.warning(f"⚠️ Could not initialize Twelve Data client: {e}")

                logger.info("→ Running in offline/placeholder mode.")

        else:
            self.td_client = None

            logger.warning(
                "⚠️ TWELVE_DATA_API_KEY not found. "
                "Running in offline/placeholder mode."
            )

        # ----------------------------------------------------
        # Symbol → Category Mapping
        # ----------------------------------------------------

        self.symbol_category_map = self._build_symbol_lookup()

        # ----------------------------------------------------
        # Candle State
        # ----------------------------------------------------

        self.candle_state = {}

        # ----------------------------------------------------
        # Existing compatibility state
        # ----------------------------------------------------

        self.last_candle_timestamps = {}

        self.init_price = None
        self.init_timestamp = None

        logger.info("📊 MultiAssetDataFetcher initialized.")

    # ========================================================
    # SYMBOL NORMALIZATION
    # ========================================================

    def _normalize_symbol(self, symbol: str) -> str:

        symbol = symbol.strip().upper()

        if len(symbol) == 6 and "/" not in symbol and not symbol.isdigit():
            symbol = f"{symbol[:3]}/{symbol[3:]}"

        return symbol

    # ========================================================
    # BUILD SYMBOL LOOKUP
    # ========================================================

    def _build_symbol_lookup(self) -> dict:

        lookup = {}

        for category, info in MARKET_CATEGORIES.items():

            for symbol in info["symbols"]:

                normalized_symbol = self._normalize_symbol(symbol)

                lookup[normalized_symbol] = category

        return lookup

    # ========================================================
    # GET ASSET CATEGORY
    # ========================================================

    def get_asset_category(self, symbol: str) -> str:

        symbol = self._normalize_symbol(symbol)

        if symbol not in self.symbol_category_map:

            raise ValueError(
                f"Symbol '{symbol}' is not supported "
                f"in the active MARKET_CATEGORIES config."
            )

        return self.symbol_category_map[symbol]

    # ========================================================
    # TIMEFRAME → MINUTES
    # ========================================================

    def _timeframe_to_minutes(self, timeframe: str) -> int:

        tf = str(timeframe).strip().lower()

        timeframe_map = {
            "1min": 1,
            "5min": 5,
            "15min": 15,
            "30min": 30,
            "1h": 60,
            "1hour": 60,
            "2h": 120,
            "4h": 240,
            "1day": 1440,
            "1d": 1440,
        }

        if tf not in timeframe_map:

            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported timeframes: "
                f"{list(timeframe_map.keys())}"
            )

        return timeframe_map[tf]

    # ========================================================
    # GET CURRENT CANDLE OPEN TIME
    # ========================================================

    def _get_current_candle_open_time(
        self, timeframe: str, now: datetime = None
    ) -> datetime:

        if now is None:

            now = datetime.now(timezone.utc)

        minutes = self._timeframe_to_minutes(timeframe)

        if minutes < 1440:

            total_minutes = now.hour * 60 + now.minute

            candle_start_minutes = (total_minutes // minutes) * minutes

            candle_hour = candle_start_minutes // 60
            candle_minute = candle_start_minutes % 60

            return now.replace(
                hour=candle_hour, minute=candle_minute, second=0, microsecond=0
            )

        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ========================================================
    # GET NEXT CANDLE OPEN TIME
    # ========================================================

    def _get_next_candle_open_time(
        self, timeframe: str, now: datetime = None
    ) -> datetime:

        current_open = self._get_current_candle_open_time(timeframe=timeframe, now=now)

        minutes = self._timeframe_to_minutes(timeframe)

        return current_open + timedelta(minutes=minutes)

    # ========================================================
    # INITIALIZE CANDLE STATE
    # ========================================================

    def _initialize_candle_state(self, symbol: str, timeframe: str):

        symbol = self._normalize_symbol(symbol)

        now = datetime.now(timezone.utc)

        current_candle = self._get_current_candle_open_time(
            timeframe=timeframe, now=now
        )

        next_candle = self._get_next_candle_open_time(timeframe=timeframe, now=now)

        if symbol not in self.candle_state:

            self.candle_state[symbol] = {}

        if timeframe not in self.candle_state[symbol]:

            self.candle_state[symbol][timeframe] = {
                "last_candle": None,
                "next_check": next_candle,
                "initialized": False,
            }

    # ========================================================
    # DETERMINE WHETHER TIMEFRAME IS DUE
    # ========================================================

    def _is_timeframe_due(self, symbol: str, timeframe: str) -> bool:

        symbol = self._normalize_symbol(symbol)

        self._initialize_candle_state(symbol, timeframe)

        now = datetime.now(timezone.utc)

        state = self.candle_state[symbol][timeframe]

        return now >= state["next_check"]

    # ========================================================
    # MARK TIMEFRAME AS FETCHED
    # ========================================================

    def _mark_timeframe_fetched(
        self, symbol: str, timeframe: str, candle_timestamp=None
    ):

        symbol = self._normalize_symbol(symbol)

        self._initialize_candle_state(symbol, timeframe)

        now = datetime.now(timezone.utc)

        next_candle = self._get_next_candle_open_time(timeframe=timeframe, now=now)

        state = self.candle_state[symbol][timeframe]

        state["last_candle"] = candle_timestamp
        state["next_check"] = next_candle
        state["initialized"] = True

    # ========================================================
    # FETCH DATA
    # ========================================================

    def fetch_data(
        self, symbol: str, timeframe: str, start_date: str = None, outputsize: int = 500
    ) -> pd.DataFrame:
        """
        Fetches historical or incremental data with adjustable outputsize.
        Default is 500 for deep indicator warm-up.
        """

        symbol = self._normalize_symbol(symbol)

        asset_type = self.get_asset_category(symbol)

        logger.info(
            f"Fetching {symbol} → "
            f"Category: {asset_type.upper()} "
            f"| Timeframe: {timeframe} "
            f"| OutputSize: {outputsize}"
        )

        df = self._fetch_twelve_data_timeseries(
            symbol, timeframe, start_date, outputsize=outputsize
        )

        if not df.empty:

            df = self._process_asset_volume(df, symbol)

        return df

    # ========================================================
    # CANDLE-SYNCHRONIZED FETCH
    # ========================================================

    def fetch_candle_synchronized_data(
        self, symbol: str, timeframe: str
    ) -> pd.DataFrame:
        """
        Fetches data using local clock scheduling:
        - Initial fetch pulls 500 bars for complete indicator warm-up.
        - Subsequent loop checks pull a optimized smaller batch (e.g. 10 bars)
          when a candle boundary is reached, avoiding heavy payloads.
        """

        symbol = self._normalize_symbol(symbol)

        self._initialize_candle_state(symbol, timeframe)

        state = self.candle_state[symbol][timeframe]

        # ----------------------------------------------------
        # FIRST RUN (Warm-up buffer: 500 bars)
        # ----------------------------------------------------
        if not state["initialized"]:

            logger.info(
                f"📥 [INITIAL WARM-UP] "
                f"{symbol} ({timeframe}) "
                f"→ Fetching 500 historical bars."
            )

            df = self.fetch_data(symbol=symbol, timeframe=timeframe, outputsize=500)

            if df.empty:
                return df

            latest_timestamp = self._get_latest_timestamp(df)

            self._mark_timeframe_fetched(
                symbol=symbol, timeframe=timeframe, candle_timestamp=latest_timestamp
            )

            self._update_legacy_timestamp_state(symbol, timeframe, latest_timestamp)

            logger.info(
                f"🕯️ [INITIAL CANDLE] "
                f"{symbol} ({timeframe}) "
                f"→ {latest_timestamp}"
            )

            return df

        # ----------------------------------------------------
        # LOCAL CLOCK CHECK (Zero API Cost if not due)
        # ----------------------------------------------------
        if not self._is_timeframe_due(symbol, timeframe):

            return pd.DataFrame()

        logger.info(
            f"⏰ [TIMEFRAME DUE] "
            f"{symbol} ({timeframe}) "
            f"→ Candle boundary reached."
        )

        # ----------------------------------------------------
        # INCREMENTAL UPDATE (Lightweight payload: 10 bars)
        # ----------------------------------------------------
        df = self.fetch_data(symbol=symbol, timeframe=timeframe, outputsize=10)

        if df.empty:

            logger.warning(f"⚠️ No data returned for " f"{symbol} ({timeframe}).")

            return pd.DataFrame()

        latest_timestamp = self._get_latest_timestamp(df)

        previous_timestamp = state["last_candle"]

        if previous_timestamp is not None and latest_timestamp == previous_timestamp:

            logger.info(
                f"⏳ [NO NEW PROVIDER CANDLE] "
                f"{symbol} ({timeframe}) "
                f"→ Provider has not published a new candle yet."
            )

            now = datetime.now(timezone.utc)

            state["next_check"] = now + timedelta(seconds=5)

            return pd.DataFrame()

        self._mark_timeframe_fetched(
            symbol=symbol, timeframe=timeframe, candle_timestamp=latest_timestamp
        )

        self._update_legacy_timestamp_state(symbol, timeframe, latest_timestamp)

        logger.info(
            f"🕯️ [NEW CANDLE CONFIRMED] "
            f"{symbol} ({timeframe}) "
            f"→ {latest_timestamp}"
        )

        return df

    # ========================================================
    # GET LATEST TIMESTAMP
    # ========================================================

    def _get_latest_timestamp(self, df: pd.DataFrame):

        if df.empty:
            return None

        if isinstance(df.index, pd.DatetimeIndex):

            timestamps = pd.to_datetime(df.index, utc=True, errors="coerce")

            timestamps = timestamps[~timestamps.isna()]

            if len(timestamps) == 0:
                return None

            return timestamps.max()

        if "datetime" in df.columns:

            timestamps = pd.to_datetime(df["datetime"], utc=True, errors="coerce")

            timestamps = timestamps[~timestamps.isna()]

            if len(timestamps) == 0:
                return None

            return timestamps.max()

        return None

    # ========================================================
    # LEGACY TIMESTAMP COMPATIBILITY
    # ========================================================

    def _update_legacy_timestamp_state(self, symbol: str, timeframe: str, timestamp):

        if symbol not in self.last_candle_timestamps:

            self.last_candle_timestamps[symbol] = {}

        self.last_candle_timestamps[symbol][timeframe] = str(timestamp)

    # ========================================================
    # MULTI-TIMEFRAME FETCH
    # ========================================================

    def fetch_multi_timeframe_data(
        self, symbol: str, timeframes: dict, start_date: str = None
    ) -> dict:

        symbol = self._normalize_symbol(symbol)

        fetched_dfs = {}

        logger.info(
            f"📥 Pulling Multi-Timeframe stack "
            f"for {symbol}: "
            f"{list(timeframes.values())}"
        )

        for role, tf in timeframes.items():

            df = self.fetch_data(
                symbol=symbol, timeframe=tf, start_date=start_date, outputsize=500
            )

            fetched_dfs[role] = df

            if not df.empty:

                logger.info(f"✅ Success: " f"{role} ({tf}) " f"| Rows: {len(df)}")

            else:

                logger.warning(f"⚠️ Empty dataset: " f"{symbol} [{role} - {tf}]")

        return fetched_dfs

    # ========================================================
    # TWELVE DATA API
    # ========================================================

    def _fetch_twelve_data_timeseries(
        self, symbol: str, timeframe: str, start_date: str, outputsize: int
    ) -> pd.DataFrame:

        if self.td_client:

            try:

                logger.info(
                    f"→ Requesting Twelve Data: "
                    f"{symbol} ({timeframe}) [outputsize={outputsize}]..."
                )

                ts = self.td_client.time_series(
                    symbol=symbol,
                    interval=timeframe,
                    start_date=start_date,
                    outputsize=outputsize,
                    timezone="UTC",
                )

                df = ts.as_pandas()

                if df is None:
                    return pd.DataFrame()

                if df.empty:
                    return pd.DataFrame()

                if isinstance(df.index, pd.DatetimeIndex):

                    df.index = pd.to_datetime(df.index, utc=True, errors="coerce")

                    df = df[~df.index.isna()]

                    df = df.sort_index(ascending=False)

                return df

            except Exception as e:

                logger.error(
                    f"❌ Error fetching Twelve Data " f"for {symbol} ({timeframe}): {e}"
                )

                return pd.DataFrame()

        logger.info(
            f"→ [OFFLINE MODE] "
            f"No Twelve Data client available "
            f"for {symbol} ({timeframe})."
        )

        return pd.DataFrame()

    # ========================================================
    # VOLUME PROCESSING
    # ========================================================

    def _process_asset_volume(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:

        category = self.symbol_category_map.get(symbol, "fx")

        if "volume" in df.columns:

            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

            if category in ["fx", "metal"]:

                df["volume_type"] = "tick_volume"

            elif category in ["crypto", "stock", "stocks"]:

                df["volume_type"] = "exchange_volume"

            else:

                df["volume_type"] = "unknown"

            rolling_mean = df["volume"].rolling(window=20, min_periods=1).mean()

            df["normalized_volume"] = df["volume"] / rolling_mean

        else:

            df["volume"] = pd.Series(float("nan"), index=df.index, dtype="float64")

            df["volume_type"] = "none"

            df["normalized_volume"] = pd.Series(
                float("nan"), index=df.index, dtype="float64"
            )

        return df

    # ========================================================
    # POLL ACTIVE MARKETS
    # ========================================================

    def poll_active_markets(
        self, symbols: list = None, timeframes: dict = None, interval_seconds: int = 5
    ) -> dict:

        polled_results = {}

        target_symbols = symbols if symbols else []

        logger.info(f"--- Polling Cycle: " f"{target_symbols} ---")

        for symbol in target_symbols:

            normalized_symbol = self._normalize_symbol(symbol)

            try:

                if timeframes and isinstance(timeframes, dict):

                    df_dict = {}

                    for role, tf in timeframes.items():

                        df = self.fetch_candle_synchronized_data(
                            symbol=normalized_symbol, timeframe=tf
                        )

                        if not df.empty:

                            df_dict[role] = df

                    if df_dict:

                        polled_results[normalized_symbol] = df_dict

                        logger.info(
                            f"✅ New candle data "
                            f"available for "
                            f"{normalized_symbol}"
                        )

                    else:

                        logger.info(
                            f"💤 No new candles "
                            f"available for "
                            f"{normalized_symbol}"
                        )

                else:

                    tf_str = timeframes if isinstance(timeframes, str) else "1h"

                    df = self.fetch_candle_synchronized_data(
                        symbol=normalized_symbol, timeframe=tf_str
                    )

                    if not df.empty:

                        polled_results[normalized_symbol] = df

            except Exception as e:

                logger.error(f"❌ Error polling " f"{normalized_symbol}: {e}")

        logger.info("--- Polling Cycle Complete ---")

        return polled_results

    # ========================================================
    # WEBSOCKET
    # ========================================================

    def start_live_stream(self, symbols: list):

        if not self.td_client:

            logger.error(
                "⚠️ Cannot start WebSocket. " "Twelve Data client unavailable."
            )

            return

        symbols = [self._normalize_symbol(s) for s in symbols]

        logger.info(f"Connecting to Twelve Data " f"WebSocket: {symbols}")

        def on_event(e):

            if "price" in e and "symbol" in e:

                symbol = e["symbol"]

                price = float(e["price"])

                timestamp = e.get("timestamp", "N/A")

                category = self.symbol_category_map.get(symbol, "unknown")

                if self.init_price is None or self.init_timestamp is None:

                    self.init_price = price
                    self.init_timestamp = timestamp

                    logger.info(
                        f"[ANCHOR SET] "
                        f"{category.upper()} | "
                        f"{symbol} | "
                        f"Base Price: "
                        f"{self.init_price}"
                    )

                price_delta = price - self.init_price

                pct_delta = (
                    (price_delta / self.init_price) * 100 if self.init_price else 0
                )

                logger.info(
                    f"[{category.upper()}] "
                    f"Ticker: {symbol} | "
                    f"Price: {price} | "
                    f"Delta: "
                    f"{price_delta:+.4f} "
                    f"({pct_delta:+.2f}%) | "
                    f"Time: {timestamp}"
                )

            else:

                logger.info(f"[WebSocket Event]: {e}")

        try:

            ws = self.td_client.websocket(symbols=symbols, on_event=on_event)

            ws.connect()
            ws.keep_alive()

        except Exception:

            import traceback

            logger.error(
                "--- CAUGHT WEBSOCKET EXCEPTION ---\n" f"{traceback.format_exc()}"
            )

    # ========================================================
    # CONTINUOUS POLLING LOOP
    # ========================================================

    def start_polling_loop(
        self, symbols: list = None, timeframes: dict = None, interval_seconds: int = 5
    ):

        logger.info(
            "🚀 Starting candle-aware polling engine "
            f"(local check interval: "
            f"{interval_seconds}s)"
        )

        try:

            while True:

                self.poll_active_markets(
                    symbols=symbols,
                    timeframes=timeframes,
                    interval_seconds=interval_seconds,
                )

                time.sleep(interval_seconds)

        except KeyboardInterrupt:

            logger.info(
                "🛑 Polling loop manually stopped. " "Shutting down gracefully."
            )
