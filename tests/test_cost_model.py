# ```python
"""
============================================================
COST MODEL TEST SUITE — MVP
============================================================

PURPOSE
-------
This file tests the mathematical behavior of CostModel.

IMPORTANT
---------
These tests DO NOT connect to a broker.

They use controlled values to verify that CostModel correctly
handles:

    1. Long entry execution
    2. Short entry execution
    3. Long exit execution
    4. Short exit execution
    5. Commission calculation
    6. Swap calculation
    7. Currency translation
    8. Round-trip cost calculation
    9. Zero-cost execution
   10. Invalid input handling

The broker will be connected later through a separate adapter.
The CostModel itself remains independent of the broker.

Run with:

    pytest -v

============================================================
"""

import pytest

from src.backtest.cost_model import CostModel

# ============================================================
# TEST CONFIGURATION
# ============================================================

TEST_CONFIG = {
    "spread": 0.0002,
    "contract_multiplier": 1.0,
    "point_value": 10.0,
    "pip_scale": 0.0001,
    "slippage_type": "fixed",
    "slippage_value": 0.00015,
    "market_impact_factor": 0.0,
    "commission_type": "flat",
    "commission_value": 2.0,
    "maker_fee": 0.0,
    "taker_fee": 0.0,
    "swap_rate_long": 0.0,
    "swap_rate_short": 0.0,
}


# ============================================================
# FIXTURE
# ============================================================


@pytest.fixture
def cost_model():
    """
    Creates a fresh CostModel for each test.
    """
    return CostModel(TEST_CONFIG.copy())


# ============================================================
# 1. ZERO-COST TEST
# ============================================================


def test_zero_cost_entry_returns_raw_price():
    """
    With spread and slippage set to zero, the execution price
    must equal the raw market price.
    """

    model = CostModel(
        {
            "spread": 0.0,
            "slippage_type": "fixed",
            "slippage_value": 0.0,
        }
    )

    raw_price = 1.08560

    long_price = model.get_entry_price(
        raw_price=raw_price,
        direction="LONG",
    )

    short_price = model.get_entry_price(
        raw_price=raw_price,
        direction="SHORT",
    )

    assert long_price == pytest.approx(raw_price)
    assert short_price == pytest.approx(raw_price)


# ============================================================
# 2. LONG ENTRY
# ============================================================


def test_long_entry_applies_spread_and_slippage(cost_model):
    """
    LONG entry crosses to the Ask side.

    Expected:

        raw price
        + half spread
        + slippage
    """

    raw_price = 1.08560

    expected = raw_price + 0.00010 + 0.00015

    result = cost_model.get_entry_price(
        raw_price=raw_price,
        direction="LONG",
    )

    assert result == pytest.approx(expected)


# ============================================================
# 3. SHORT ENTRY
# ============================================================


def test_short_entry_applies_spread_and_slippage(cost_model):
    """
    SHORT entry crosses to the Bid side.

    Expected:

        raw price
        - half spread
        - slippage
    """

    raw_price = 1.08560

    expected = raw_price - 0.00010 - 0.00015

    result = cost_model.get_entry_price(
        raw_price=raw_price,
        direction="SHORT",
    )

    assert result == pytest.approx(expected)


# ============================================================
# 4. LONG EXIT
# ============================================================


def test_long_exit_applies_spread_and_slippage(cost_model):
    """
    Closing a LONG means selling at the Bid.

    Expected:

        raw price
        - half spread
        - slippage
    """

    raw_price = 1.08650

    expected = raw_price - 0.00010 - 0.00015

    result = cost_model.get_exit_price(
        raw_price=raw_price,
        direction="LONG",
    )

    assert result == pytest.approx(expected)


# ============================================================
# 5. SHORT EXIT
# ============================================================


def test_short_exit_applies_spread_and_slippage(cost_model):
    """
    Closing a SHORT means buying back at the Ask.

    Expected:

        raw price
        + half spread
        + slippage
    """

    raw_price = 1.08450

    expected = raw_price + 0.00010 + 0.00015

    result = cost_model.get_exit_price(
        raw_price=raw_price,
        direction="SHORT",
    )

    assert result == pytest.approx(expected)


# ============================================================
# 6. COMMISSION
# ============================================================


def test_flat_commission(cost_model):
    """
    Flat commission should equal:

        commission_value × size
    """

    result = cost_model.calculate_commission(
        size=1.0,
        price=1.08560,
    )

    assert result == pytest.approx(2.0)


def test_flat_commission_scales_with_size(cost_model):
    """
    Commission should scale with position size.
    """

    result = cost_model.calculate_commission(
        size=2.0,
        price=1.08560,
    )

    assert result == pytest.approx(4.0)


# ============================================================
# 7. PERCENTAGE COMMISSION
# ============================================================


