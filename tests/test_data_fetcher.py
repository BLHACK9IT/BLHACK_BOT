import pytest
import pandas as pd
import numpy as np

from datetime import datetime, timezone

from src.data.data_fetcher import MultiAssetDataFetcher

# ============================================================
# TEST HELPERS
# ============================================================


@pytest.fixture
def fetcher():
    """
    Creates the data fetcher without requiring a real API key.

    The tests below focus on the internal data contracts and
    processing logic rather than making live Twelve Data calls.
    """
    return MultiAssetDataFetcher(data_api_keys={})


def test_twelve_data_uses_api_key_config_name():
    fetcher = MultiAssetDataFetcher(
        data_api_keys={"twelve_data": {"api_key": "test-api-key"}}
    )

    assert fetcher.api_key == "test-api-key"
    assert fetcher.td_client is not None


@pytest.fixture
def sample_ohlcv():
    """
    Small deterministic OHLCV dataset used for local tests.
    """
    index = pd.date_range(
        start="2026-01-01 00:00:00",
        periods=30,
        freq="1min",
        tz="UTC",
    )

    return pd.DataFrame(
        {
            "open": np.linspace(1.1000, 1.1030, 30),
            "high": np.linspace(1.1010, 1.1040, 30),
            "low": np.linspace(1.0990, 1.1020, 30),
            "close": np.linspace(1.1005, 1.1035, 30),
            "volume": np.arange(100, 130, dtype=float),
        },
        index=index,
    )


# ============================================================
# SYMBOL NORMALIZATION
# ============================================================


def test_symbol_normalization_forex():
    fetcher = MultiAssetDataFetcher(data_api_keys={})

    assert fetcher._normalize_symbol("eurusd") == "EUR/USD"
    assert fetcher._normalize_symbol("EURUSD") == "EUR/USD"
    assert fetcher._normalize_symbol(" EURUSD ") == "EUR/USD"


def test_symbol_normalization_existing_slash():
    fetcher = MultiAssetDataFetcher(data_api_keys={})

    assert fetcher._normalize_symbol("eur/usd") == "EUR/USD"


def test_symbol_normalization_does_not_modify_non_six_character_symbol():
    fetcher = MultiAssetDataFetcher(data_api_keys={})

    assert fetcher._normalize_symbol("BTC/USDT") == "BTC/USDT"


# ============================================================
# TIMEFRAME CONVERSION
# ============================================================


@pytest.mark.parametrize(
    "timeframe, expected_minutes",
    [
        ("1min", 1),
        ("5min", 5),
        ("15min", 15),
        ("30min", 30),
        ("1h", 60),
        ("1hour", 60),
        ("2h", 120),
        ("4h", 240),
        ("1day", 1440),
        ("1d", 1440),
    ],
)
def test_timeframe_to_minutes(
    fetcher,
    timeframe,
    expected_minutes,
):
    assert fetcher._timeframe_to_minutes(timeframe) == expected_minutes


def test_unsupported_timeframe_raises():
    with pytest.raises(ValueError):
        MultiAssetDataFetcher(data_api_keys={})._timeframe_to_minutes("7min")


# ============================================================
# CANDLE OPEN TIME
# ============================================================


def test_get_current_1m_candle_open_time(fetcher):
    now = datetime(
        2026,
        1,
        1,
        12,
        34,
        56,
        tzinfo=timezone.utc,
    )

    result = fetcher._get_current_candle_open_time(
        timeframe="1min",
        now=now,
    )

    assert result == datetime(
        2026,
        1,
        1,
        12,
        34,
        0,
        tzinfo=timezone.utc,
    )


def test_get_current_5m_candle_open_time(fetcher):
    now = datetime(
        2026,
        1,
        1,
        12,
        34,
        56,
        tzinfo=timezone.utc,
    )

    result = fetcher._get_current_candle_open_time(
        timeframe="5min",
        now=now,
    )

    assert result == datetime(
        2026,
        1,
        1,
        12,
        30,
        0,
        tzinfo=timezone.utc,
    )


def test_get_current_15m_candle_open_time(fetcher):
    now = datetime(
        2026,
        1,
        1,
        12,
        34,
        56,
        tzinfo=timezone.utc,
    )

    result = fetcher._get_current_candle_open_time(
        timeframe="15min",
        now=now,
    )

    assert result == datetime(
        2026,
        1,
        1,
        12,
        30,
        0,
        tzinfo=timezone.utc,
    )


def test_get_next_candle_open_time(fetcher):
    now = datetime(
        2026,
        1,
        1,
        12,
        34,
        56,
        tzinfo=timezone.utc,
    )

    result = fetcher._get_next_candle_open_time(
        timeframe="5min",
        now=now,
    )

    assert result == datetime(
        2026,
        1,
        1,
        12,
        35,
        0,
        tzinfo=timezone.utc,
    )


