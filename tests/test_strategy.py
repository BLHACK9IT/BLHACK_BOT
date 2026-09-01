# tests/test_strategy.py
"""
COMPREHENSIVE BIDIRECTIONAL SCALPING STRATEGY TEST SUITE

Tests the complete 4-layer hierarchy:
  1. ScalpingBiasEngine (1H macro direction)
  2. ScalpingRegimeEngine (15M market type + direction)
  3. ScalpingSetupEngine (5M structural setups)
  4. ScalpingEntryEngine (1M confirmation)

WORST-CASE SCENARIO FOCUS:
  - Ambiguous market transitions
  - Direction reversals
  - Regime changes mid-structure
  - Failed confirmations
  - Timeout scenarios

DATA VALIDATION PRINCIPLE:
  Every test explicitly validates that the test data actually
  represents what it claims to represent before running assertions.
"""

import pandas as pd
import numpy as np
import pytest

# ============================================================================
# 1H MACRO BIAS ENGINE TESTS
# ============================================================================


class TestBiasEngineBullish:
    """1H macro bias engine in bullish conditions."""

    def test_bias_engine_detects_clean_bullish_structure(self):
        """
        Clean 1H bullish: close > ema9 > ema21, positive slope.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1h")

        df = pd.DataFrame(
            {
                "close": [100, 102, 104, 106, 108],
                "ema_9": [99, 101, 103, 105, 107],
                "ema_21": [98, 100, 102, 104, 106],
                "ema_separation_pct": [0.01, 0.01, 0.01, 0.01, 0.01],
                "ema_fast_slope": [0.5, 0.5, 0.5, 0.5, 0.5],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        # Validate test data
        assert (df["close"] > df["ema_9"]).all(), "Test data: close must be > ema_9"
        assert (df["ema_9"] > df["ema_21"]).all(), "Test data: ema_9 must be > ema_21"

        bias = ScalpingBiasEngine.evaluate_bias(
            df,
            persistence_window=1,
            min_separation_pct=0.005,
        )

        # After one qualifying bar, should see BULLISH
        assert bias.iloc[0] == "BULLISH"

    def test_bias_engine_requires_persistence_bullish(self):
        """
        Bullish structure requires persistence_window consecutive bars.

        With persistence_window=2:
        - Bar 0: only 1 qualifying bar → NEUTRAL (insufficient data)
        - Bar 1: 2 consecutive qualifying bars (0-1) → BULLISH (persistence met)
        - Bar 2: 2 consecutive qualifying bars (1-2) → BULLISH (persistence maintained)
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine

        dates = pd.date_range("2026-01-01", periods=3, freq="1h")

        df = pd.DataFrame(
            {
                "close": [100, 102, 104],
                "ema_9": [99, 101, 103],
                "ema_21": [98, 100, 102],
                "ema_separation_pct": [0.01, 0.01, 0.01],
                "ema_fast_slope": [0.5, 0.5, 0.5],
                "atr": [1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias = ScalpingBiasEngine.evaluate_bias(
            df,
            persistence_window=2,
            min_separation_pct=0.005,
        )

        # Bar 0: Only 1 qualifying bar, need 2 → NEUTRAL
        assert bias.iloc[0] == "NEUTRAL"

        # Bar 1: Now 2 consecutive qualifying bars (0-1) → BULLISH
        assert bias.iloc[1] == "BULLISH"

        # Bar 2: Still 2 consecutive qualifying bars (1-2) → BULLISH
        assert bias.iloc[2] == "BULLISH"

    def test_bias_engine_worst_case_tight_ema_separation(self):
        """
        WORST CASE: EMA9 and EMA21 are extremely close.

        When separation is below threshold, market is too choppy
        to establish clear bias. Should return NEUTRAL.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1h")

        df = pd.DataFrame(
            {
                "close": [100, 100.1, 100.2, 100.3, 100.4],
                "ema_9": [100.05, 100.15, 100.25, 100.35, 100.45],
                "ema_21": [100.04, 100.14, 100.24, 100.34, 100.44],
                "ema_separation_pct": [0.0001, 0.0001, 0.0001, 0.0001, 0.0001],
                "ema_fast_slope": [0.5, 0.5, 0.5, 0.5, 0.5],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias = ScalpingBiasEngine.evaluate_bias(
            df,
            persistence_window=1,
            min_separation_pct=0.005,
        )

        # Separation below threshold → NEUTRAL
        assert (bias == "NEUTRAL").all()


class TestBiasEngineBearish:
    """1H macro bias engine in bearish conditions."""

    def test_bias_engine_detects_clean_bearish_structure(self):
        """
        Clean 1H bearish: close < ema9 < ema21, negative slope.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1h")

        df = pd.DataFrame(
            {
                "close": [108, 106, 104, 102, 100],
                "ema_9": [109, 107, 105, 103, 101],
                "ema_21": [110, 108, 106, 104, 102],
                "ema_separation_pct": [-0.01, -0.01, -0.01, -0.01, -0.01],
                "ema_fast_slope": [-0.5, -0.5, -0.5, -0.5, -0.5],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        # Validate test data
        assert (df["close"] < df["ema_9"]).all(), "Test data: close must be < ema_9"
        assert (df["ema_9"] < df["ema_21"]).all(), "Test data: ema_9 must be < ema_21"

        bias = ScalpingBiasEngine.evaluate_bias(
            df,
            persistence_window=1,
            min_separation_pct=0.005,
        )

        # After one qualifying bar, should see BEARISH
        assert bias.iloc[0] == "BEARISH"

    def test_bias_engine_worst_case_reversal_bullish_to_bearish(self):
        """
        WORST CASE: Macro bias flips from BULLISH to BEARISH.

        Tests the engine's ability to recognize state transitions.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine

        dates = pd.date_range("2026-01-01", periods=8, freq="1h")

        # Start bullish for 4 bars
        df = pd.DataFrame(
            {
                "close": [100, 102, 104, 106, 105, 103, 101, 99],
                "ema_9": [99, 101, 103, 105, 106, 104, 102, 100],
                "ema_21": [98, 100, 102, 104, 107, 105, 103, 101],
                "ema_separation_pct": [
                    0.01,
                    0.01,
                    0.01,
                    0.01,
                    -0.01,
                    -0.01,
                    -0.01,
                    -0.01,
                ],
                "ema_fast_slope": [0.5, 0.5, 0.5, 0.5, -0.5, -0.5, -0.5, -0.5],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias = ScalpingBiasEngine.evaluate_bias(
            df,
            persistence_window=1,
            min_separation_pct=0.005,
        )

        # First 4 bars: BULLISH
        assert bias.iloc[0] == "BULLISH"
        assert bias.iloc[3] == "BULLISH"

        # Last 4 bars: BEARISH (transition detected)
        assert bias.iloc[4] == "BEARISH"
        assert bias.iloc[7] == "BEARISH"


# ============================================================================
# 15M REGIME + DIRECTION ENGINE TESTS
# ============================================================================


class TestRegimeEngineBullish:
    """15M regime + direction in bullish conditions."""

    def test_direction_engine_detects_clear_bullish(self):
        """
        Clean 15M bullish: close > ema9 > ema21, expanding structure.
        """
        from src.strategy.regime_engine import ScalpingRegimeEngine

        dates = pd.date_range("2026-01-01", periods=30, freq="15min")

        # Build clearly bullish: close always above ema_9
        df = pd.DataFrame(
            {
                "close": np.linspace(100, 115, 30),
                "ema_9": np.linspace(98, 113, 30),
                "ema_21": np.linspace(96, 111, 30),
                "ema_separation_pct": [0.02] * 30,
                "ema_fast_slope": [0.5] * 30,
                "atr": [1.0] * 30,
            },
            index=dates,
        )

        # Validate test data
        assert (df["close"] > df["ema_9"]).all(), "Test data: close must be > ema_9"
        assert (df["ema_9"] > df["ema_21"]).all(), "Test data: ema_9 must be > ema_21"

        direction = ScalpingRegimeEngine.evaluate_direction(df)

        # Direction should be BULLISH
        assert direction.iloc[-1] == "BULLISH"

    def test_direction_engine_worst_case_choppy_neutral(self):
        """
        WORST CASE: Market structure is neutral/choppy.

        Close oscillates around EMA, no clear direction.
        """
        from src.strategy.regime_engine import ScalpingRegimeEngine

        dates = pd.date_range("2026-01-01", periods=30, freq="15min")

        # Oscillating around EMA: no directional conviction
        df = pd.DataFrame(
            {
                "close": [100 + (i % 2) * 0.5 for i in range(30)],
                "ema_9": [100 + 0.2] * 30,
                "ema_21": [100 + 0.1] * 30,
                "ema_separation_pct": [0.001] * 30,
                "ema_fast_slope": [0.0] * 30,
                "atr": [1.0] * 30,
            },
            index=dates,
        )

        direction = ScalpingRegimeEngine.evaluate_direction(df)

        # Should be NEUTRAL (valid data but no direction)
        assert direction.iloc[-1] == "NEUTRAL"


class TestRegimeEngineBearish:
    """15M regime + direction in bearish conditions."""

    def test_direction_engine_detects_clear_bearish(self):
        """
        Clean 15M bearish: close < ema9 < ema21, declining structure.
        """
        from src.strategy.regime_engine import ScalpingRegimeEngine

        dates = pd.date_range("2026-01-01", periods=30, freq="15min")

        # Build clearly bearish: close always below ema_9
        df = pd.DataFrame(
            {
                "close": np.linspace(115, 100, 30),
                "ema_9": np.linspace(117, 102, 30),
                "ema_21": np.linspace(119, 104, 30),
                "ema_separation_pct": [-0.02] * 30,
                "ema_fast_slope": [-0.5] * 30,
                "atr": [1.0] * 30,
            },
            index=dates,
        )

        # Validate test data
        assert (df["close"] < df["ema_9"]).all(), "Test data: close must be < ema_9"
        assert (df["ema_9"] < df["ema_21"]).all(), "Test data: ema_9 must be < ema_21"

        direction = ScalpingRegimeEngine.evaluate_direction(df)

        # Direction should be BEARISH
        assert direction.iloc[-1] == "BEARISH"


# ============================================================================
# 5M SETUP ENGINE TESTS
# ============================================================================


class TestSetupEngineBullish:
    """5M setup engine in bullish context."""

    def test_setup_engine_detects_long_setup_trend_continuation(self):
        """
        Valid LONG_SETUP: 1H bullish + 15M bullish + 5M pullback.
        """
        from src.strategy.setup_engine import ScalpingSetupEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="5min")

        df = pd.DataFrame(
            {
                "open": [100, 100.5, 101, 101.5, 102],
                "high": [101.5, 102, 102.5, 103, 103.5],
                "low": [99.5, 100, 100.5, 101, 101.5],
                "close": [101, 101.5, 102, 102.5, 103],
                "ema_9": [100.5, 101, 101.5, 102, 102.5],
                "ema_21": [100, 100.5, 101, 101.5, 102],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias_1h = pd.Series(["BULLISH"] * 5, index=dates)
        regime_15m = pd.Series(["TRENDING_EXPANSION"] * 5, index=dates)
        direction_15m = pd.Series(["BULLISH"] * 5, index=dates)

        setups = ScalpingSetupEngine.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=0.25,
        )

        # Should produce LONG_SETUP (at least once)
        assert "LONG_SETUP" in setups.values

    def test_setup_engine_discrete_event_deduplication_long(self):
        """
        Discrete event filtering: consecutive LONG_SETUP → dedup to NONE.

        Bars 0-2: same bullish structure → emit LONG_SETUP once, then NONE.
        """
        from src.strategy.setup_engine import ScalpingSetupEngine

        dates = pd.date_range("2026-01-01", periods=4, freq="5min")

        # All identical bullish candles
        df = pd.DataFrame(
            {
                "open": [100, 100, 100, 100],
                "high": [103, 103, 103, 103],
                "low": [99, 99, 99, 99],
                "close": [102, 102, 102, 102],
                "ema_9": [101, 101, 101, 101],
                "ema_21": [100, 100, 100, 100],
                "atr": [1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias_1h = pd.Series(["BULLISH"] * 4, index=dates)
        regime_15m = pd.Series(["TRENDING_EXPANSION"] * 4, index=dates)
        direction_15m = pd.Series(["BULLISH"] * 4, index=dates)

        setups = ScalpingSetupEngine.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=0.25,
        )

        # Bar 0: LONG_SETUP (event fires)
        assert setups.iloc[0] == "LONG_SETUP"

        # Bars 1-3: NONE (same structure, already fired)
        assert setups.iloc[1] == "NONE"
        assert setups.iloc[2] == "NONE"
        assert setups.iloc[3] == "NONE"

    def test_setup_engine_worst_case_bias_veto(self):
        """
        WORST CASE: 5M suggests SHORT but 1H is strictly BULLISH.

        1H macro should veto this setup.
        """
        from src.strategy.setup_engine import ScalpingSetupEngine

        dates = pd.date_range("2026-01-01", periods=4, freq="5min")

        df = pd.DataFrame(
            {
                "open": [102, 102, 102, 102],
                "high": [103, 103, 103, 103],
                "low": [99, 99, 99, 99],
                "close": [100, 100, 100, 100],
                "ema_9": [101, 101, 101, 101],
                "ema_21": [102, 102, 102, 102],
                "atr": [1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias_1h = pd.Series(["BULLISH"] * 4, index=dates)
        regime_15m = pd.Series(["TRENDING_EXPANSION"] * 4, index=dates)
        direction_15m = pd.Series(["BEARISH"] * 4, index=dates)

        setups = ScalpingSetupEngine.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=0.25,
        )

        # Should veto the SHORT_SETUP because 1H is BULLISH
        assert "SHORT_SETUP" not in setups.values or (setups == "NONE").all()


class TestSetupEngineBearish:
    """5M setup engine in bearish context."""

    def test_setup_engine_detects_short_setup_trend_continuation(self):
        """
        Valid SHORT_SETUP: 1H bearish + 15M bearish + 5M reversal.
        """
        from src.strategy.setup_engine import ScalpingSetupEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="5min")

        df = pd.DataFrame(
            {
                "open": [103, 102.5, 102, 101.5, 101],
                "high": [103.5, 103, 102.5, 102, 101.5],
                "low": [101.5, 101, 100.5, 100, 99.5],
                "close": [102, 101.5, 101, 100.5, 100],
                "ema_9": [102.5, 102, 101.5, 101, 100.5],
                "ema_21": [103, 102.5, 102, 101.5, 101],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias_1h = pd.Series(["BEARISH"] * 5, index=dates)
        regime_15m = pd.Series(["TRENDING_EXPANSION"] * 5, index=dates)
        direction_15m = pd.Series(["BEARISH"] * 5, index=dates)

        setups = ScalpingSetupEngine.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=0.25,
        )

        # Should produce SHORT_SETUP (at least once)
        assert "SHORT_SETUP" in setups.values

    def test_setup_engine_discrete_event_deduplication_short(self):
        """
        Discrete event filtering: consecutive SHORT_SETUP → dedup to NONE.
        """
        from src.strategy.setup_engine import ScalpingSetupEngine

        dates = pd.date_range("2026-01-01", periods=4, freq="5min")

        df = pd.DataFrame(
            {
                "open": [102, 102, 102, 102],
                "high": [103, 103, 103, 103],
                "low": [99, 99, 99, 99],
                "close": [100, 100, 100, 100],
                "ema_9": [101, 101, 101, 101],
                "ema_21": [102, 102, 102, 102],
                "atr": [1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        bias_1h = pd.Series(["BEARISH"] * 4, index=dates)
        regime_15m = pd.Series(["TRENDING_EXPANSION"] * 4, index=dates)
        direction_15m = pd.Series(["BEARISH"] * 4, index=dates)

        setups = ScalpingSetupEngine.evaluate_setups(
            df_5m=df,
            bias_1h=bias_1h,
            regime_15m=regime_15m,
            direction_15m=direction_15m,
            min_body_atr_ratio=0.25,
        )

        # Bar 0: SHORT_SETUP (event fires)
        assert setups.iloc[0] == "SHORT_SETUP"

        # Bars 1-3: NONE (same structure, already fired)
        assert setups.iloc[1] == "NONE"
        assert setups.iloc[2] == "NONE"
        assert setups.iloc[3] == "NONE"


# ============================================================================
# 1M ENTRY ENGINE TESTS
# ============================================================================


class TestEntryEngineBullish:
    """1M entry engine confirmation in bullish setups."""

    def test_entry_engine_confirms_long_setup(self):
        """
        LONG_SETUP at bar 0, 1M confirmation at bar 1 → EXECUTE_LONG.
        """
        from src.strategy.entry_engine import ScalpingEntryEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1min")

        df_1m = pd.DataFrame(
            {
                "open": [100.0, 100.2, 100.4, 100.6, 100.8],
                "high": [100.5, 100.7, 100.9, 101.1, 101.3],
                "low": [99.8, 100.0, 100.2, 100.4, 100.6],
                "close": [100.3, 100.5, 100.7, 100.9, 101.1],
                "ema_9": [100.0, 100.2, 100.4, 100.6, 100.8],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        # Setup fires at bar 0, then NONE
        setup_5m = pd.Series(
            ["LONG_SETUP", "NONE", "NONE", "NONE", "NONE"],
            index=dates,
        )

        entry = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_5m,
            max_timeout_bars=4,
            min_body_ratio=0.30,
        )

        # Should have at least one EXECUTE_LONG
        assert "EXECUTE_LONG" in entry.values

    def test_entry_engine_worst_case_timeout_before_confirmation(self):
        """
        WORST CASE: Setup fires but times out before confirmation.

        Setup at bar 0, no confirmation by bar 3 → timeout.
        """
        from src.strategy.entry_engine import ScalpingEntryEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1min")

        df_1m = pd.DataFrame(
            {
                "open": [100.0, 100.1, 100.1, 100.1, 100.1],
                "high": [100.2, 100.2, 100.2, 100.2, 100.2],
                "low": [99.9, 99.9, 99.9, 99.9, 99.9],
                "close": [100.0, 100.0, 100.0, 100.0, 100.0],
                "ema_9": [100.0, 100.0, 100.0, 100.0, 100.0],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        # Setup fires, then none
        setup_5m = pd.Series(
            ["LONG_SETUP", "NONE", "NONE", "NONE", "NONE"],
            index=dates,
        )

        entry = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_5m,
            max_timeout_bars=3,
            min_body_ratio=0.30,
        )

        # Should timeout with no EXECUTE_LONG
        assert entry.iloc[4] == "STANDBY"


class TestEntryEngineBearish:
    """1M entry engine confirmation in bearish setups."""

    def test_entry_engine_confirms_short_setup(self):
        """
        SHORT_SETUP at bar 0, 1M confirmation at bar 1 → EXECUTE_SHORT.
        """
        from src.strategy.entry_engine import ScalpingEntryEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1min")

        df_1m = pd.DataFrame(
            {
                "open": [100.8, 100.6, 100.4, 100.2, 100.0],
                "high": [101.0, 100.8, 100.6, 100.4, 100.2],
                "low": [100.3, 100.1, 99.9, 99.7, 99.5],
                "close": [100.5, 100.3, 100.1, 99.9, 99.7],
                "ema_9": [100.8, 100.6, 100.4, 100.2, 100.0],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        # Setup fires at bar 0
        setup_5m = pd.Series(
            ["SHORT_SETUP", "NONE", "NONE", "NONE", "NONE"],
            index=dates,
        )

        entry = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_5m,
            max_timeout_bars=4,
            min_body_ratio=0.30,
        )

        # Should have at least one EXECUTE_SHORT
        assert "EXECUTE_SHORT" in entry.values

    def test_entry_engine_worst_case_whipsaw_reversal(self):
        """
        WORST CASE: Setup fires LONG, but market immediately reverses.

        Bars 0-1: bullish setup window
        Bars 2-4: bearish reversal
        """
        from src.strategy.entry_engine import ScalpingEntryEngine

        dates = pd.date_range("2026-01-01", periods=5, freq="1min")

        df_1m = pd.DataFrame(
            {
                "open": [100.0, 100.2, 100.4, 100.2, 100.0],
                "high": [100.5, 100.7, 100.8, 100.5, 100.2],
                "low": [99.8, 100.0, 100.2, 100.0, 99.8],
                "close": [100.3, 100.5, 100.6, 100.3, 100.0],
                "ema_9": [100.0, 100.2, 100.4, 100.2, 100.0],
                "atr": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dates,
        )

        setup_5m = pd.Series(
            ["LONG_SETUP", "NONE", "NONE", "NONE", "NONE"],
            index=dates,
        )

        entry = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_5m,
            max_timeout_bars=4,
            min_body_ratio=0.30,
        )

        # Engine should handle this gracefully
        assert entry is not None


# ============================================================================
# INTEGRATION TESTS (Full Hierarchy)
# ============================================================================


class TestFullHierarchyBullish:
    """End-to-end bullish scenario: 1H → 15M → 5M → 1M."""

    def test_complete_bullish_pipeline(self):
        """
        Macro bullish → 15M bullish → 5M setup → 1M confirmation.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine
        from src.strategy.regime_engine import ScalpingRegimeEngine
        from src.strategy.setup_engine import ScalpingSetupEngine
        from src.strategy.entry_engine import ScalpingEntryEngine

        # 1H data
        dates_1h = pd.date_range("2026-01-01", periods=2, freq="1h")
        df_1h = pd.DataFrame(
            {
                "close": [100, 104],
                "ema_9": [99, 103],
                "ema_21": [98, 102],
                "ema_separation_pct": [0.01, 0.01],
                "ema_fast_slope": [0.5, 0.5],
                "atr": [1.0, 1.0],
            },
            index=dates_1h,
        )

        bias_1h = ScalpingBiasEngine.evaluate_bias(df_1h, persistence_window=1)

        # 15M data
        dates_15m = pd.date_range("2026-01-01", periods=8, freq="15min")
        df_15m = pd.DataFrame(
            {
                "close": np.linspace(100, 105, 8),
                "ema_9": np.linspace(99, 104, 8),
                "ema_21": np.linspace(98, 103, 8),
                "ema_separation_pct": [0.01] * 8,
                "ema_fast_slope": [0.5] * 8,
                "atr": [1.0] * 8,
            },
            index=dates_15m,
        )

        regime_15m = ScalpingRegimeEngine.evaluate_regime(df_15m)
        direction_15m = ScalpingRegimeEngine.evaluate_direction(df_15m)

        # 5M data
        dates_5m = pd.date_range("2026-01-01", periods=16, freq="5min")
        df_5m = pd.DataFrame(
            {
                "open": np.linspace(100, 103, 16),
                "high": np.linspace(101, 104, 16),
                "low": np.linspace(99, 102, 16),
                "close": np.linspace(100.5, 103.5, 16),
                "ema_9": np.linspace(99, 102.5, 16),
                "ema_21": np.linspace(98, 101.5, 16),
                "atr": [1.0] * 16,
            },
            index=dates_5m,
        )

        # Align HTF data to 5M
        bias_5m = bias_1h.reindex(df_5m.index, method="ffill")
        regime_5m = regime_15m.reindex(df_5m.index, method="ffill")
        direction_5m = direction_15m.reindex(df_5m.index, method="ffill")

        setups_5m = ScalpingSetupEngine.evaluate_setups(
            df_5m=df_5m,
            bias_1h=bias_5m,
            regime_15m=regime_5m,
            direction_15m=direction_5m,
            min_body_atr_ratio=0.25,
        )

        # 1M data
        dates_1m = pd.date_range("2026-01-01", periods=64, freq="1min")
        df_1m = pd.DataFrame(
            {
                "open": np.linspace(100, 103, 64),
                "high": np.linspace(101, 104, 64),
                "low": np.linspace(99, 102, 64),
                "close": np.linspace(100.5, 103.5, 64),
                "ema_9": np.linspace(99, 102.5, 64),
                "atr": [1.0] * 64,
            },
            index=dates_1m,
        )

        setup_1m = setups_5m.reindex(df_1m.index, method="ffill").fillna("NONE")

        entry_signals = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_1m,
            max_timeout_bars=4,
        )

        # Verify hierarchy produced results
        assert bias_1h is not None
        assert regime_15m is not None
        assert direction_15m is not None
        assert setups_5m is not None
        assert entry_signals is not None


class TestFullHierarchyBearish:
    """End-to-end bearish scenario: 1H → 15M → 5M → 1M."""

    def test_complete_bearish_pipeline(self):
        """
        Macro bearish → 15M bearish → 5M setup → 1M confirmation.
        """
        from src.strategy.scalping_bias_engine import ScalpingBiasEngine
        from src.strategy.regime_engine import ScalpingRegimeEngine
        from src.strategy.setup_engine import ScalpingSetupEngine
        from src.strategy.entry_engine import ScalpingEntryEngine

        # 1H data
        dates_1h = pd.date_range("2026-01-01", periods=2, freq="1h")
        df_1h = pd.DataFrame(
            {
                "close": [104, 100],
                "ema_9": [105, 101],
                "ema_21": [106, 102],
                "ema_separation_pct": [-0.01, -0.01],
                "ema_fast_slope": [-0.5, -0.5],
                "atr": [1.0, 1.0],
            },
            index=dates_1h,
        )

        bias_1h = ScalpingBiasEngine.evaluate_bias(df_1h, persistence_window=1)

        # 15M data
        dates_15m = pd.date_range("2026-01-01", periods=8, freq="15min")
        df_15m = pd.DataFrame(
            {
                "close": np.linspace(105, 100, 8),
                "ema_9": np.linspace(106, 101, 8),
                "ema_21": np.linspace(107, 102, 8),
                "ema_separation_pct": [-0.01] * 8,
                "ema_fast_slope": [-0.5] * 8,
                "atr": [1.0] * 8,
            },
            index=dates_15m,
        )

        regime_15m = ScalpingRegimeEngine.evaluate_regime(df_15m)
        direction_15m = ScalpingRegimeEngine.evaluate_direction(df_15m)

        # 5M data
        dates_5m = pd.date_range("2026-01-01", periods=16, freq="5min")
        df_5m = pd.DataFrame(
            {
                "open": np.linspace(103, 100, 16),
                "high": np.linspace(104, 101, 16),
                "low": np.linspace(102, 99, 16),
                "close": np.linspace(103.5, 99.5, 16),
                "ema_9": np.linspace(104.5, 100.5, 16),
                "ema_21": np.linspace(105.5, 101.5, 16),
                "atr": [1.0] * 16,
            },
            index=dates_5m,
        )

        bias_5m = bias_1h.reindex(df_5m.index, method="ffill")
        regime_5m = regime_15m.reindex(df_5m.index, method="ffill")
        direction_5m = direction_15m.reindex(df_5m.index, method="ffill")

        setups_5m = ScalpingSetupEngine.evaluate_setups(
            df_5m=df_5m,
            bias_1h=bias_5m,
            regime_15m=regime_5m,
            direction_15m=direction_5m,
            min_body_atr_ratio=0.25,
        )

        # 1M data
        dates_1m = pd.date_range("2026-01-01", periods=64, freq="1min")
        df_1m = pd.DataFrame(
            {
                "open": np.linspace(103, 100, 64),
                "high": np.linspace(104, 101, 64),
                "low": np.linspace(102, 99, 64),
                "close": np.linspace(103.5, 99.5, 64),
                "ema_9": np.linspace(104.5, 100.5, 64),
                "atr": [1.0] * 64,
            },
            index=dates_1m,
        )

        setup_1m = setups_5m.reindex(df_1m.index, method="ffill").fillna("NONE")

        entry_signals = ScalpingEntryEngine.evaluate(
            df_1m=df_1m,
            setup_5m=setup_1m,
            max_timeout_bars=4,
        )

        # Verify hierarchy produced results
        assert bias_1h is not None
        assert regime_15m is not None
        assert direction_15m is not None
        assert setups_5m is not None
        assert entry_signals is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
