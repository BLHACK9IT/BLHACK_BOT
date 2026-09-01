"""
============================================================
SCALPING INDICATOR TEST SUITE — MVP
============================================================

Purpose
-------
Tests the FeatureEngineer / Scalping Indicator layer.

The indicator receives NORMALIZED OHLCV data.

Contract
--------
1. Empty DataFrame must return safely.
2. Non-empty malformed DataFrame must raise clearly.
3. Valid OHLCV data must produce the expected features.
4. Feature engineering must not change row count.
5. Original OHLCV columns must remain.
6. Features must not introduce obviously invalid ratios.
7. Volume metadata must be preserved.

Important
---------
These tests do NOT test trading profitability.

They test the correctness and safety of the indicator layer.
============================================================
"""

import numpy as np
import pandas as pd
import pytest

from src.features.scalping_indicators import FeatureEngineer

# ============================================================
# TEST DATA
# ============================================================


@pytest.fixture
def sample_ohlcv():
    """
    Deterministic OHLCV dataset.

    Enough rows are provided for:
        EMA 9
        EMA 21
        ATR 14
        RSI 14
        volume MA 20
        momentum features
    """

    index = pd.date_range(
        start="2026-01-01 00:00:00",
        periods=60,
        freq="1min",
        tz="UTC",
    )

    base = np.linspace(1.1000, 1.1060, 60)

    return pd.DataFrame(
        {
            "open": base,
            "high": base + 0.0010,
            "low": base - 0.0010,
            "close": base + 0.0005,
            "volume": np.arange(
                100,
                160,
                dtype=float,
            ),
            "volume_type": "exchange",
        },
        index=index,
    )


# ============================================================
# 1. EMPTY INPUT
# ============================================================


def test_empty_dataframe_returns_empty():
    """
    Empty upstream data is a valid pipeline condition.

    The indicator must NOT crash merely because there
    are no rows to process.
    """

    df = pd.DataFrame()

    result = FeatureEngineer.apply_all_features(df)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ============================================================
# 2. WRONG INPUT TYPE
# ============================================================


@pytest.mark.parametrize(
    "bad_input",
    [
        None,
        [],
        {},
        "invalid",
        123,
    ],
)
def test_non_dataframe_input_raises_type_error(
    bad_input,
):
    """
    Completely wrong input types should fail clearly.
    """

    with pytest.raises(TypeError):
        FeatureEngineer.apply_all_features(bad_input)


# ============================================================
# 3. NON-EMPTY MISSING COLUMNS
# ============================================================


def test_non_empty_dataframe_missing_required_columns_raises():
    """
    An empty DataFrame is allowed.

    A NON-EMPTY DataFrame missing required OHLCV
    columns is NOT allowed.
    """

    df = pd.DataFrame(
        {
            "close": [1.10, 1.11],
            "volume": [100, 110],
        }
    )

    with pytest.raises(ValueError):
        FeatureEngineer.apply_all_features(df)


# ============================================================
# 4. ROW COUNT
# ============================================================


def test_features_do_not_change_row_count(
    sample_ohlcv,
):
    """
    Feature engineering must add columns,
    not remove market-data rows.
    """

    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    assert len(result) == len(sample_ohlcv)


# ============================================================
# 5. ORIGINAL OHLCV COLUMNS
# ============================================================