def test_percentage_commission():
    """
    Percentage commission should be calculated from:

        price × size × contract_multiplier × percentage
    """

    model = CostModel(
        {
            "commission_type": "percentage",
            "commission_value": 0.10,
            "contract_multiplier": 1.0,
        }
    )

    result = model.calculate_commission(
        size=1.0,
        price=100.0,
    )

    expected = 100.0 * 0.10 / 100.0

    assert result == pytest.approx(expected)


# ============================================================
# 8. SWAP
# ============================================================


def test_long_swap():
    """
    Long swap should use swap_rate_long.
    """

    model = CostModel(
        {
            "swap_rate_long": 2.0,
            "swap_rate_short": -1.0,
        }
    )

    result = model.calculate_swap(
        size=1.0,
        direction="LONG",
        holding_days=3.0,
    )

    assert result == pytest.approx(6.0)


def test_short_swap():
    """
    Short swap should use swap_rate_short.
    """

    model = CostModel(
        {
            "swap_rate_long": 2.0,
            "swap_rate_short": -1.0,
        }
    )

    result = model.calculate_swap(
        size=1.0,
        direction="SHORT",
        holding_days=3.0,
    )

    assert result == pytest.approx(-3.0)


# ============================================================
# 9. CURRENCY TRANSLATION
# ============================================================


def test_translate_to_currency(cost_model):
    """
    Converts price movement into monetary value.

    Example:

        price difference = 0.0010
        pip scale        = 0.0001
        points            = 10 pips
        point value       = $10

        result = $100
    """

    result = cost_model.translate_to_currency(
        price_difference=0.0010,
        size=1.0,
    )

    assert result == pytest.approx(100.0)


# ============================================================
# 10. INVALID DIRECTION
# ============================================================


def test_invalid_entry_direction_raises_error(cost_model):
    """
    Unknown execution directions must fail rather than silently
    producing an incorrect price.
    """

    with pytest.raises(ValueError):
        cost_model.get_entry_price(
            raw_price=1.08560,
            direction="INVALID",
        )


def test_invalid_exit_direction_raises_error(cost_model):
    """
    Unknown exit directions must also fail.
    """

    with pytest.raises(ValueError):
        cost_model.get_exit_price(
            raw_price=1.08560,
            direction="INVALID",
        )


# ============================================================
# 11. SLIPPAGE MUST NOT BE NEGATIVE
# ============================================================


def test_negative_slippage_is_rejected():
    """
    Negative slippage is invalid configuration.

    CostModel should reject it during initialization rather
    than silently changing the user's configuration.
    """

    with pytest.raises(ValueError, match="slippage_value must be >= 0"):
        CostModel(
            {
                "spread": 0.0002,
                "slippage_type": "fixed",
                "slippage_value": -0.0005,
            }
        )


# ============================================================
# 12. ENTRY/EXIT ASYMMETRY
# ============================================================


def test_long_round_trip_execution_is_asymmetric(cost_model):
    """
    A LONG trade must pay friction on both sides.

    Entry moves upward from raw price.
    Exit moves downward from raw price.
    """

    raw_entry = 1.08560
    raw_exit = 1.08650

    entry = cost_model.get_entry_price(
        raw_price=raw_entry,
        direction="LONG",
    )

    exit_price = cost_model.get_exit_price(
        raw_price=raw_exit,
        direction="LONG",
    )

    assert entry > raw_entry
    assert exit_price < raw_exit


def test_short_round_trip_execution_is_asymmetric(cost_model):
    """
    A SHORT trade must also pay friction on both sides.

    Entry moves downward from raw price.
    Exit moves upward from raw price.
    """

    raw_entry = 1.08560
    raw_exit = 1.08450

    entry = cost_model.get_entry_price(
        raw_price=raw_entry,
        direction="SHORT",
    )

    exit_price = cost_model.get_exit_price(
        raw_price=raw_exit,
        direction="SHORT",
    )

    assert entry < raw_entry
    assert exit_price > raw_exit


# ============================================================
# 13. MANUAL LONG TRADE MATH
# ============================================================


def test_manual_long_trade_math(cost_model):
    """
    Explicitly verifies the example used during CostModel design.

    Raw entry:
        1.08560

    Raw exit:
        1.08650

    Spread:
        0.00020

    Half spread:
        0.00010

    Slippage:
        0.00015
    """

    raw_entry = 1.08560
    raw_exit = 1.08650

    entry = cost_model.get_entry_price(
        raw_price=raw_entry,
        direction="LONG",
    )

    exit_price = cost_model.get_exit_price(
        raw_price=raw_exit,
        direction="LONG",
    )

    expected_entry = 1.08585
    expected_exit = 1.08625

    assert entry == pytest.approx(expected_entry)
    assert exit_price == pytest.approx(expected_exit)

    gross_price_difference = exit_price - entry

    assert gross_price_difference == pytest.approx(0.00040)


# ============================================================
# END OF TEST FILE
# ============================================================
