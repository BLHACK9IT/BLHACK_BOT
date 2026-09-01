"""
============================================================
MARKET DATA NORMALIZER TEST SUITE — SCALPING V1
============================================================
"""

import numpy as np
import pandas as pd
import pytest

from src.data.normalizer import MarketDataNormalizer, normalize_market_data


@pytest.fixture
def normalizer():
    return MarketDataNormalizer(timeframe="1min")


def test_valid_market_data_normalization(normalizer):
    """
    Valid raw provider data is successfully normalized into canonical format.
    """
    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:01:00", "2026-08-01 10:00:00"],  # Unsorted
            "Open": [1.0850, 1.0845],
            "High": [1.0860, 1.0855],
            "Low": [1.0840, 1.0835],
            "Close": [1.0855, 1.0850],
            "Volume": [100, 200],
        }
    )

    result = normalizer.normalize(raw_df)

    # Check canonical columns and sorted chronological index
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.index.is_monotonic_increasing
    assert result.index[0] == pd.Timestamp("2026-08-01 10:00:00", tz="UTC")
    assert result.loc[result.index[0], "open"] == 1.0845


def test_column_alias_translation():
    """
    Provider-specific alternative names are correctly mapped and extra columns preserved.
    """
    raw_df = pd.DataFrame(
        {
            "datetime": ["2026-08-01 10:00:00"],
            "OPEN": [1.0],
            "HIGH": [1.2],
            "LOW": [0.9],
            "CLOSE": [1.1],
            "volume": [100],
            "custom_provider_metric": [50],
        }
    )

    result = normalize_market_data(raw_df)

    assert "open" in result.columns
    assert "volume" in result.columns
    assert "custom_provider_metric" in result.columns


def test_duplicate_timestamps_raise_error(normalizer):
    """
    Duplicate candle timestamps must be rejected immediately.
    """
    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:00:00", "2026-08-01 10:00:00"],
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.0, 1.0],
            "volume": [100, 100],
        }
    )

    with pytest.raises(ValueError, match="duplicate timestamps"):
        normalizer.normalize(raw_df)


def test_non_positive_prices_raise_error(normalizer):
    """
    Zero or negative prices violate candle integrity and must fail.
    """
    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:00:00"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.0],  # Invalid low
            "close": [1.0],
            "volume": [100],
        }
    )

    with pytest.raises(ValueError, match="non-positive OHLC prices"):
        normalizer.normalize(raw_df)


def test_structural_candle_violation_raises_error(normalizer):
    """
    High must be >= max(open, close) and low must be <= min(open, close).
    """
    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:00:00"],
            "open": [1.0850],
            "high": [1.0840],  # High is lower than open!
            "low": [1.0830],
            "close": [1.0845],
            "volume": [100],
        }
    )

    with pytest.raises(ValueError, match="structurally invalid candles"):
        normalizer.normalize(raw_df)


def test_negative_volume_raises_error(normalizer):
    """
    Negative volume values are illegal and must trigger validation failure.
    """
    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:00:00"],
            "open": [1.0850],
            "high": [1.0860],
            "low": [1.0840],
            "close": [1.0855],
            "volume": [-50],
        }
    )

    with pytest.raises(ValueError, match="negative volume values"):
        normalizer.normalize(raw_df)


def test_zero_as_missing_volume_policy():
    """
    Configuring volume_policy to 'zero_as_missing' converts 0 volumes to NaN.
    """
    normalizer = MarketDataNormalizer(volume_policy="zero_as_missing")

    raw_df = pd.DataFrame(
        {
            "timestamp": ["2026-08-01 10:00:00"],
            "open": [1.0850],
            "high": [1.0860],
            "low": [1.0840],
            "close": [1.0855],
            "volume": [0],
        }
    )

    result = normalizer.normalize(raw_df)
    assert np.isnan(result.loc[result.index[0], "volume"])


def test_empty_dataframe_raises_error(normalizer):
    """
    An empty raw dataframe must be explicitly rejected.
    """
    with pytest.raises(ValueError, match="Cannot normalize an empty"):
        normalizer.normalize(pd.DataFrame())
