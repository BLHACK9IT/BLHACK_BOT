# src/strategy/entry_engine.py

"""
============================================================
1M ENTRY ENGINE — SCALPING V1
============================================================

ROLE
----

The 1M Entry Engine is the micro-structural execution trigger
situated downstream from the 5M Setup Engine.

Its job is to answer:

    "Should we pull the trigger right now based on 1M price action?"

The engine therefore:

    1. Listens for DISCRETE 5M setup events.
    2. Opens a limited 1M confirmation window.
    3. Searches subsequent 1M candles for directional confirmation.
    4. Invalidates stale setups after the configured timeout.
    5. Produces an execution event.
    6. Provides diagnostic information for research and paper trading.

Possible output signals:

    EXECUTE_LONG
    EXECUTE_SHORT
    STANDBY

IMPORTANT
---------

This engine does NOT:

    - calculate account risk
    - submit broker orders
    - calculate position size
    - determine 1H bias
    - determine 15M regime
    - create 5M setups

Those responsibilities belong to other layers.

ARCHITECTURE
------------

    1H BIAS
       ↓
    15M REGIME
       ↓
    5M SETUP
       ↓
    1M ENTRY ENGINE
       ↓
    EDGE / COST
       ↓
    RISK
       ↓
    EXECUTION

ENTRY HYPOTHESIS V1
-------------------

A valid 5M setup establishes directional intent.

The 1M engine then waits for a simple local confirmation:

LONG:

    close > EMA9
    close > open
    candle body ratio >= minimum threshold

SHORT:

    close < EMA9
    close < open
    candle body ratio >= minimum threshold

The purpose of this simplicity is deliberate.

V1 should establish whether the structural hierarchy itself
has measurable value before adding additional oscillators or
complex filters.
"""

from __future__ import annotations

import pandas as pd


