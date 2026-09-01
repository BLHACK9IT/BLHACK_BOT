from __future__ import annotations

import numpy as np
import pandas as pd


class FeatureEngineer:
    """
    Scalping V1 Feature Engineering Layer.

    PURPOSE
    -------
    Converts normalized OHLCV market data into the feature set used
    by the strategy pipeline.

    DESIGN RULES
    ------------
    1. Never crash because the DataFrame is empty.
    2. Never silently invent OHLC prices.
    3. Missing optional volume data must not crash the pipeline.
    4. Insufficient historical candles must produce NaN, not an error.
    5. No global dropna() is performed.
    6. Feature order is intentional.
    7. No future candle information may be used by a feature.
    8. Existing input columns are preserved unless a feature intentionally
       updates/adds the same named column.
    """

    # ============================================================
    # REQUIRED INPUT COLUMNS
    # ============================================================

    REQUIRED_COLUMNS = {
        "open",
        "high",
        "low",
        "close",
    }

    # ============================================================
    # PUBLIC PIPELINE
    # ============================================================

    @staticmethod
    def apply_all_features(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Apply the complete Scalping V1 feature pipeline.

        Execution order:

            1. Validate input
            2. Handle empty dataset
            3. Price structure
            4. Trend
            5. Volatility
            6. Momentum
            7. Volume
            8. Auxiliary indicators

        IMPORTANT
        ---------
        The function intentionally does NOT call dropna().

        Early rows will naturally contain NaN values because indicators
        such as EMA, ATR, RSI, and moving averages require historical
        candles.

        Empty input is treated as a valid "no data" state.
        """

        # --------------------------------------------------------
        # STEP 1: Validate the DataFrame itself and required columns.
        #
        # This catches malformed input early.
        # --------------------------------------------------------

        FeatureEngineer._validate_input(df)

        # --------------------------------------------------------
        # STEP 2: Empty DataFrame is NOT an error.
        #
        # This is important for the full pipeline:
        #
        # DataFetcher
        #      ↓
        # Normalizer
        #      ↓
        # FeatureEngineer
        #
        # If the fetcher returns zero candles, the system should
        # safely return an empty result instead of crashing.
        # --------------------------------------------------------

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Input must be a DataFrame")

        if df.empty:
            return df.copy()

        # --------------------------------------------------------
        # Work on a copy so the caller's DataFrame is not modified
        # unexpectedly.
        # --------------------------------------------------------

        result = df.copy()

        # --------------------------------------------------------
        # STEP 3: Make OHLC columns numerically usable.
        #
        # Invalid numeric values become NaN instead of causing
        # arithmetic operations to fail.
        # --------------------------------------------------------

        result = FeatureEngineer._coerce_price_columns(result)

        # --------------------------------------------------------
        # STEP 4: Price structure
        #
        # Must run before volatility because volatility can use
        # candle_range.
        # --------------------------------------------------------

        result = FeatureEngineer.add_price_structure_features(result)

        # --------------------------------------------------------
        # STEP 5: Trend
        # --------------------------------------------------------

        result = FeatureEngineer.add_trend_features(result)

        # --------------------------------------------------------
        # STEP 6: Volatility
        # --------------------------------------------------------

        result = FeatureEngineer.add_volatility_features(result)

        # --------------------------------------------------------
        # STEP 7: Momentum
        # --------------------------------------------------------

        result = FeatureEngineer.add_momentum_features(result)

        # --------------------------------------------------------
        # STEP 8: Volume
        #
        # Volume is optional because some market feeds do not
        # provide exchange volume.
        # --------------------------------------------------------

        result = FeatureEngineer.add_volume_features(result)

        # --------------------------------------------------------
        # STEP 9: Auxiliary indicators
        #
        # Currently includes RSI.
        # --------------------------------------------------------

        result = FeatureEngineer.add_auxiliary_features(result)

        return result

    # ============================================================
    # VALIDATION
    # ============================================================

    @staticmethod
    def _validate_input(
        df: pd.DataFrame,
    ) -> None:
        """
        Validate the basic DataFrame contract.

        Empty DataFrames are allowed.

        However, a non-empty DataFrame must contain the required
        OHLC columns because those prices are fundamental to every
        downstream feature.
        """

        if not isinstance(df, pd.DataFrame):
            raise TypeError("FeatureEngineer input must be a pandas DataFrame.")

        # Empty DataFrames are valid.
        if df.empty:
            return

        missing_columns = FeatureEngineer.REQUIRED_COLUMNS - set(df.columns)

        if missing_columns:
            raise ValueError(
                "FeatureEngineer input is missing required columns: "
                f"{sorted(missing_columns)}"
            )

    # ============================================================
    # PRICE COLUMN CLEANUP
    # ============================================================

    @staticmethod
    def _coerce_price_columns(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert OHLC columns to numeric values.

        Invalid values become NaN.

        We deliberately do not fill invalid prices with artificial
        values because doing so could create fake market data.
        """

        result = df.copy()

        for column in (
            "open",
            "high",
            "low",
            "close",
        ):
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        return result

    # ============================================================
    # TREND FEATURES
    # ============================================================

    @staticmethod
    def add_trend_features(
        df: pd.DataFrame,
        fast_period: int = 9,
        slow_period: int = 21,
    ) -> pd.DataFrame:
        """
        Add EMA-based trend features.

        Features
        --------
        ema_9
            Fast exponential moving average.

        ema_21
            Slow exponential moving average.

        ema_separation
            Absolute distance between fast and slow EMA.

        ema_separation_pct
            EMA separation relative to current close.

        price_to_ema_fast
            Distance between close and fast EMA.

        price_to_ema_fast_pct
            Price distance from fast EMA as a percentage.

        ema_fast_slope
            Fast EMA change over three candles.

        ema_fast_slope_pct
            Fast EMA slope relative to current price.

        No future candle information is used.
        """

        result = df.copy()

        # --------------------------------------------------------
        # Fast EMA
        # --------------------------------------------------------

        result[f"ema_{fast_period}"] = (
            result["close"]
            .ewm(
                span=fast_period,
                adjust=False,
                min_periods=fast_period,
            )
            .mean()
        )

        # --------------------------------------------------------
        # Slow EMA
        # --------------------------------------------------------

        result[f"ema_{slow_period}"] = (
            result["close"]
            .ewm(
                span=slow_period,
                adjust=False,
                min_periods=slow_period,
            )
            .mean()
        )

        fast_ema = result[f"ema_{fast_period}"]
        slow_ema = result[f"ema_{slow_period}"]

        # --------------------------------------------------------
        # EMA separation
        # --------------------------------------------------------

        result["ema_separation"] = fast_ema - slow_ema

        result["ema_separation_pct"] = (
            result["ema_separation"] / result["close"]
        ) * 100

        # --------------------------------------------------------
        # Price relative to fast EMA
        # --------------------------------------------------------

        result["price_to_ema_fast"] = result["close"] - fast_ema

        result["price_to_ema_fast_pct"] = (
            result["price_to_ema_fast"] / result["close"]
        ) * 100

        # --------------------------------------------------------
        # EMA slope
        #
        # diff(3) means:
        #
        # current EMA - EMA three candles ago
        #
        # It does NOT inspect future candles.
        # --------------------------------------------------------

        slope_period = 3

        result["ema_fast_slope"] = fast_ema.diff(slope_period) / slope_period

        result["ema_fast_slope_pct"] = (
            result["ema_fast_slope"] / result["close"]
        ) * 100

        return result

    # ============================================================
    # VOLATILITY FEATURES
    # ============================================================

    @staticmethod
    def add_volatility_features(
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.DataFrame:
        """
        Add volatility features.

        Features
        --------
        true_range
            Current candle's True Range.

        atr
            Simple rolling ATR over the configured period.

        atr_pct
            ATR relative to current close.

        range_to_atr
            Current candle range divided by ATR.

        Price structure is calculated before this method, so
        candle_range is expected to already exist.
        """

        result = df.copy()

        # --------------------------------------------------------
        # True Range components
        # --------------------------------------------------------

        high_low = result["high"] - result["low"]

        high_close = (result["high"] - result["close"].shift(1)).abs()

        low_close = (result["low"] - result["close"].shift(1)).abs()

        ranges = pd.concat(
            [
                high_low,
                high_close,
                low_close,
            ],
            axis=1,
        )

        true_range = ranges.max(axis=1)

        result["true_range"] = true_range

        # --------------------------------------------------------
        # ATR
        #
        # The first `period - 1` rows naturally remain NaN.
        # That is expected and should NOT crash the pipeline.
        # --------------------------------------------------------

        result["atr"] = true_range.rolling(
            window=period,
            min_periods=period,
        ).mean()

        # --------------------------------------------------------
        # ATR percentage
        # --------------------------------------------------------

        result["atr_pct"] = (result["atr"] / result["close"]) * 100

        # --------------------------------------------------------
        # Price structure should already have created this.
        #
        # We keep a defensive fallback here because this method
        # can still be called independently during testing.
        #
        # This does NOT affect the normal pipeline order.
        # --------------------------------------------------------

        if "candle_range" not in result.columns:
            result["candle_range"] = result["high"] - result["low"]

        # --------------------------------------------------------
        # Candle range relative to ATR.
        #
        # If ATR is zero or NaN, pandas naturally produces NaN.
        # That is preferable to crashing.
        # --------------------------------------------------------

        result["range_to_atr"] = result["candle_range"] / result["atr"]

        return result

    # ============================================================
    # MOMENTUM FEATURES
    # ============================================================

    @staticmethod
    def add_momentum_features(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Add price-return and ATR-normalized momentum features.

        Features
        --------
        return_1c
        return_3c
        return_5c

        mom_1c_atr
        mom_3c_atr
        mom_5c_atr

        Insufficient history results in NaN.
        """

        result = df.copy()

        # --------------------------------------------------------
        # Ensure ATR exists when this method is called directly.
        # --------------------------------------------------------

        if "atr" not in result.columns:
            result = FeatureEngineer.add_volatility_features(result)

        # --------------------------------------------------------
        # Percentage returns
        # --------------------------------------------------------

        result["return_1c"] = result["close"].pct_change(periods=1)

        result["return_3c"] = result["close"].pct_change(periods=3)

        result["return_5c"] = result["close"].pct_change(periods=5)

        # --------------------------------------------------------
        # ATR-normalized momentum
        #
        # This expresses movement in volatility units instead
        # of raw price units.
        # --------------------------------------------------------

        result["mom_1c_atr"] = (result["close"] - result["close"].shift(1)) / result[
            "atr"
        ]

        result["mom_3c_atr"] = (result["close"] - result["close"].shift(3)) / result[
            "atr"
        ]

        result["mom_5c_atr"] = (result["close"] - result["close"].shift(5)) / result[
            "atr"
        ]

        return result

    # ============================================================
    # VOLUME FEATURES
    # ============================================================

    @staticmethod
    def add_volume_features(
        df: pd.DataFrame,
        period: int = 20,
    ) -> pd.DataFrame:
        """
        Add volume-based features.

        Features
        --------
        volume
            Numeric volume when supplied by the data source.

        volume_type
            Metadata describing the volume source.

        vol_ma
            Rolling average volume.

        rvol
            Relative volume.

        IMPORTANT
        ---------
        Volume is optional.

        If the data source does not provide volume, the method
        creates a NaN volume series rather than crashing.
        """

        result = df.copy()

        # --------------------------------------------------------
        # Missing volume is allowed.
        # --------------------------------------------------------

        if "volume" not in result.columns:
            result["volume"] = pd.Series(
                np.nan,
                index=result.index,
                dtype="float64",
            )

        result["volume"] = pd.to_numeric(
            result["volume"],
            errors="coerce",
        )

        # --------------------------------------------------------
        # Preserve volume source metadata.
        # --------------------------------------------------------

        if "volume_type" not in result.columns:
            result["volume_type"] = "unknown"

        # --------------------------------------------------------
        # Determine whether any usable volume exists.
        # --------------------------------------------------------

        has_volume = result["volume"].notna().any()

        # --------------------------------------------------------
        # No usable volume:
        #
        # Do not crash.
        # Return explicit unavailable values.
        # --------------------------------------------------------

        if not has_volume:
            result["vol_ma"] = pd.Series(
                np.nan,
                index=result.index,
                dtype="float64",
            )

            result["rvol"] = pd.Series(
                np.nan,
                index=result.index,
                dtype="float64",
            )

            return result

        # --------------------------------------------------------
        # Rolling volume average.
        # --------------------------------------------------------

        result["vol_ma"] = (
            result["volume"]
            .rolling(
                window=period,
                min_periods=period,
            )
            .mean()
        )

        # --------------------------------------------------------
        # Relative volume.
        # --------------------------------------------------------

        result["rvol"] = result["volume"] / result["vol_ma"]

        # --------------------------------------------------------
        # Avoid division by zero.
        # --------------------------------------------------------

        result.loc[
            result["vol_ma"] == 0,
            "rvol",
        ] = np.nan

        return result

    # ============================================================
    # AUXILIARY FEATURES
    # ============================================================

    @staticmethod
    def add_auxiliary_features(
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.DataFrame:
        """
        Add auxiliary momentum/condition features.

        Currently provides RSI.

        RSI is calculated using rolling average gains and losses.
        """

        result = df.copy()

        # --------------------------------------------------------
        # Price change.
        # --------------------------------------------------------

        delta = result["close"].diff()

        # --------------------------------------------------------
        # Positive movement.
        # --------------------------------------------------------

        gain = (
            delta.where(
                delta > 0,
                0.0,
            )
            .rolling(
                window=period,
                min_periods=period,
            )
            .mean()
        )

        # --------------------------------------------------------
        # Negative movement.
        # --------------------------------------------------------

        loss = (
            (-delta)
            .where(
                delta < 0,
                0.0,
            )
            .rolling(
                window=period,
                min_periods=period,
            )
            .mean()
        )

        # --------------------------------------------------------
        # Relative strength.
        #
        # A zero loss is handled separately below.
        # --------------------------------------------------------

        rs = gain.div(
            loss.replace(
                0,
                np.nan,
            )
        )

        # --------------------------------------------------------
        # RSI.
        # --------------------------------------------------------

        result["rsi"] = 100 - (100 / (1 + rs))

        # --------------------------------------------------------
        # If there are gains but no losses, RSI is 100.
        # --------------------------------------------------------

        result.loc[
            (loss == 0) & (gain > 0),
            "rsi",
        ] = 100

        return result

    # ============================================================
    # PRICE STRUCTURE FEATURES
    # ============================================================

    @staticmethod
    def add_price_structure_features(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Add candle and swing-structure features.

        Features
        --------
        candle_range
        body_size
        upper_wick
        lower_wick
        body_ratio
        upper_wick_ratio
        lower_wick_ratio
        close_location
        swing_high
        swing_low
        confirmed_swing_high_price
        confirmed_swing_low_price

        IMPORTANT
        ---------
        Swing confirmation is deliberately delayed by one candle.

        This prevents the feature from treating a swing as known
        before the required neighboring candle information exists.
        """

        result = df.copy()

        # --------------------------------------------------------
        # Candle range
        # --------------------------------------------------------

        result["candle_range"] = result["high"] - result["low"]

        # --------------------------------------------------------
        # Candle body
        # --------------------------------------------------------

        result["body_size"] = (result["close"] - result["open"]).abs()

        # --------------------------------------------------------
        # Upper wick
        # --------------------------------------------------------

        result["upper_wick"] = result["high"] - result[["open", "close"]].max(axis=1)

        # --------------------------------------------------------
        # Lower wick
        # --------------------------------------------------------

        result["lower_wick"] = result[["open", "close"]].min(axis=1) - result["low"]

        # --------------------------------------------------------
        # Body ratio
        #
        # If candle range is zero, ratio is undefined.
        # Return NaN rather than divide by zero.
        # --------------------------------------------------------

        result["body_ratio"] = np.where(
            result["candle_range"] == 0,
            np.nan,
            result["body_size"] / result["candle_range"],
        )

        # --------------------------------------------------------
        # Upper wick ratio
        # --------------------------------------------------------

        result["upper_wick_ratio"] = np.where(
            result["candle_range"] == 0,
            np.nan,
            result["upper_wick"] / result["candle_range"],
        )

        # --------------------------------------------------------
        # Lower wick ratio
        # --------------------------------------------------------

        result["lower_wick_ratio"] = np.where(
            result["candle_range"] == 0,
            np.nan,
            result["lower_wick"] / result["candle_range"],
        )

        # --------------------------------------------------------
        # Close location.
        #
        # 0 = close near low
        # 1 = close near high
        # --------------------------------------------------------

        result["close_location"] = np.where(
            result["candle_range"] == 0,
            np.nan,
            (result["close"] - result["low"]) / result["candle_range"],
        )

        # ========================================================
        # SWING HIGH / LOW CANDIDATES
        # ========================================================

        # --------------------------------------------------------
        # A candle is a candidate swing high when its high is
        # greater than the previous and next candle's high.
        #
        # Notice the shift below. The strategy does NOT use this
        # information on the same candle where the candidate is
        # formed.
        # --------------------------------------------------------

        swing_high_candidate = (result["high"] > result["high"].shift(1)) & (
            result["high"] > result["high"].shift(-1)
        )

        # --------------------------------------------------------
        # Swing low candidate.
        # --------------------------------------------------------

        swing_low_candidate = (result["low"] < result["low"].shift(1)) & (
            result["low"] < result["low"].shift(-1)
        )

        # ========================================================
        # CONFIRMED SWINGS
        # ========================================================

        # --------------------------------------------------------
        # Shift by one candle so the swing becomes available only
        # after confirmation.
        # --------------------------------------------------------

        result["swing_high"] = swing_high_candidate.shift(1).fillna(False).astype(bool)

        result["swing_low"] = swing_low_candidate.shift(1).fillna(False).astype(bool)

        # --------------------------------------------------------
        # Confirmed swing prices.
        # --------------------------------------------------------

        result["confirmed_swing_high_price"] = (
            result["high"].shift(1).where(result["swing_high"])
        )

        result["confirmed_swing_low_price"] = (
            result["low"].shift(1).where(result["swing_low"])
        )

        return result
