# src/strategy/setup_engine.py

"""
====================================================================
5M SETUP ENGINE — SCALPING V1
====================================================================

ROLE
----

The 5M Setup Engine is the structural setup layer of the scalping
pipeline.

Its job is to answer ONE question:

    "Do the higher-timeframe constraints and local 5M price
     structure align strongly enough to form a valid setup?"

The engine sits between:

    1H BIAS
        ↓
    15M REGIME + DIRECTION
        ↓
    5M SETUP ENGINE
        ↓
    1M ENTRY ENGINE

The engine produces setup hypotheses only.

It does NOT:

    - execute orders
    - calculate position size
    - manage open positions
    - communicate with a broker
    - calculate portfolio risk
    - optimize parameters
    - use AI/LLMs
    - determine final execution quality

V1 SETUP HYPOTHESES
-------------------

A. TREND PULLBACK CONTINUATION

    1H bias and 15M direction agree.
    15M regime is TRENDING_EXPANSION.
    5M price interacts with the EMA 9 / EMA 21 value zone.
    The 5M candle provides directional conviction.

B. COMPRESSION BOUNDARY REJECTION

    15M regime is RANGING_COMPRESSION.
    A confirmed 5M structural boundary is available.
    Price interacts with the relevant boundary.
    The candle provides directional rejection/conviction.

OUTPUT STATES
-------------

    LONG_SETUP
    SHORT_SETUP
    NONE

IMPORTANT STATE RULE
--------------------

The engine returns DISCRETE setup EVENTS.

A condition remaining true for several consecutive 5M candles
must not produce repeated LONG_SETUP or SHORT_SETUP events.

Example:

    NONE
    LONG_SETUP
    LONG_SETUP
    LONG_SETUP
    NONE

becomes:

    NONE
    LONG_SETUP
    NONE
    NONE
    NONE

This prevents the downstream 1M entry engine from treating one
structural setup as multiple independent setup events.

HIGHER-TIMEFRAME RULE
---------------------

The 1H bias establishes the macro directional preference.

The 15M regime describes the current operating environment.

The 15M direction describes the current directional state.

The hierarchy is therefore:

    1H BIAS
        ↓
    15M REGIME + DIRECTION
        ↓
    5M STRUCTURE

A 5M setup must not silently fight a strict 1H directional bias.

However, a compression regime is not automatically invalid merely
because the 1H market has a directional bias.

Example:

    1H BULLISH
    15M RANGING_COMPRESSION
    5M bullish boundary rejection

can remain a valid LONG_SETUP hypothesis.

Conversely:

    1H BULLISH
    15M BEARISH
    5M SHORT_SETUP

is rejected because the lower timeframe is attempting to produce
a counter-bias setup without an explicit counter-trend hypothesis.

TIMESTAMP CONTRACT
------------------

Higher-timeframe series are forward-filled onto the 5M timeline.

This is only safe when the supplied HTF timestamps represent the
time at which the corresponding state became available.

The data pipeline is responsible for ensuring:

    - candles are closed before their state is published
    - timestamps use a consistent timezone
    - timestamps represent state availability
    - no future HTF state is supplied to an earlier 5M candle

The Setup Engine intentionally does not perform timezone conversion
or candle reconstruction.

MISSING DATA RULE
-----------------

Missing HTF context is NOT treated as a neutral trading state.

Rows without complete required context remain unevaluable.

This protects the strategy from accidentally treating missing data
as permission to trade.

PARAMETER RULE
--------------

Thresholds are hypotheses.

They are intentionally exposed as parameters so the backtesting
layer can later test them across assets, regimes, and out-of-sample
periods.

The Setup Engine itself does not optimize them.
====================================================================
"""

import pandas as pd


