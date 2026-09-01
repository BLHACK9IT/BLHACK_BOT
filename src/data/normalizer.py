# src/data/normalizer.py

"""
============================================================
MARKET DATA NORMALIZER — SCALPING V1
============================================================

ROLE
----

The Normalizer sits directly between the external market-data
provider and the internal trading system.

Its job is NOT to generate trading signals.

Its job is to transform raw API candle data into a clean,
strict, predictable market-data contract that can safely be
consumed by:

    - indicators.py
    - bias_engine.py
    - regime_engine.py
    - setup_engine.py
    - entry_engine.py
    - edge_engine.py
    - backtesting
    - paper trading

PIPELINE
--------

    Twelve Data / Other Provider
                |
                v
          Raw API Data
                |
                v
          NORMALIZER
                |
                v
        Canonical OHLCV
                |
                v
            Indicators
                |
                v
        Strategy Engines


CORE DESIGN PRINCIPLES
----------------------

1. NEVER manufacture market information.

2. NEVER silently repair impossible OHLC values.

3. NEVER use global dropna() because some values, especially
   volume, can legitimately be unavailable.

4. Preserve the volume column even when volume is unavailable.

5. Use NaN to represent unavailable numeric information.

6. Require a clean, monotonic, unique datetime index.

7. Reject malformed candles instead of allowing corrupted
   market data into the strategy pipeline.

8. Keep normalization separate from indicator calculation.

9. Keep normalization separate from trading decisions.

10. The same normalization rules should be usable for historical
    data, live data, and paper trading.


CANONICAL DATA CONTRACT
-----------------------

Every normalized dataframe should contain:

    open
    high
    low
    close
    volume

The timestamp is stored as the dataframe index.

OHLC columns must contain valid numeric prices.

Volume is numeric when supplied by the provider and NaN when
volume is unavailable or cannot be meaningfully represented.

The normalizer does NOT calculate:

    EMA
    ATR
    RSI
    MACD
    RVOL
    signals
    bias
    regime
    setup
    entry


TIMEFRAME DESIGN
----------------

The normalizer does not resample market data.

Each timeframe should be normalized independently.

Examples:

    1M  -> normalize 1-minute API candles
    5M  -> normalize 5-minute API candles
    15M -> normalize 15-minute API candles
    1H  -> normalize 1-hour API candles

Resampling/alignment belongs to the appropriate data or
strategy layer rather than silently happening here.

This is important because the trading system must know exactly
which candle generated each higher-timeframe state.


VOLUME DESIGN
-------------

Volume behaves differently depending on the market.

Examples:

    Stocks/Crypto:
        volume may represent actual traded volume.

    FX:
        exchange-wide centralized volume is generally unavailable
        from the spot FX market, while some providers may expose
        tick volume or another provider-specific volume measure.

Therefore:

    - preserve the volume column
    - never invent volume
    - unavailable volume becomes NaN
    - downstream volume-based features must explicitly handle NaN

The normalizer does not decide whether volume is "good enough"
for a strategy. That is a downstream feature/strategy concern.


DATA QUALITY
------------

The normalizer validates:

    - dataframe type
    - required columns
    - timestamp validity
    - timestamp uniqueness
    - timestamp ordering
    - numeric OHLC values
    - positive OHLC prices
    - non-negative volume when volume exists
    - candle high/low structural integrity

Malformed candles are rejected rather than silently modified.


FUTURE EXTENSIONS
------------------

Potential future additions:

    - provider-specific adapters
    - timezone normalization
    - explicit candle-close metadata
    - expected timeframe gap detection
    - asset-class metadata
    - tick-volume classification
    - market-session validation
    - stale-data detection
    - provider failover
    - schema versioning

These are deliberately not embedded into V1 unless required,
because excessive normalization logic can make the data layer
harder to reason about.
"""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd


class MarketDataNormalizer:
    """
    Normalize raw market-data candles into the internal
    canonical OHLCV dataframe format.
    """

    # ==========================================================
    # CANONICAL SCHEMA
    # ==========================================================

    REQUIRED_COLUMNS = {
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    PRICE_COLUMNS = (
        "open",
        "high",
        "low",
        "close",
    )

    # ==========================================================
    # COMMON API COLUMN ALIASES
    # ==========================================================

    COLUMN_ALIASES = {
        "datetime": "timestamp",
        "date": "timestamp",
        "time": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }

    # ==========================================================
    # INITIALIZATION
    # ==========================================================

    def __init__(
        self,
        timeframe: Optional[str] = None,
        volume_policy: str = "preserve",
    ) -> None:
        """
        Parameters
        ----------
        timeframe:
            Optional expected timeframe such as:

                "1min"
                "5min"
                "15min"
                "1h"

            The normalizer does not resample data. The timeframe
            is used as metadata/validation context.

        volume_policy:
            Controls how unavailable volume is represented.

            "preserve":
                Keep supplied volume values and represent missing
                volume as NaN.

            "zero_as_missing":
                Convert zero volume to NaN.

        V1 recommendation:
            Use "preserve" unless the provider's documentation
            confirms that zero specifically means unavailable.
        """

        self.timeframe = timeframe

        valid_policies = {
            "preserve",
            "zero_as_missing",
        }

        if volume_policy not in valid_policies:
            raise ValueError(
                "volume_policy must be one of: " + ", ".join(sorted(valid_policies))
            )

        self.volume_policy = volume_policy

    # ==========================================================
    # COLUMN NORMALIZATION
    # ==========================================================

    def _normalize_column_names(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert known provider-specific column names into the
        canonical internal names.

        Unknown columns are preserved.

        Preserving unknown columns is intentional because future
        provider metadata may be useful for diagnostics without
        forcing the normalizer to understand every provider field.
        """

        result = df.copy()

        rename_map = {}

        for column in result.columns:
            if column in self.COLUMN_ALIASES:
                rename_map[column] = self.COLUMN_ALIASES[column]
            else:
                normalized_name = str(column).strip().lower()

                if normalized_name in {
                    "datetime",
                    "date",
                    "time",
                }:
                    rename_map[column] = "timestamp"

                elif normalized_name in {
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                }:
                    rename_map[column] = normalized_name

        result = result.rename(columns=rename_map)

        return result

    # ==========================================================
    # TIMESTAMP NORMALIZATION
    # ==========================================================

    @staticmethod
    def _normalize_timestamp(
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert the timestamp field into a datetime index.

        The function accepts either:

            - an existing DatetimeIndex
            - a timestamp column
            - a date column already renamed to timestamp

        Timestamps are sorted and duplicate timestamps are rejected.

        The normalizer does not shift timestamps or invent candle
        close times. Timestamp semantics must remain consistent with
        the provider.
        """

        result = df.copy()

        if isinstance(result.index, pd.DatetimeIndex):
            timestamp_index = result.index

        elif "timestamp" in result.columns:
            timestamp_index = pd.to_datetime(
                result["timestamp"],
                errors="coerce",
                utc=True,
            )

            result = result.drop(columns=["timestamp"])

        else:
            raise ValueError(
                "Market data must contain a timestamp column or " "a DatetimeIndex."
            )

        if timestamp_index.isna().any():
            raise ValueError("Market data contains invalid or unparseable timestamps.")

        result.index = timestamp_index

        if result.index.has_duplicates:
            raise ValueError("Market data contains duplicate timestamps.")

        result = result.sort_index()

        if not result.index.is_monotonic_increasing:
            raise ValueError("Market data index must be monotonically increasing.")

        result.index.name = "timestamp"

        return result

    # ==========================================================
    # NUMERIC NORMALIZATION
    # ==========================================================

    def _normalize_numeric_columns(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert OHLCV fields to numeric values.

        Invalid strings are converted to NaN first so they can be
        explicitly detected rather than silently entering strategy
        calculations.
        """

        result = df.copy()

        for column in self.PRICE_COLUMNS:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        result["volume"] = pd.to_numeric(
            result["volume"],
            errors="coerce",
        )

        return result

    # ==========================================================
    # CANDLE VALIDATION
    # ==========================================================

    @staticmethod
    def _validate_prices(
        df: pd.DataFrame,
    ) -> None:
        """
        Validate OHLC price integrity.

        A valid candle must satisfy:

            open  > 0
            high  > 0
            low   > 0
            close > 0

        and:

            high >= max(open, close)
            low  <= min(open, close)
        """

        invalid_price = df[list(MarketDataNormalizer.PRICE_COLUMNS)].isna().any(axis=1)

        if invalid_price.any():
            bad_timestamps = df.index[invalid_price].tolist()

            raise ValueError(
                "Market data contains missing or non-numeric OHLC "
                f"values at timestamps: {bad_timestamps[:5]}"
            )

        non_positive = (df[list(MarketDataNormalizer.PRICE_COLUMNS)] <= 0).any(axis=1)

        if non_positive.any():
            bad_timestamps = df.index[non_positive].tolist()

            raise ValueError(
                "Market data contains non-positive OHLC prices at "
                f"timestamps: {bad_timestamps[:5]}"
            )

        invalid_high = df["high"] < df[["open", "close"]].max(axis=1)

        invalid_low = df["low"] > df[["open", "close"]].min(axis=1)

        invalid_structure = invalid_high | invalid_low

        if invalid_structure.any():
            bad_timestamps = df.index[invalid_structure].tolist()

            raise ValueError(
                "Market data contains structurally invalid candles "
                f"at timestamps: {bad_timestamps[:5]}"
            )

    # ==========================================================
    # VOLUME VALIDATION
    # ==========================================================

    def _normalize_volume(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Normalize volume without inventing missing information.

        Missing volume remains NaN.

        Negative volume is considered invalid.

        Zero-volume handling depends on volume_policy.

        This distinction is important because zero does not
        universally mean "volume unavailable."
        """

        result = df.copy()

        negative_volume = result["volume"].notna() & (result["volume"] < 0)

        if negative_volume.any():
            bad_timestamps = result.index[negative_volume].tolist()

            raise ValueError(
                "Market data contains negative volume values at "
                f"timestamps: {bad_timestamps[:5]}"
            )

        if self.volume_policy == "zero_as_missing":
            result.loc[result["volume"] == 0, "volume"] = np.nan

        return result

    # ==========================================================
    # REQUIRED COLUMN VALIDATION
    # ==========================================================

    @staticmethod
    def _validate_required_columns(
        df: pd.DataFrame,
    ) -> None:
        """
        Ensure the canonical OHLCV fields exist.
        """

        missing = MarketDataNormalizer.REQUIRED_COLUMNS - set(df.columns)

        if missing:
            raise ValueError(
                "Missing required market-data columns: " + ", ".join(sorted(missing))
            )

    # ==========================================================
    # PUBLIC NORMALIZER
    # ==========================================================

    def normalize(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Normalize raw provider candle data.

        Returns
        -------
        pandas.DataFrame
            Canonical OHLCV dataframe indexed by timestamp.

        Important:
            This method does NOT calculate indicators and does NOT
            remove rows globally with dropna().
        """

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Market data must be provided as a pandas DataFrame.")

        if df.empty:
            raise ValueError("Cannot normalize an empty market-data dataframe.")

        result = df.copy()

        # ------------------------------------------------------
        # STEP 1 — Normalize provider column names
        # ------------------------------------------------------

        result = self._normalize_column_names(result)

        # ------------------------------------------------------
        # STEP 2 — Validate canonical schema
        # ------------------------------------------------------

        self._validate_required_columns(result)

        # ------------------------------------------------------
        # STEP 3 — Normalize timestamp/index
        # ------------------------------------------------------

        result = self._normalize_timestamp(result)

        # ------------------------------------------------------
        # STEP 4 — Convert OHLCV to numeric values
        # ------------------------------------------------------

        result = self._normalize_numeric_columns(result)

        # ------------------------------------------------------
        # STEP 5 — Validate OHLC candle integrity
        # ------------------------------------------------------

        self._validate_prices(result)

        # ------------------------------------------------------
        # STEP 6 — Normalize volume
        # ------------------------------------------------------

        result = self._normalize_volume(result)

        # ------------------------------------------------------
        # STEP 7 — Keep canonical columns first
        # ------------------------------------------------------

        canonical_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        remaining_columns = [
            column for column in result.columns if column not in canonical_columns
        ]

        result = result[canonical_columns + remaining_columns]

        # ------------------------------------------------------
        # STEP 8 — Final index assertions
        # ------------------------------------------------------

        if result.index.has_duplicates:
            raise ValueError("Normalized market data contains duplicate timestamps.")

        if not result.index.is_monotonic_increasing:
            raise ValueError("Normalized market data index is not sorted.")

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT call:
        #
        #     result.dropna()
        #
        # here.
        #
        # Indicators such as EMA/ATR naturally produce initial
        # NaN values during their warm-up periods.
        #
        # Removing those rows belongs to the appropriate
        # downstream calculation/backtesting stage.
        # ------------------------------------------------------

        return result

    # ==========================================================
    # DATAFRAME CONTRACT CHECK
    # ==========================================================

    def validate_normalized(
        self,
        df: pd.DataFrame,
    ) -> None:
        """
        Validate that a dataframe already satisfies the canonical
        normalized market-data contract.

        This can be used by downstream modules before consuming
        externally supplied data.
        """

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Normalized market data must be a pandas DataFrame.")

        self._validate_required_columns(df)

        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("Normalized market data must use a DatetimeIndex.")

        if df.index.has_duplicates:
            raise ValueError("Normalized market data contains duplicate timestamps.")

        if not df.index.is_monotonic_increasing:
            raise ValueError(
                "Normalized market data index must be monotonically increasing."
            )

        self._validate_prices(df)

        self._normalize_volume(df)

    # ==========================================================
    # CONVENIENCE FUNCTION
    # ==========================================================


def normalize_market_data(
    df: pd.DataFrame,
    timeframe: Optional[str] = None,
    volume_policy: str = "preserve",
) -> pd.DataFrame:
    """
    Convenience wrapper around MarketDataNormalizer.

    Example conceptual usage:

        normalized = normalize_market_data(
            raw_data,
            timeframe="1min",
        )

    The returned dataframe follows the canonical OHLCV contract.
    """

    normalizer = MarketDataNormalizer(
        timeframe=timeframe,
        volume_policy=volume_policy,
    )

    return normalizer.normalize(df)