# ============================================================
# ASSET CATEGORY
# ============================================================


def test_supported_asset_category(fetcher):
    """
    EURUSD should resolve if EUR/USD is present in the active
    MARKET_CATEGORIES configuration.
    """
    category = fetcher.get_asset_category("EURUSD")

    assert isinstance(category, str)
    assert category != ""


def test_unknown_asset_raises():
    fetcher = MultiAssetDataFetcher(data_api_keys={})

    with pytest.raises(ValueError):
        fetcher.get_asset_category("THIS_IS_NOT_A_SUPPORTED_SYMBOL")


# ============================================================
# LATEST TIMESTAMP
# ============================================================


def test_get_latest_timestamp_from_datetime_index(
    fetcher,
    sample_ohlcv,
):
    result = fetcher._get_latest_timestamp(sample_ohlcv)

    assert result is not None
    assert result == sample_ohlcv.index.max()


def test_get_latest_timestamp_from_datetime_column(
    fetcher,
):
    df = pd.DataFrame(
        {
            "datetime": [
                "2026-01-01 00:00:00+00:00",
                "2026-01-01 00:01:00+00:00",
                "2026-01-01 00:02:00+00:00",
            ],
            "open": [1, 2, 3],
        }
    )

    result = fetcher._get_latest_timestamp(df)

    assert result == pd.Timestamp(
        "2026-01-01 00:02:00",
        tz="UTC",
    )


def test_get_latest_timestamp_empty_dataframe(
    fetcher,
):
    result = fetcher._get_latest_timestamp(pd.DataFrame())

    assert result is None


# ============================================================
# VOLUME PROCESSING
# ============================================================


def test_volume_processing_adds_volume_type(
    fetcher,
    sample_ohlcv,
):
    result = fetcher._process_asset_volume(
        sample_ohlcv.copy(),
        "EUR/USD",
    )

    assert "volume_type" in result.columns


def test_volume_processing_adds_normalized_volume(
    fetcher,
    sample_ohlcv,
):
    result = fetcher._process_asset_volume(
        sample_ohlcv.copy(),
        "EUR/USD",
    )

    assert "normalized_volume" in result.columns


def test_volume_is_numeric_after_processing(
    fetcher,
    sample_ohlcv,
):
    result = fetcher._process_asset_volume(
        sample_ohlcv.copy(),
        "EUR/USD",
    )

    assert pd.api.types.is_numeric_dtype(result["volume"])


def test_volume_processing_without_volume_column(
    fetcher,
):
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
        }
    )

    result = fetcher._process_asset_volume(
        df,
        "EUR/USD",
    )

    assert "volume" in result.columns
    assert "volume_type" in result.columns
    assert "normalized_volume" in result.columns

    assert result["volume"].isna().all()
    assert result["normalized_volume"].isna().all()


# ============================================================
# CANDLE STATE
# ============================================================


def test_initialize_candle_state(fetcher):
    fetcher._initialize_candle_state(
        symbol="EURUSD",
        timeframe="1min",
    )

    assert "EUR/USD" in fetcher.candle_state
    assert "1min" in fetcher.candle_state["EUR/USD"]

    state = fetcher.candle_state["EUR/USD"]["1min"]

    assert "last_candle" in state
    assert "next_check" in state
    assert "initialized" in state


def test_initial_candle_state_is_not_initialized(
    fetcher,
):
    fetcher._initialize_candle_state(
        symbol="EURUSD",
        timeframe="5min",
    )

    state = fetcher.candle_state["EUR/USD"]["5min"]

    assert state["initialized"] is False
    assert state["last_candle"] is None


# ============================================================
# OFFLINE MODE
# ============================================================


def test_offline_fetch_returns_empty_dataframe(
    fetcher,
):
    result = fetcher._fetch_twelve_data_timeseries(
        symbol="EUR/USD",
        timeframe="1min",
        start_date=None,
        outputsize=10,
    )

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ============================================================
# FETCH DATA OFFLINE
# ============================================================


def test_fetch_data_offline_returns_dataframe(
    fetcher,
):
    result = fetcher.fetch_data(
        symbol="EURUSD",
        timeframe="1min",
        outputsize=10,
    )

    assert isinstance(result, pd.DataFrame)


# ============================================================
# MULTI-TIMEFRAME OFFLINE
# ============================================================


def test_fetch_multi_timeframe_returns_dictionary(
    fetcher,
):
    result = fetcher.fetch_multi_timeframe_data(
        symbol="EURUSD",
        timeframes={
            "execution": "1min",
            "setup": "5min",
            "regime": "15min",
            "bias": "1h",
        },
    )

    assert isinstance(result, dict)

    assert set(result.keys()) == {
        "execution",
        "setup",
        "regime",
        "bias",
    }