def test_original_ohlcv_columns_remain(
    sample_ohlcv,
):
    """
    The feature layer must preserve the normalized
    market-data columns.
    """

    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    required = {
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    assert required.issubset(result.columns)


# ============================================================
# 6. TREND FEATURES
# ============================================================


def test_trend_features_exist(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = {
        "ema_9",
        "ema_21",
        "ema_separation",
        "ema_separation_pct",
        "price_to_ema_fast",
        "price_to_ema_fast_pct",
        "ema_fast_slope",
        "ema_fast_slope_pct",
    }

    assert expected.issubset(result.columns)


# ============================================================
# 7. VOLATILITY FEATURES
# ============================================================


def test_volatility_features_exist(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = {
        "candle_range",
        "true_range",
        "atr",
        "atr_pct",
        "range_to_atr",
    }

    assert expected.issubset(result.columns)


# ============================================================
# 8. MOMENTUM FEATURES
# ============================================================


def test_momentum_features_exist(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = {
        "return_1c",
        "return_3c",
        "return_5c",
        "mom_1c_atr",
        "mom_3c_atr",
        "mom_5c_atr",
    }

    assert expected.issubset(result.columns)


# ============================================================
# 9. VOLUME FEATURES
# ============================================================


def test_volume_features_exist(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = {
        "volume",
        "volume_type",
        "vol_ma",
        "rvol",
    }

    assert expected.issubset(result.columns)


# ============================================================
# 10. RSI
# ============================================================


def test_rsi_exists(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    assert "rsi" in result.columns


# ============================================================
# 11. PRICE STRUCTURE
# ============================================================


def test_price_structure_features_exist(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = {
        "candle_range",
        "body_size",
        "upper_wick",
        "lower_wick",
        "body_ratio",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "close_location",
        "swing_high",
        "swing_low",
        "confirmed_swing_high_price",
        "confirmed_swing_low_price",
    }

    assert expected.issubset(result.columns)


# ============================================================
# 12. BODY RATIO
# ============================================================


def test_body_ratio_is_between_zero_and_one(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    values = result["body_ratio"].dropna()

    assert (values >= 0).all()
    assert (values <= 1).all()


# ============================================================
# 13. WICK RATIOS
# ============================================================


def test_wick_ratios_are_not_negative(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    for column in [
        "upper_wick_ratio",
        "lower_wick_ratio",
    ]:
        values = result[column].dropna()

        assert (values >= 0).all()


# ============================================================
# 14. CLOSE LOCATION
# ============================================================


def test_close_location_is_between_zero_and_one(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    values = result["close_location"].dropna()

    assert (values >= 0).all()
    assert (values <= 1).all()


# ============================================================
# 15. VOLUME TYPE
# ============================================================


def test_volume_type_is_preserved(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    assert "volume_type" in result.columns

    assert (result["volume_type"] == "exchange").all()


# ============================================================
# 16. NO GLOBAL DROPNA
# ============================================================


def test_warmup_rows_are_not_deleted(
    sample_ohlcv,
):
    """
    Indicators need warm-up periods.

    Early rows may contain NaN values.

    That is expected.

    The feature engine must NOT delete those rows
    with a global dropna().
    """

    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    assert len(result) == len(sample_ohlcv)

    assert result["ema_21"].isna().any()


# ============================================================
# 17. FEATURE ENGINE DOES NOT MUTATE INPUT
# ============================================================


def test_input_dataframe_is_not_mutated(
    sample_ohlcv,
):
    """
    Feature engineering should operate on a copy.
    """

    original_columns = sample_ohlcv.columns.tolist()
    original_values = sample_ohlcv.copy()

    FeatureEngineer.apply_all_features(sample_ohlcv)

    assert sample_ohlcv.columns.tolist() == original_columns

    pd.testing.assert_frame_equal(
        sample_ohlcv,
        original_values,
    )


# ============================================================
# 18. EMPTY DATA WITH OHLCV COLUMNS
# ============================================================


def test_empty_ohlcv_dataframe_returns_empty():
    """
    Empty normalized data with the correct columns
    must also pass safely.
    """

    df = pd.DataFrame(
        columns=[
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
    )

    result = FeatureEngineer.apply_all_features(df)

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ============================================================
# 19. CANDLE RANGE IS CONSISTENT
# ============================================================


def test_candle_range_matches_high_minus_low(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    expected = result["high"] - result["low"]

    pd.testing.assert_series_equal(
        result["candle_range"],
        expected,
        check_names=False,
    )


# ============================================================
# 20. BODY SIZE IS NON-NEGATIVE
# ============================================================


def test_body_size_is_non_negative(
    sample_ohlcv,
):
    result = FeatureEngineer.apply_all_features(sample_ohlcv)

    values = result["body_size"].dropna()

    assert (values >= 0).all()