class ScalpingEntryEngine:
    """
    1M micro-structural entry engine for the scalping system.
    """

    # ==========================================================
    # PUBLIC STATES
    # ==========================================================

    LONG = "EXECUTE_LONG"
    SHORT = "EXECUTE_SHORT"
    STANDBY = "STANDBY"

    # Internal state values
    WAITING_LONG = "WAITING_LONG"
    WAITING_SHORT = "WAITING_SHORT"

    # ==========================================================
    # VALID SETUP STATES
    # ==========================================================

    VALID_SETUPS = {
        "LONG_SETUP",
        "SHORT_SETUP",
        "NONE",
    }

    # ==========================================================
    # REQUIRED 1M FEATURES
    # ==========================================================

    REQUIRED_COLUMNS = {
        "open",
        "high",
        "low",
        "close",
        "ema_9",
        "atr",
    }

    # ==========================================================
    # V1 CONFIGURATION
    # ==========================================================

    DEFAULT_MAX_TIMEOUT_BARS = 4
    DEFAULT_MIN_BODY_RATIO = 0.30
    DEFAULT_ATR_STOP_BUFFER = 0.50

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @classmethod
    def _validate_1m_dataframe(
        cls,
        df: pd.DataFrame,
    ) -> None:
        """
        Validate the 1M dataframe contract.
        """

        if not isinstance(df, pd.DataFrame):
            raise TypeError("df_1m must be a pandas DataFrame.")

        if df.empty:
            raise ValueError("df_1m cannot be empty.")

        missing = cls.REQUIRED_COLUMNS - set(df.columns)

        if missing:
            raise ValueError(
                "Missing required 1M feature columns: " + ", ".join(sorted(missing))
            )

        if not df.index.is_monotonic_increasing:
            raise ValueError("df_1m index must be monotonically increasing.")

        if df.index.has_duplicates:
            raise ValueError("df_1m index contains duplicate timestamps.")

    @classmethod
    def _validate_setup_series(
        cls,
        series: pd.Series,
    ) -> None:
        """
        Validate the incoming 5M setup event series.
        """

        if not isinstance(series, pd.Series):
            raise TypeError("setup_5m must be a pandas Series.")

        if series.index.has_duplicates:
            raise ValueError("setup_5m index contains duplicate timestamps.")

        if not series.index.is_monotonic_increasing:
            raise ValueError("setup_5m index must be monotonically increasing.")

        invalid_values = set(series.dropna().unique()) - cls.VALID_SETUPS

        if invalid_values:
            raise ValueError(
                "setup_5m contains invalid setup states: "
                + ", ".join(sorted(map(str, invalid_values)))
            )

    @staticmethod
    def _validate_parameters(
        max_timeout_bars: int,
        atr_stop_buffer: float,
        min_body_ratio: float,
    ) -> None:
        """
        Validate engine configuration.
        """

        if (
            not isinstance(max_timeout_bars, int)
            or isinstance(max_timeout_bars, bool)
            or max_timeout_bars < 1
        ):
            raise ValueError("max_timeout_bars must be an integer >= 1.")

        if atr_stop_buffer < 0:
            raise ValueError("atr_stop_buffer must be >= 0.")

        if not 0 < min_body_ratio <= 1:
            raise ValueError("min_body_ratio must be > 0 and <= 1.")

    # ==========================================================
    # MICROSTRUCTURE
    # ==========================================================

    @staticmethod
    def _build_micro_triggers(
        df: pd.DataFrame,
        min_body_ratio: float,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Build the simple V1 1M confirmation conditions.

        Returns
        -------

        body_ratio
            Candle body / total candle range.

        micro_long_trigger
            Bullish 1M confirmation.

        micro_short_trigger
            Bearish 1M confirmation.
        """

        candle_range = df["high"] - df["low"]

        safe_range = candle_range.where(candle_range > 0)

        body_ratio = (df["close"] - df["open"]).abs() / safe_range

        micro_long_trigger = (
            (df["close"] > df["ema_9"])
            & (df["close"] > df["open"])
            & (body_ratio >= min_body_ratio)
        )

        micro_short_trigger = (
            (df["close"] < df["ema_9"])
            & (df["close"] < df["open"])
            & (body_ratio >= min_body_ratio)
        )

        return (
            body_ratio,
            micro_long_trigger,
            micro_short_trigger,
        )

    # ==========================================================
    # SETUP ALIGNMENT
    # ==========================================================

    @staticmethod
    def _align_setup_events(
        df_1m: pd.DataFrame,
        setup_5m: pd.Series,
    ) -> pd.Series:
        """
        Align discrete 5M setup events onto the 1M timeline.

        IMPORTANT
        ---------

        The setup engine should emit discrete events rather than
        continuous setup states.

        Therefore a LONG_SETUP or SHORT_SETUP exists only at the
        timestamp where the event becomes available.

        All other 1M candles are treated as NONE.

        This avoids treating one setup event as an indefinitely
        active state.
        """

        aligned = setup_5m.reindex(
            df_1m.index,
            fill_value="NONE",
        )

        return aligned.fillna("NONE")

    # ==========================================================
    # MAIN EVALUATOR
    # ==========================================================

    @classmethod
    def evaluate(
        cls,
        df_1m: pd.DataFrame,
        setup_5m: pd.Series,
        max_timeout_bars: int = DEFAULT_MAX_TIMEOUT_BARS,
        atr_stop_buffer: float = DEFAULT_ATR_STOP_BUFFER,
        min_body_ratio: float = DEFAULT_MIN_BODY_RATIO,
    ) -> pd.Series:
        """
        Evaluate 1M entry confirmation following 5M setup events.

        A setup opens a finite confirmation window.

        The first valid directional 1M confirmation produces:

            EXECUTE_LONG
            EXECUTE_SHORT

        Otherwise:

            STANDBY
        """

        cls._validate_1m_dataframe(df_1m)
        cls._validate_setup_series(setup_5m)

        cls._validate_parameters(
            max_timeout_bars=max_timeout_bars,
            atr_stop_buffer=atr_stop_buffer,
            min_body_ratio=min_body_ratio,
        )

        df = df_1m.copy()

        aligned_setup = cls._align_setup_events(
            df_1m=df,
            setup_5m=setup_5m,
        )

        (
            _,
            micro_long_trigger,
            micro_short_trigger,
        ) = cls._build_micro_triggers(
            df,
            min_body_ratio=min_body_ratio,
        )

        signals = []

        active_state = cls.STANDBY
        bars_waiting = 0

        for i in range(len(df)):

            current_setup = aligned_setup.iloc[i]

            is_long = bool(micro_long_trigger.iloc[i])

            is_short = bool(micro_short_trigger.iloc[i])

            # --------------------------------------------------
            # NEW LONG SETUP EVENT
            # --------------------------------------------------

            if current_setup == "LONG_SETUP":

                active_state = cls.WAITING_LONG
                bars_waiting = 0

                signals.append(cls.STANDBY)

                continue

            # --------------------------------------------------
            # NEW SHORT SETUP EVENT
            # --------------------------------------------------

            if current_setup == "SHORT_SETUP":

                active_state = cls.WAITING_SHORT
                bars_waiting = 0

                signals.append(cls.STANDBY)

                continue

            # --------------------------------------------------
            # WAITING FOR LONG CONFIRMATION
            # --------------------------------------------------

            if active_state == cls.WAITING_LONG:

                bars_waiting += 1

                if is_long:

                    signals.append(cls.LONG)

                    active_state = cls.STANDBY
                    bars_waiting = 0

                elif bars_waiting >= max_timeout_bars:

                    signals.append(cls.STANDBY)

                    active_state = cls.STANDBY
                    bars_waiting = 0

                else:

                    signals.append(cls.STANDBY)

                continue

            # --------------------------------------------------
            # WAITING FOR SHORT CONFIRMATION
            # --------------------------------------------------

            if active_state == cls.WAITING_SHORT:

                bars_waiting += 1

                if is_short:

                    signals.append(cls.SHORT)

                    active_state = cls.STANDBY
                    bars_waiting = 0

                elif bars_waiting >= max_timeout_bars:

                    signals.append(cls.STANDBY)

                    active_state = cls.STANDBY
                    bars_waiting = 0

                else:

                    signals.append(cls.STANDBY)

                continue

            # --------------------------------------------------
            # NO ACTIVE SETUP
            # --------------------------------------------------

            signals.append(cls.STANDBY)

        return pd.Series(
            signals,
            index=df.index,
            dtype="object",
            name="execution_signal",
        )

    # ==========================================================
    # DIAGNOSTIC EVALUATOR
    # ==========================================================

    @classmethod
    def evaluate_with_diagnostics(
        cls,
        df_1m: pd.DataFrame,
        setup_5m: pd.Series,
        max_timeout_bars: int = DEFAULT_MAX_TIMEOUT_BARS,
        atr_stop_buffer: float = DEFAULT_ATR_STOP_BUFFER,
        min_body_ratio: float = DEFAULT_MIN_BODY_RATIO,
    ) -> pd.DataFrame:
        """
        Evaluate entries while exposing internal measurements.

        These diagnostics are intended for:

            backtesting
            paper trading
            debugging
            research
            threshold analysis

        They are not themselves trading signals.
        """

        cls._validate_1m_dataframe(df_1m)
        cls._validate_setup_series(setup_5m)

        cls._validate_parameters(
            max_timeout_bars=max_timeout_bars,
            atr_stop_buffer=atr_stop_buffer,
            min_body_ratio=min_body_ratio,
        )

        df = df_1m.copy()

        aligned_setup = cls._align_setup_events(
            df_1m=df,
            setup_5m=setup_5m,
        )

        (
            body_ratio,
            micro_long_trigger,
            micro_short_trigger,
        ) = cls._build_micro_triggers(
            df,
            min_body_ratio=min_body_ratio,
        )

        signals = cls.evaluate(
            df_1m=df,
            setup_5m=setup_5m,
            max_timeout_bars=max_timeout_bars,
            atr_stop_buffer=atr_stop_buffer,
            min_body_ratio=min_body_ratio,
        )

        # ------------------------------------------------------
        # FILL PRICE
        # ------------------------------------------------------

        # V1 uses the completed 1M candle close as the
        # theoretical signal/fill reference.
        #
        # This is NOT a realistic broker fill model.
        #
        # The future Cost Model / Paper Broker must model:
        #
        #     spread
        #     slippage
        #     execution delay
        #
        fill_price = df["close"].copy()

        # ------------------------------------------------------
        # STOP REFERENCE
        # ------------------------------------------------------

        stop_loss = pd.Series(
            pd.NA,
            index=df.index,
            dtype="Float64",
            name="stop_loss",
        )

        long_exec = signals == cls.LONG

        short_exec = signals == cls.SHORT

        if long_exec.any():

            stop_loss.loc[long_exec] = df.loc[long_exec, "low"] - (
                df.loc[long_exec, "atr"] * atr_stop_buffer
            )

        if short_exec.any():

            stop_loss.loc[short_exec] = df.loc[short_exec, "high"] + (
                df.loc[short_exec, "atr"] * atr_stop_buffer
            )

        # ------------------------------------------------------
        # DIAGNOSTIC DATAFRAME
        # ------------------------------------------------------

        diagnostics = pd.DataFrame(index=df.index)

        diagnostics["execution_signal"] = signals

        diagnostics["setup_5m_event"] = aligned_setup

        diagnostics["micro_long_trigger"] = micro_long_trigger

        diagnostics["micro_short_trigger"] = micro_short_trigger

        diagnostics["body_ratio"] = body_ratio

        diagnostics["fill_price_reference"] = fill_price

        diagnostics["stop_loss_reference"] = stop_loss

        diagnostics["open"] = df["open"]
        diagnostics["high"] = df["high"]
        diagnostics["low"] = df["low"]
        diagnostics["close"] = df["close"]

        diagnostics["ema_9"] = df["ema_9"]
        diagnostics["atr"] = df["atr"]

        return diagnostics