class ScalpingSetupEngine:
    """
    5M structural setup engine for the scalping system.

    The class contains only setup-generation logic.

    It does not execute trades or manage risk.
    """

    # ==============================================================
    # PUBLIC SETUP STATES
    # ==============================================================

    LONG_SETUP = "LONG_SETUP"
    SHORT_SETUP = "SHORT_SETUP"
    NONE = "NONE"

    VALID_SETUPS = {
        LONG_SETUP,
        SHORT_SETUP,
        NONE,
    }

    # ==============================================================
    # VALID HIGHER-TIMEFRAME STATES
    # ==============================================================

    VALID_BIAS = {
        "BULLISH",
        "BEARISH",
        "NEUTRAL",
    }

    VALID_DIRECTIONS = {
        "BULLISH",
        "BEARISH",
        "NEUTRAL",
    }

    VALID_REGIMES = {
        "TRENDING_EXPANSION",
        "RANGING_COMPRESSION",
        "HIGH_VOLATILITY_CHOP",
        "NEUTRAL",
    }

    # ==============================================================
    # REQUIRED 5M FEATURES
    # ==============================================================

    REQUIRED_COLUMNS = {
        "open",
        "high",
        "low",
        "close",
        "ema_9",
        "ema_21",
        "atr",
    }

    # ==============================================================
    # DEFAULT PARAMETERS
    # ==============================================================

    DEFAULT_MIN_BODY_ATR_RATIO = 0.25

    # Maximum distance from a confirmed swing boundary expressed
    # as a fraction of ATR for compression rejection evaluation.
    DEFAULT_BOUNDARY_ATR_BUFFER = 0.50

    # ==============================================================
    # VALIDATION
    # ==============================================================

    @classmethod
    def _validate_dataframe(cls, df: pd.DataFrame) -> None:
        """
        Validate the incoming 5M dataframe.

        The engine requires chronological, unique timestamps and
        the core OHLC + EMA + ATR feature contract.
        """

        if not isinstance(df, pd.DataFrame):
            raise TypeError("df_5m must be a pandas DataFrame.")

        missing = cls.REQUIRED_COLUMNS - set(df.columns)

        if missing:
            raise ValueError(
                "Missing required 5M feature columns: " + ", ".join(sorted(missing))
            )

        if df.index.has_duplicates:
            raise ValueError("df_5m index contains duplicate timestamps.")

        if not df.index.is_monotonic_increasing:
            raise ValueError("df_5m index must be monotonically increasing.")

    @classmethod
    def _validate_htf_series(
        cls,
        series: pd.Series,
        name: str,
        valid_values: set,
    ) -> None:
        """
        Validate one higher-timeframe state series.

        Missing values are allowed because some rows may legitimately
        be unavailable during warm-up. Invalid non-null states are not.
        """

        if not isinstance(series, pd.Series):
            raise TypeError(f"{name} must be a pandas Series.")

        if series.index.has_duplicates:
            raise ValueError(f"{name} index contains duplicate timestamps.")

        if not series.index.is_monotonic_increasing:
            raise ValueError(f"{name} index must be monotonically increasing.")

        values = set(series.dropna().unique())

        invalid = values - valid_values

        if invalid:
            raise ValueError(
                f"{name} contains invalid states: "
                + ", ".join(sorted(map(str, invalid)))
            )

    @classmethod
    def _validate_parameters(
        cls,
        min_body_atr_ratio: float,
        boundary_atr_buffer: float,
    ) -> None:
        """
        Validate configurable setup thresholds.

        These values are research parameters, not proven constants.
        """

        if not isinstance(min_body_atr_ratio, (int, float)):
            raise TypeError("min_body_atr_ratio must be numeric.")

        if min_body_atr_ratio < 0:
            raise ValueError("min_body_atr_ratio must be >= 0.")

        if not isinstance(boundary_atr_buffer, (int, float)):
            raise TypeError("boundary_atr_buffer must be numeric.")

        if boundary_atr_buffer < 0:
            raise ValueError("boundary_atr_buffer must be >= 0.")

    # ==============================================================
    # HIGHER-TIMEFRAME ALIGNMENT
    # ==============================================================

    @staticmethod
    def _align_htf_series(
        series: pd.Series,
        target_index: pd.Index,
    ) -> pd.Series:
        """
        Forward-fill a higher-timeframe state onto the 5M timeline.

        IMPORTANT
        ---------

        This assumes the incoming HTF timestamps represent the moment
        at which the state became available.

        The function does not attempt to infer candle-close timing.

        That responsibility belongs to the data-validation layer.
        """

        return series.reindex(
            target_index,
            method="ffill",
        )

    # ==============================================================
    # CORE EVALUATOR
    # ==============================================================

    @classmethod
    def evaluate_setups(
        cls,
        df_5m: pd.DataFrame,
        bias_1h: pd.Series = None,
        regime_15m: pd.Series = None,
        direction_15m: pd.Series = None,
        min_body_atr_ratio: float = DEFAULT_MIN_BODY_ATR_RATIO,
        boundary_atr_buffer: float = DEFAULT_BOUNDARY_ATR_BUFFER,
    ) -> pd.Series:
        """
        Evaluate 5M setup hypotheses.

        Parameters
        ----------
        df_5m:
            5M feature dataframe.

        bias_1h:
            1H macro bias:
                BULLISH
                BEARISH
                NEUTRAL

        regime_15m:
            15M operating regime:
                TRENDING_EXPANSION
                RANGING_COMPRESSION
                HIGH_VOLATILITY_CHOP
                NEUTRAL

        direction_15m:
            15M directional state:
                BULLISH
                BEARISH
                NEUTRAL

        min_body_atr_ratio:
            Minimum candle body measured relative to ATR.

        boundary_atr_buffer:
            Maximum distance from a confirmed swing boundary,
            expressed as ATR.

        Returns
        -------
        pd.Series

            LONG_SETUP
            SHORT_SETUP
            NONE

        Rows without sufficient data remain None.
        """

        # ----------------------------------------------------------
        # 1. EMPTY INPUT
        # ----------------------------------------------------------

        if df_5m.empty:
            return pd.Series(
                dtype=object,
                index=df_5m.index,
                name="setup",
            )

        # ----------------------------------------------------------
        # 2. VALIDATE INPUTS
        # ----------------------------------------------------------

        cls._validate_dataframe(df_5m)

        if bias_1h is None or regime_15m is None or direction_15m is None:
            raise ValueError(
                "bias_1h, regime_15m, and direction_15m "
                "are all required for setup evaluation."
            )

        cls._validate_htf_series(
            bias_1h,
            "bias_1h",
            cls.VALID_BIAS,
        )

        cls._validate_htf_series(
            regime_15m,
            "regime_15m",
            cls.VALID_REGIMES,
        )

        cls._validate_htf_series(
            direction_15m,
            "direction_15m",
            cls.VALID_DIRECTIONS,
        )

        cls._validate_parameters(
            min_body_atr_ratio,
            boundary_atr_buffer,
        )

        # ----------------------------------------------------------
        # 3. COPY INPUT
        # ----------------------------------------------------------

        df = df_5m.copy()

        # ----------------------------------------------------------
        # 4. INITIAL OUTPUT
        # ----------------------------------------------------------

        raw_setup = pd.Series(
            None,
            index=df.index,
            dtype=object,
            name="setup",
        )

        # ----------------------------------------------------------
        # 5. 5M DATA VALIDATION / WARM-UP
        # ----------------------------------------------------------

        valid_mask = (
            df["open"].notna()
            & df["high"].notna()
            & df["low"].notna()
            & df["close"].notna()
            & df["ema_9"].notna()
            & df["ema_21"].notna()
            & df["atr"].notna()
            & (df["atr"] > 0)
        )

        if not valid_mask.any():
            return raw_setup

        # ----------------------------------------------------------
        # 6. HIGHER-TIMEFRAME ALIGNMENT
        # ----------------------------------------------------------

        h_bias = cls._align_htf_series(
            bias_1h,
            df.index,
        )

        m_regime = cls._align_htf_series(
            regime_15m,
            df.index,
        )

        m_direction = cls._align_htf_series(
            direction_15m,
            df.index,
        )

        # ----------------------------------------------------------
        # 7. HTF DATA AVAILABILITY
        # ----------------------------------------------------------

        htf_available = h_bias.notna() & m_regime.notna() & m_direction.notna()

        evaluable_mask = valid_mask & htf_available

        if not evaluable_mask.any():
            return raw_setup

        # ----------------------------------------------------------
        # 8. CANDLE STRUCTURE
        # ----------------------------------------------------------

        candle_range = df["high"] - df["low"]

        candle_body = (df["close"] - df["open"]).abs()

        conviction_ok = candle_body >= (df["atr"] * min_body_atr_ratio)

        bullish_candle = df["close"] > df["open"]

        bearish_candle = df["close"] < df["open"]

        # ----------------------------------------------------------
        # 9. EMA VALUE ZONE
        # ----------------------------------------------------------

        ema_min = df[["ema_9", "ema_21"]].min(axis=1)

        ema_max = df[["ema_9", "ema_21"]].max(axis=1)

        bullish_pullback_zone = (df["low"] <= ema_max) & (df["close"] > ema_min)

        bearish_pullback_zone = (df["high"] >= ema_min) & (df["close"] < ema_max)

        # ----------------------------------------------------------
        # 10. EXPLICIT HTF DIRECTIONAL CONFLICT RESOLUTION
        # ----------------------------------------------------------
        #
        # Trend continuation requires:
        #
        #     1H BULLISH
        #     15M BULLISH
        #     15M TRENDING_EXPANSION
        #
        # or:
        #
        #     1H BEARISH
        #     15M BEARISH
        #     15M TRENDING_EXPANSION
        #
        # This prevents a lower timeframe trend setup from fighting
        # a strict macro directional bias.
        # ----------------------------------------------------------

        bullish_trend_context = (
            (h_bias == "BULLISH")
            & (m_direction == "BULLISH")
            & (m_regime == "TRENDING_EXPANSION")
        )

        bearish_trend_context = (
            (h_bias == "BEARISH")
            & (m_direction == "BEARISH")
            & (m_regime == "TRENDING_EXPANSION")
        )

        # ----------------------------------------------------------
        # 11. COMPRESSION CONTEXT
        # ----------------------------------------------------------
        #
        # Compression is different from trend continuation.
        #
        # We do not require 15M direction to agree with 1H because
        # the market is explicitly classified as compressed.
        #
        # However, the eventual setup direction must still agree
        # with the 1H macro bias.
        #
        # Therefore:
        #
        #     1H BULLISH + compression → LONG allowed
        #     1H BEARISH + compression → SHORT allowed
        #
        # but:
        #
        #     1H BULLISH + compression → SHORT blocked
        #     1H BEARISH + compression → LONG blocked
        # ----------------------------------------------------------

        bullish_compression_context = (h_bias == "BULLISH") & (
            m_regime == "RANGING_COMPRESSION"
        )

        bearish_compression_context = (h_bias == "BEARISH") & (
            m_regime == "RANGING_COMPRESSION"
        )

        # ----------------------------------------------------------
        # 12. CONFIRMED SWING INFORMATION
        # ----------------------------------------------------------
        #
        # The indicator pipeline may provide confirmed swing prices.
        #
        # Missing swing columns are handled safely because not every
        # data source or feature configuration must provide them.
        # ----------------------------------------------------------

        has_swing_high = "confirmed_swing_high_price" in df.columns

        has_swing_low = "confirmed_swing_low_price" in df.columns

        if has_swing_high:
            swing_high = pd.to_numeric(
                df["confirmed_swing_high_price"],
                errors="coerce",
            )
        else:
            swing_high = pd.Series(
                float("nan"),
                index=df.index,
            )

        if has_swing_low:
            swing_low = pd.to_numeric(
                df["confirmed_swing_low_price"],
                errors="coerce",
            )
        else:
            swing_low = pd.Series(
                float("nan"),
                index=df.index,
            )

        swing_high_available = swing_high.notna()

        swing_low_available = swing_low.notna()

        # ----------------------------------------------------------
        # 13. COMPRESSION BOUNDARY INTERACTION
        # ----------------------------------------------------------

        long_boundary_distance = (df["low"] - swing_low).abs()

        short_boundary_distance = (df["high"] - swing_high).abs()

        long_boundary_touch = swing_low_available & (
            long_boundary_distance <= (df["atr"] * boundary_atr_buffer)
        )

        short_boundary_touch = swing_high_available & (
            short_boundary_distance <= (df["atr"] * boundary_atr_buffer)
        )

        # ----------------------------------------------------------
        # 14. REJECTION STRUCTURE
        # ----------------------------------------------------------
        #
        # A bullish rejection should show:
        #
        #     - interaction with a lower structural boundary
        #     - bullish close
        #     - sufficient body conviction
        #
        # A bearish rejection should show:
        #
        #     - interaction with an upper structural boundary
        #     - bearish close
        #     - sufficient body conviction
        #
        # The candle range must be positive.
        # ----------------------------------------------------------

        valid_range = candle_range > 0

        bullish_rejection = (
            long_boundary_touch & bullish_candle & conviction_ok & valid_range
        )

        bearish_rejection = (
            short_boundary_touch & bearish_candle & conviction_ok & valid_range
        )

        # ----------------------------------------------------------
        # 15. TREND PULLBACK SETUPS
        # ----------------------------------------------------------

        bullish_trend_setup = (
            evaluable_mask
            & bullish_trend_context
            & bullish_pullback_zone
            & conviction_ok
            & bullish_candle
        )

        bearish_trend_setup = (
            evaluable_mask
            & bearish_trend_context
            & bearish_pullback_zone
            & conviction_ok
            & bearish_candle
        )

        # ----------------------------------------------------------
        # 16. COMPRESSION REJECTION SETUPS
        # ----------------------------------------------------------

        bullish_compression_setup = (
            evaluable_mask & bullish_compression_context & bullish_rejection
        )

        bearish_compression_setup = (
            evaluable_mask & bearish_compression_context & bearish_rejection
        )

        # ----------------------------------------------------------
        # 17. COMBINE RAW SETUP HYPOTHESES
        # ----------------------------------------------------------

        bullish_trigger = bullish_trend_setup | bullish_compression_setup

        bearish_trigger = bearish_trend_setup | bearish_compression_setup

        # ----------------------------------------------------------
        # 18. ASSIGN RAW STATES
        # ----------------------------------------------------------

        raw_setup.loc[bullish_trigger] = cls.LONG_SETUP

        raw_setup.loc[bearish_trigger] = cls.SHORT_SETUP

        # ----------------------------------------------------------
        # 19. EXPLICIT VETO OF INVALID CONFLICTS
        # ----------------------------------------------------------
        #
        # This is intentionally explicit.
        #
        # Even if another condition accidentally becomes true,
        # the macro bias still prevents an opposing setup.
        # ----------------------------------------------------------

        invalid_long_bias = evaluable_mask & (h_bias == "BEARISH")

        invalid_short_bias = evaluable_mask & (h_bias == "BULLISH")

        raw_setup.loc[invalid_long_bias & (raw_setup == cls.LONG_SETUP)] = cls.NONE

        raw_setup.loc[invalid_short_bias & (raw_setup == cls.SHORT_SETUP)] = cls.NONE

        # ----------------------------------------------------------
        # 20. NEUTRAL / UNKNOWN CONTEXT VETO
        # ----------------------------------------------------------

        neutral_htf = (
            (h_bias == "NEUTRAL")
            | (m_direction == "NEUTRAL")
            | (m_regime == "NEUTRAL")
            | (m_regime == "HIGH_VOLATILITY_CHOP")
        )

        raw_setup.loc[evaluable_mask & neutral_htf] = cls.NONE

        # ----------------------------------------------------------
        # 21. DEFAULT EVALUATED ROWS TO NONE
        # ----------------------------------------------------------

        evaluated_none = evaluable_mask & raw_setup.isna()

        raw_setup.loc[evaluated_none] = cls.NONE

        # ----------------------------------------------------------
        # 22. DISCRETE EVENT DETECTION
        # ----------------------------------------------------------
        #
        # Continuous conditions are converted into one-shot events.
        #
        # Example:
        #
        #     NONE
        #     LONG_SETUP
        #     LONG_SETUP
        #     LONG_SETUP
        #
        # becomes:
        #
        #     NONE
        #     LONG_SETUP
        #     NONE
        #     NONE
        #
        # This protects the downstream 1M entry engine from treating
        # the same 5M structural event as multiple new opportunities.
        # ----------------------------------------------------------

        previous_state = raw_setup.shift(1)

        discrete_setup = raw_setup.copy()

        repeated_long = (raw_setup == cls.LONG_SETUP) & (
            previous_state == cls.LONG_SETUP
        )

        repeated_short = (raw_setup == cls.SHORT_SETUP) & (
            previous_state == cls.SHORT_SETUP
        )

        discrete_setup.loc[repeated_long] = cls.NONE

        discrete_setup.loc[repeated_short] = cls.NONE

        # ----------------------------------------------------------
        # 23. PRESERVE UNEVALUABLE ROWS
        # ----------------------------------------------------------

        discrete_setup.loc[~evaluable_mask] = None

        discrete_setup.name = "setup"

        return discrete_setup

    # ==============================================================
    # DIAGNOSTIC EVALUATOR
    # ==============================================================

    @classmethod
    def evaluate_with_diagnostics(
        cls,
        df_5m: pd.DataFrame,
        bias_1h: pd.Series = None,
        regime_15m: pd.Series = None,
        direction_15m: pd.Series = None,
        min_body_atr_ratio: float = DEFAULT_MIN_BODY_ATR_RATIO,
        boundary_atr_buffer: float = DEFAULT_BOUNDARY_ATR_BUFFER,
    ) -> pd.DataFrame:
        """
        Evaluate setups while exposing the internal decision path.

        Diagnostic output is intended for:

            - debugging
            - backtesting
            - parameter research
            - paper trading
            - detecting missing structural data
            - investigating rejected setups

        This method does not alter the setup decision logic.
        """

        if df_5m.empty:
            return pd.DataFrame(index=df_5m.index)

        cls._validate_dataframe(df_5m)

        if bias_1h is None or regime_15m is None or direction_15m is None:
            raise ValueError(
                "bias_1h, regime_15m, and direction_15m "
                "are all required for diagnostics."
            )

        cls._validate_htf_series(
            bias_1h,
            "bias_1h",
            cls.VALID_BIAS,
        )

        cls._validate_htf_series(
            regime_15m,
            "regime_15m",
            cls.VALID_REGIMES,
        )

        cls._validate_htf_series(
            direction_15m,
            "direction_15m",
            cls.VALID_DIRECTIONS,
        )

        cls._validate_parameters(
            min_body_atr_ratio,
            boundary_atr_buffer,
        )

        df = df_5m.copy()

        h_bias = cls._align_htf_series(
            bias_1h,
            df.index,
        )

        m_regime = cls._align_htf_series(
            regime_15m,
            df.index,
        )

        m_direction = cls._align_htf_series(
            direction_15m,
            df.index,
        )

        candle_range = df["high"] - df["low"]

        candle_body = (df["close"] - df["open"]).abs()

        body_atr_ratio = candle_body / df["atr"]

        conviction_ok = body_atr_ratio >= min_body_atr_ratio

        ema_min = df[["ema_9", "ema_21"]].min(axis=1)

        ema_max = df[["ema_9", "ema_21"]].max(axis=1)

        bullish_pullback_zone = (df["low"] <= ema_max) & (df["close"] > ema_min)

        bearish_pullback_zone = (df["high"] >= ema_min) & (df["close"] < ema_max)

        if "confirmed_swing_high_price" in df.columns:
            swing_high = pd.to_numeric(
                df["confirmed_swing_high_price"],
                errors="coerce",
            )
        else:
            swing_high = pd.Series(
                float("nan"),
                index=df.index,
            )

        if "confirmed_swing_low_price" in df.columns:
            swing_low = pd.to_numeric(
                df["confirmed_swing_low_price"],
                errors="coerce",
            )
        else:
            swing_low = pd.Series(
                float("nan"),
                index=df.index,
            )

        long_boundary_distance = (df["low"] - swing_low).abs()

        short_boundary_distance = (df["high"] - swing_high).abs()

        long_boundary_touch = swing_low.notna() & (
            long_boundary_distance <= (df["atr"] * boundary_atr_buffer)
        )

        short_boundary_touch = swing_high.notna() & (
            short_boundary_distance <= (df["atr"] * boundary_atr_buffer)
        )

        bullish_trend_context = (
            (h_bias == "BULLISH")
            & (m_direction == "BULLISH")
            & (m_regime == "TRENDING_EXPANSION")
        )

        bearish_trend_context = (
            (h_bias == "BEARISH")
            & (m_direction == "BEARISH")
            & (m_regime == "TRENDING_EXPANSION")
        )

        bullish_compression_context = (h_bias == "BULLISH") & (
            m_regime == "RANGING_COMPRESSION"
        )

        bearish_compression_context = (h_bias == "BEARISH") & (
            m_regime == "RANGING_COMPRESSION"
        )

        bullish_rejection = (
            long_boundary_touch
            & (df["close"] > df["open"])
            & conviction_ok
            & (candle_range > 0)
        )

        bearish_rejection = (
            short_boundary_touch
            & (df["close"] < df["open"])
            & conviction_ok
            & (candle_range > 0)
        )

        bullish_trend_setup = (
            bullish_trend_context
            & bullish_pullback_zone
            & conviction_ok
            & (df["close"] > df["open"])
        )

        bearish_trend_setup = (
            bearish_trend_context
            & bearish_pullback_zone
            & conviction_ok
            & (df["close"] < df["open"])
        )

        bullish_compression_setup = bullish_compression_context & bullish_rejection

        bearish_compression_setup = bearish_compression_context & bearish_rejection

        diagnostics = pd.DataFrame(index=df.index)

        diagnostics["bias_1h"] = h_bias
        diagnostics["regime_15m"] = m_regime
        diagnostics["direction_15m"] = m_direction

        diagnostics["ema_9"] = df["ema_9"]
        diagnostics["ema_21"] = df["ema_21"]
        diagnostics["atr"] = df["atr"]

        diagnostics["candle_range"] = candle_range
        diagnostics["candle_body"] = candle_body
        diagnostics["body_atr_ratio"] = body_atr_ratio
        diagnostics["conviction_ok"] = conviction_ok

        diagnostics["ema_zone_low"] = ema_min
        diagnostics["ema_zone_high"] = ema_max

        diagnostics["bullish_pullback_zone"] = bullish_pullback_zone

        diagnostics["bearish_pullback_zone"] = bearish_pullback_zone

        diagnostics["confirmed_swing_high_price"] = swing_high

        diagnostics["confirmed_swing_low_price"] = swing_low

        diagnostics["long_boundary_distance"] = long_boundary_distance

        diagnostics["short_boundary_distance"] = short_boundary_distance

        diagnostics["long_boundary_touch"] = long_boundary_touch

        diagnostics["short_boundary_touch"] = short_boundary_touch

        diagnostics["bullish_trend_context"] = bullish_trend_context

        diagnostics["bearish_trend_context"] = bearish_trend_context

        diagnostics["bullish_compression_context"] = bullish_compression_context

        diagnostics["bearish_compression_context"] = bearish_compression_context

        diagnostics["bullish_trend_setup"] = bullish_trend_setup

        diagnostics["bearish_trend_setup"] = bearish_trend_setup

        diagnostics["bullish_compression_setup"] = bullish_compression_setup

        diagnostics["bearish_compression_setup"] = bearish_compression_setup

        diagnostics["setup"] = cls.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=min_body_atr_ratio,
            boundary_atr_buffer=boundary_atr_buffer,
        )

        return diagnostics
