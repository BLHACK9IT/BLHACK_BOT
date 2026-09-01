# src/backtest/cost_model.py

"""
======================================================================
COST MODEL — EXECUTION FRICTION V1
======================================================================

PURPOSE
-------

The CostModel represents the transaction-cost mathematics used by the
trading system.

It does NOT:

    - connect to a broker
    - submit orders
    - simulate a market
    - decide when to enter
    - decide when to exit
    - manage positions
    - determine strategy signals

Its responsibility is narrower:

    "Given an intended market price and execution-cost information,
     what execution price and transaction cost should be attributed
     to that trade?"

The model can operate using either:

    1. CONFIGURED COSTS
       Used when broker-specific historical execution information is
       unavailable.

    2. OBSERVED BID/ASK DATA
       Used when real broker market data is available.

This allows the same CostModel to be used during:

    - deterministic unit testing
    - historical research
    - paper trading
    - future live execution


======================================================================
V1 DESIGN PRINCIPLES
======================================================================

1. NO BROKER CONNECTION
   --------------------
   The CostModel is deliberately broker-agnostic.

   A future broker adapter is responsible for retrieving:

       - bid
       - ask
       - actual fill price
       - commission
       - execution information

   The CostModel only performs calculations.


2. NO UNIVERSAL ASSET ASSUMPTIONS
   ------------------------------
   The model does not claim that a particular asset always has a
   particular spread or slippage value.

   Example:

       EURUSD does not permanently mean "2 pips spread".

   Actual costs depend on broker, account, liquidity, session,
   volatility, order size and execution conditions.

   Therefore asset-specific values belong in configuration or
   broker-provided data.


3. EXPLICIT EXECUTION FRICTION
   ---------------------------
   Execution costs are kept separate:

       spread
       slippage
       commission
       swap

   This makes later analysis much easier.


4. DIRECTIONAL ASYMMETRY
   ----------------------
   Long and short execution correctly cross the bid/ask side.

       LONG ENTRY
           raw + half spread + slippage

       SHORT ENTRY
           raw - half spread - slippage

       LONG EXIT
           raw - half spread - slippage

       SHORT EXIT
           raw + half spread + slippage


5. FULL FILLS IN V1
   -----------------
   V1 assumes an order is fully filled.

   The following remain outside the CostModel:

       - partial fills
       - rejected orders
       - order-book depth
       - liquidity failure
       - gap execution
       - latency
       - order queue position

   These belong to the future broker/execution layer.


6. NO FALSE PRECISION
   -------------------
   If broker execution information is unavailable, configured values
   are treated as research assumptions rather than facts.


======================================================================
SUPPORTED CONFIGURATION
======================================================================

spread
    Absolute bid/ask spread when broker bid/ask is unavailable.

slippage_type
    Supported:

        "fixed"
        "atr"

    V1 deliberately keeps slippage simple.

slippage_value
    Fixed price-distance slippage or ATR multiplier depending on
    slippage_type.

commission_type
    Supported:

        "flat"
        "percentage"
        "per_lot"
        "maker_taker"

commission_value
    Value used by flat, percentage or per-lot commission models.

maker_fee
    Maker commission rate.

taker_fee
    Taker commission rate.

contract_multiplier
    Contract-size scaling factor.

point_value
    Monetary value assigned to one point/pip.

pip_scale
    Price distance represented by one point/pip.

swap_rate_long
    Financing cost/rate for long positions.

swap_rate_short
    Financing cost/rate for short positions.


======================================================================
IMPORTANT
======================================================================

The CostModel does not decide whether a cost value is realistic.

For paper/live trading:

    broker data > configured assumption

For historical testing:

    configured research assumption is used when actual historical
    execution data is unavailable.

This separation prevents the cost engine from becoming tied to a
specific broker or asset.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class CostModel:
    """
    Broker-agnostic transaction-cost calculation engine.

    The class performs execution-cost mathematics but does not connect
    to external broker APIs.
    """

    # ==============================================================
    # SUPPORTED VALUES
    # ==============================================================

    SUPPORTED_SLIPPAGE_TYPES = {
        "fixed",
        "atr",
    }

    SUPPORTED_COMMISSION_TYPES = {
        "flat",
        "percentage",
        "per_lot",
        "maker_taker",
    }

    LONG_DIRECTIONS = {
        "BUY",
        "LONG",
    }

    SHORT_DIRECTIONS = {
        "SELL",
        "SHORT",
    }

    # ==============================================================
    # DEFAULT CONFIGURATION
    # ==============================================================

    DEFAULT_CONFIG: Dict[str, Any] = {
        # No universal market-cost assumptions.
        # These are intentionally zero until supplied by configuration
        # or broker/execution data.
        "spread": 0.0,
        "slippage_type": "fixed",
        "slippage_value": 0.0,
        "commission_type": "flat",
        "commission_value": 0.0,
        "maker_fee": 0.0,
        "taker_fee": 0.0,
        "contract_multiplier": 1.0,
        "point_value": 1.0,
        "pip_scale": 0.0001,
        "swap_rate_long": 0.0,
        "swap_rate_short": 0.0,
    }

    # ==============================================================
    # INITIALIZATION
    # ==============================================================

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the CostModel.

        User-supplied configuration overrides the default configuration.

        Example:

            CostModel({
                "spread": 0.0002,
                "slippage_type": "fixed",
                "slippage_value": 0.0001,
                "commission_type": "flat",
                "commission_value": 2.0,
            })

        These values should represent either:

            - research assumptions, or
            - broker-provided specifications.
        """

        self.config = self.DEFAULT_CONFIG.copy()

        if config is not None:
            if not isinstance(config, dict):
                raise TypeError("config must be a dictionary or None.")

            self.config.update(config)

        self._validate_config()

    # ==============================================================
    # CONFIGURATION VALIDATION
    # ==============================================================

    def _validate_config(self) -> None:
        """
        Validate all configured cost parameters.

        Invalid configuration should fail early rather than silently
        producing misleading backtest or paper-trading results.
        """

        spread = self.config["spread"]

        if not isinstance(spread, (int, float)):
            raise TypeError("spread must be numeric.")

        if spread < 0:
            raise ValueError("spread must be >= 0.")

        slippage_type = self.config["slippage_type"]

        if slippage_type not in self.SUPPORTED_SLIPPAGE_TYPES:
            raise ValueError(
                "Unsupported slippage_type. "
                f"Expected one of: "
                f"{sorted(self.SUPPORTED_SLIPPAGE_TYPES)}"
            )

        slippage_value = self.config["slippage_value"]

        if not isinstance(slippage_value, (int, float)):
            raise TypeError("slippage_value must be numeric.")

        if slippage_value < 0:
            raise ValueError("slippage_value must be >= 0.")

        commission_type = self.config["commission_type"]

        if commission_type not in self.SUPPORTED_COMMISSION_TYPES:
            raise ValueError(
                "Unsupported commission_type. "
                f"Expected one of: "
                f"{sorted(self.SUPPORTED_COMMISSION_TYPES)}"
            )

        commission_value = self.config["commission_value"]

        if not isinstance(commission_value, (int, float)):
            raise TypeError("commission_value must be numeric.")

        if commission_value < 0:
            raise ValueError("commission_value must be >= 0.")

        maker_fee = self.config["maker_fee"]
        taker_fee = self.config["taker_fee"]

        if not isinstance(maker_fee, (int, float)):
            raise TypeError("maker_fee must be numeric.")

        if not isinstance(taker_fee, (int, float)):
            raise TypeError("taker_fee must be numeric.")

        if maker_fee < 0 or taker_fee < 0:
            raise ValueError("maker_fee and taker_fee must be >= 0.")

        contract_multiplier = self.config["contract_multiplier"]

        if not isinstance(contract_multiplier, (int, float)):
            raise TypeError("contract_multiplier must be numeric.")

        if contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be > 0.")

        point_value = self.config["point_value"]

        if not isinstance(point_value, (int, float)):
            raise TypeError("point_value must be numeric.")

        if point_value <= 0:
            raise ValueError("point_value must be > 0.")

        pip_scale = self.config["pip_scale"]

        if not isinstance(pip_scale, (int, float)):
            raise TypeError("pip_scale must be numeric.")

        if pip_scale <= 0:
            raise ValueError("pip_scale must be > 0.")

        swap_long = self.config["swap_rate_long"]
        swap_short = self.config["swap_rate_short"]

        if not isinstance(swap_long, (int, float)):
            raise TypeError("swap_rate_long must be numeric.")

        if not isinstance(swap_short, (int, float)):
            raise TypeError("swap_rate_short must be numeric.")

    # ==============================================================
    # DIRECTION VALIDATION
    # ==============================================================

    @classmethod
    def _normalize_direction(
        cls,
        direction: str,
    ) -> str:
        """
        Normalize BUY/LONG and SELL/SHORT into a common representation.
        """

        if not isinstance(direction, str):
            raise TypeError("direction must be a string.")

        normalized = direction.upper().strip()

        if normalized in cls.LONG_DIRECTIONS:
            return "LONG"

        if normalized in cls.SHORT_DIRECTIONS:
            return "SHORT"

        raise ValueError(f"Invalid execution direction: {direction}")

    # ==============================================================
    # BROKER BID/ASK HELPERS
    # ==============================================================

    @staticmethod
    def calculate_spread_from_quote(
        bid: float,
        ask: float,
    ) -> float:
        """
        Calculate actual spread from broker bid/ask data.

        This allows the broker adapter to pass observed market
        information into the CostModel.

        Example:

            bid = 1.08550
            ask = 1.08570

            spread = 0.00020
        """

        if bid < 0 or ask < 0:
            raise ValueError("bid and ask must be >= 0.")

        if ask < bid:
            raise ValueError("ask cannot be lower than bid.")

        return float(ask - bid)

    # ==============================================================
    # SLIPPAGE
    # ==============================================================

    def calculate_slippage(
        self,
        size: float = 1.0,
        atr: Optional[float] = None,
    ) -> float:
        """
        Calculate configured execution slippage.

        V1 supports:

            fixed:
                slippage_value

            atr:
                ATR × slippage_value

        Order size is accepted so the public interface can remain
        compatible with future execution models.

        V1 does not invent volume-based market impact.
        """

        if size <= 0:
            raise ValueError("size must be > 0.")

        slippage_type = self.config["slippage_type"]
        slippage_value = float(self.config["slippage_value"])

        if slippage_type == "atr":

            if atr is None:
                raise ValueError("ATR is required when " "slippage_type='atr'.")

            if atr < 0:
                raise ValueError("atr must be >= 0.")

            return float(atr * slippage_value)

        return slippage_value

    # Backward-compatible private alias.
    def _calculate_slippage(
        self,
        direction: str,
        size: float = 1.0,
        atr: Optional[float] = None,
        candle_volume: Optional[float] = None,
    ) -> float:
        """
        Compatibility wrapper for older callers.

        V1 deliberately does not use candle volume for market impact.
        That belongs to a future execution model.
        """

        self._normalize_direction(direction)

        return self.calculate_slippage(
            size=size,
            atr=atr,
        )

    # ==============================================================
    # ENTRY PRICE
    # ==============================================================

    def get_entry_price(
        self,
        raw_price: float,
        direction: str,
        size: float = 1.0,
        atr: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> float:
        """
        Calculate simulated execution entry price.

        If broker bid/ask values are supplied, they take priority.

        LONG:

            broker ask
            + slippage

        SHORT:

            broker bid
            - slippage

        If bid/ask are unavailable, configured spread is used around
        raw_price.
        """

        if raw_price <= 0:
            raise ValueError("raw_price must be > 0.")

        normalized = self._normalize_direction(direction)

        slip = self.calculate_slippage(
            size=size,
            atr=atr,
        )

        # ----------------------------------------------------------
        # BROKER QUOTE PATH
        # ----------------------------------------------------------

        if bid is not None or ask is not None:

            if bid is None or ask is None:
                raise ValueError("Both bid and ask must be supplied together.")

            actual_spread = self.calculate_spread_from_quote(
                bid=bid,
                ask=ask,
            )

            # actual_spread is intentionally calculated here so the
            # broker quote is validated. The actual execution side
            # is then used directly.
            _ = actual_spread

            if normalized == "LONG":
                return float(ask + slip)

            return float(bid - slip)

        # ----------------------------------------------------------
        # CONFIGURED-SPREAD PATH
        # ----------------------------------------------------------

        spread = float(self.config["spread"])
        half_spread = spread / 2.0

        if normalized == "LONG":
            return float(raw_price + half_spread + slip)

        return float(raw_price - half_spread - slip)

    # ==============================================================
    # EXIT PRICE
    # ==============================================================

    def get_exit_price(
        self,
        raw_price: float,
        direction: str,
        size: float = 1.0,
        atr: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> float:
        """
        Calculate simulated execution exit price.

        LONG exit:

            sell at bid
            minus slippage

        SHORT exit:

            buy at ask
            plus slippage

        Broker bid/ask values take priority when supplied.
        """

        if raw_price <= 0:
            raise ValueError("raw_price must be > 0.")

        normalized = self._normalize_direction(direction)

        slip = self.calculate_slippage(
            size=size,
            atr=atr,
        )

        # ----------------------------------------------------------
        # BROKER QUOTE PATH
        # ----------------------------------------------------------

        if bid is not None or ask is not None:

            if bid is None or ask is None:
                raise ValueError("Both bid and ask must be supplied together.")

            self.calculate_spread_from_quote(
                bid=bid,
                ask=ask,
            )

            if normalized == "LONG":
                return float(bid - slip)

            return float(ask + slip)

        # ----------------------------------------------------------
        # CONFIGURED-SPREAD PATH
        # ----------------------------------------------------------

        spread = float(self.config["spread"])
        half_spread = spread / 2.0

        if normalized == "LONG":
            return float(raw_price - half_spread - slip)

        return float(raw_price + half_spread + slip)

    # ==============================================================
    # COMMISSION
    # ==============================================================

    def calculate_commission(
        self,
        size: float,
        price: float,
        is_maker: bool = False,
    ) -> float:
        """
        Calculate commission for one execution.

        Supported models:

            flat
            per_lot
            percentage
            maker_taker

        Commission is calculated independently from spread and
        slippage.
        """

        if size <= 0:
            raise ValueError("size must be > 0.")

        if price <= 0:
            raise ValueError("price must be > 0.")

        commission_type = self.config["commission_type"]

        contract_multiplier = float(self.config["contract_multiplier"])

        if commission_type in {
            "flat",
            "per_lot",
        }:
            return float(self.config["commission_value"] * size)

        if commission_type == "percentage":

            rate = float(self.config["commission_value"])

            return float(price * size * contract_multiplier * (rate / 100.0))

        if commission_type == "maker_taker":

            rate = self.config["maker_fee"] if is_maker else self.config["taker_fee"]

            return float(price * size * contract_multiplier * (rate / 100.0))

        raise ValueError(f"Unsupported commission type: " f"{commission_type}")

    # ==============================================================
    # SWAP
    # ==============================================================

    def calculate_swap(
        self,
        size: float,
        direction: str,
        holding_days: float,
    ) -> float:
        """
        Calculate financing/swap cost.

        The CostModel does not determine whether a broker charges
        swap or when settlement occurs. It simply applies the
        supplied configured rate.
        """

        if size <= 0:
            raise ValueError("size must be > 0.")

        if holding_days < 0:
            raise ValueError("holding_days must be >= 0.")

        normalized = self._normalize_direction(direction)

        if normalized == "LONG":
            rate = float(self.config["swap_rate_long"])
        else:
            rate = float(self.config["swap_rate_short"])

        return float(rate * size * holding_days)

    # ==============================================================
    # CURRENCY TRANSLATION
    # ==============================================================

    def translate_to_currency(
        self,
        price_difference: float,
        size: float,
    ) -> float:
        """
        Translate a price difference into account currency.

        Formula:

            price_difference
            / pip_scale
            × point_value
            × size
            × contract_multiplier

        This keeps price-distance units separate from monetary value.
        """

        if size <= 0:
            raise ValueError("size must be > 0.")

        point_value = float(self.config["point_value"])

        pip_scale = float(self.config["pip_scale"])

        contract_multiplier = float(self.config["contract_multiplier"])

        points = price_difference / pip_scale

        return float(points * point_value * size * contract_multiplier)

    # ==============================================================
    # ROUND-TRIP COST
    # ==============================================================

    def calculate_round_trip_cost(
        self,
        entry_raw_price: float,
        exit_raw_price: float,
        direction: str,
        size: float = 1.0,
        atr: Optional[float] = None,
        entry_bid: Optional[float] = None,
        entry_ask: Optional[float] = None,
        exit_bid: Optional[float] = None,
        exit_ask: Optional[float] = None,
        entry_is_maker: bool = False,
        exit_is_maker: bool = False,
        holding_days: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calculate a complete round-trip execution-cost breakdown.

        This method does NOT simulate a trade lifecycle.

        It simply answers:

            "If an entry and exit occurred at these prices,
             what would the execution and transaction costs be?"

        Returned fields include:

            entry_raw_price
            entry_execution_price
            exit_raw_price
            exit_execution_price
            entry_slippage
            exit_slippage
            entry_commission
            exit_commission
            total_commission
            swap
            gross_price_difference
            net_price_difference
            total_transaction_cost
        """

        normalized = self._normalize_direction(direction)

        # ----------------------------------------------------------
        # EXECUTION PRICES
        # ----------------------------------------------------------

        entry_price = self.get_entry_price(
            raw_price=entry_raw_price,
            direction=normalized,
            size=size,
            atr=atr,
            bid=entry_bid,
            ask=entry_ask,
        )

        exit_price = self.get_exit_price(
            raw_price=exit_raw_price,
            direction=normalized,
            size=size,
            atr=atr,
            bid=exit_bid,
            ask=exit_ask,
        )

        # ----------------------------------------------------------
        # SLIPPAGE
        # ----------------------------------------------------------

        slippage = self.calculate_slippage(
            size=size,
            atr=atr,
        )

        entry_slippage = slippage
        exit_slippage = slippage

        # ----------------------------------------------------------
        # COMMISSIONS
        # ----------------------------------------------------------

        entry_commission = self.calculate_commission(
            size=size,
            price=entry_price,
            is_maker=entry_is_maker,
        )

        exit_commission = self.calculate_commission(
            size=size,
            price=exit_price,
            is_maker=exit_is_maker,
        )

        total_commission = entry_commission + exit_commission

        # ----------------------------------------------------------
        # SWAP
        # ----------------------------------------------------------

        swap = self.calculate_swap(
            size=size,
            direction=normalized,
            holding_days=holding_days,
        )

        # ----------------------------------------------------------
        # GROSS PRICE DIFFERENCE
        # ----------------------------------------------------------

        if normalized == "LONG":

            gross_price_difference = exit_raw_price - entry_raw_price

            net_price_difference = exit_price - entry_price

        else:

            gross_price_difference = entry_raw_price - exit_raw_price

            net_price_difference = entry_price - exit_price

        # ----------------------------------------------------------
        # PRICE FRICTION
        # ----------------------------------------------------------

        spread_and_slippage_cost = abs(gross_price_difference - net_price_difference)

        total_transaction_cost = spread_and_slippage_cost + total_commission + swap

        # ----------------------------------------------------------
        # RETURN AUDITABLE BREAKDOWN
        # ----------------------------------------------------------

        return {
            "direction": normalized,
            "size": float(size),
            "entry_raw_price": float(entry_raw_price),
            "entry_execution_price": float(entry_price),
            "exit_raw_price": float(exit_raw_price),
            "exit_execution_price": float(exit_price),
            "entry_slippage": float(entry_slippage),
            "exit_slippage": float(exit_slippage),
            "entry_commission": float(entry_commission),
            "exit_commission": float(exit_commission),
            "total_commission": float(total_commission),
            "swap": float(swap),
            "gross_price_difference": float(gross_price_difference),
            "net_price_difference": float(net_price_difference),
            "spread_and_slippage_cost": float(spread_and_slippage_cost),
            "total_transaction_cost": float(total_transaction_cost),
        }
