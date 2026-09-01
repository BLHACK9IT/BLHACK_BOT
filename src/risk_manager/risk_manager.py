# src/risk_manager.py

import math
from typing import Optional, Dict


class RiskManager:
    """
    Position sizing and risk management using REAL broker account details.

    Instead of using DEFAULT_ACCOUNT_BALANCE from config, this reads actual
    account balance from the configured broker account client.
    """

    def __init__(
        self,
        account_balance: float,
        default_risk_pct: float = 1.0,
        broker_account_details: Optional[Dict] = None,
        max_open_positions: int = 3,
    ):
        """
        Initialize RiskManager with account balance and risk settings.

        Parameters
        ----------
        account_balance : float
            Current account balance (can come from broker or default)
        default_risk_pct : float, optional
            Default risk per trade as percentage (default: 1.0 = 1%)
        broker_account_details : dict, optional
            Full account details from broker:
            {
                "balance": float,
                "currency": str,
                "equity": float,
                "used_margin": float,
                "free_margin": float,
                "account_type": str,
                "is_virtual": bool,
            }
        max_open_positions : int, optional
            Maximum number of open positions allowed (default: 3)
        """
        self.account_balance = account_balance
        self.default_risk_pct = default_risk_pct
        self.broker_details = broker_account_details or {}
        self.max_open_positions = max_open_positions

        # Track current open positions
        self.open_positions_count = 0

    @classmethod
    def from_broker(
        cls,
        broker_client,
        default_risk_pct: float = 1.0,
        max_open_positions: int = 3,
    ):
        """
        Factory method: create RiskManager from live broker connection.

        This reads REAL account balance from broker instead of using defaults.

        Parameters
        ----------
        broker_client : object
            Connected broker client implementing ``get_account_details``
        default_risk_pct : float
            Default risk percentage per trade
        max_open_positions : int
            Max concurrent positions

        Returns
        -------
        RiskManager
            Initialized with real broker account details

        Example
        -------
        from src.broker import MT5ReadOnlyClient
        from src.risk_manager import RiskManager

        # Get real account details from broker
        mt5 = MT5ReadOnlyClient(login=123456, password="...", server="...")
        mt5.connect()
        risk_mgr = RiskManager.from_broker(mt5)

        # Now risk_mgr uses REAL balance, not default
        """
        try:
            # Fetch real account details from broker
            account_details = broker_client.get_account_details()
            balance = account_details.get("balance", 0)

            if balance <= 0:
                raise ValueError(f"Invalid account balance from broker: {balance}")

            # Create instance with real broker details
            return cls(
                account_balance=balance,
                default_risk_pct=default_risk_pct,
                broker_account_details=account_details,
                max_open_positions=max_open_positions,
            )

        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize RiskManager from broker: {str(e)}"
            )

    def calculate_position_size(
        self,
        stop_loss_distance: float,
        pip_value: float,
        risk_pct: Optional[float] = None,
        lot_step: float = 0.01,
    ) -> float:
        """
        Calculate position size based on risk formula.

        Formula:
            Position Size = (Account Balance × Risk %) / (Stop Loss Distance × Pip Value)

        Then rounds down to nearest lot_step to avoid over-risking.

        Parameters
        ----------
        stop_loss_distance : float
            Distance from entry to stop loss (in pips)
        pip_value : float
            Value per pip (instrument-specific, e.g., 10 for EURUSD with standard lots)
        risk_pct : float, optional
            Risk percentage (overrides default if provided)
        lot_step : float, optional
            Broker's minimum lot increment (default: 0.01 for micro lots)

        Returns
        -------
        float
            Position size in lots, rounded down to lot_step

        Raises
        ------
        ValueError
            If stop_loss_distance or pip_value is zero

        Example
        -------
        risk_mgr = RiskManager.from_broker(mt5_client)

        # Calculate position size for EURUSD trade
        position_size = risk_mgr.calculate_position_size(
            stop_loss_distance=25,   # 25 pips
            pip_value=10,            # Standard lot
            risk_pct=1.0,            # 1% of account
        )
        """
        # Use provided risk or default
        risk = risk_pct if risk_pct is not None else self.default_risk_pct
        risk_decimal = risk / 100.0

        # Calculate dollar amount to risk on this trade
        dollar_risk = self.account_balance * risk_decimal

        # Calculate risk per unit of position
        risk_per_unit = stop_loss_distance * pip_value

        if risk_per_unit == 0:
            raise ValueError(
                "Risk per unit cannot be zero. "
                "Check your stop loss distance or pip value."
            )

        # Raw position size (before rounding)
        raw_position_size = dollar_risk / risk_per_unit

        # Round DOWN to nearest lot_step
        # This ensures we never risk more than calculated
        precision = round(-math.log10(lot_step))
        position_size = math.floor(raw_position_size / lot_step) * lot_step

        return round(position_size, precision)

    def validate_position(
        self,
        position_size: float,
        symbol: str = "EURUSD",
    ) -> tuple:
        """
        Validate if a position can be opened given current risk constraints.

        Checks:
        - Not exceeding max open positions
        - Sufficient free margin (if broker tracks it)
        - Position size is positive

        Parameters
        ----------
        position_size : float
            Position size in lots
        symbol : str
            Trading symbol (for reference)

        Returns
        -------
        tuple
            (is_valid: bool, message: str)

        Example
        -------
        valid, msg = risk_mgr.validate_position(0.5, "EURUSD")
        if valid:
            print("Position approved")
        else:
            print(f"Position rejected: {msg}")
        """
        # Check position count
        if self.open_positions_count >= self.max_open_positions:
            return (False, f"Max open positions ({self.max_open_positions}) reached")

        # Check position size
        if position_size <= 0:
            return False, "Position size must be positive"

        # Check free margin if broker details are available
        if self.broker_details:
            free_margin = self.broker_details.get("free_margin", None)
            if free_margin is not None and free_margin <= 0:
                return False, "Insufficient free margin"

        return True, "Position approved"

    def log_position_opened(self, position_id: str, symbol: str, size: float):
        """
        Log that a position was opened.
        Updates internal position counter.

        Parameters
        ----------
        position_id : str
            Unique position identifier
        symbol : str
            Trading symbol
        size : float
            Position size
        """
        self.open_positions_count += 1
        print(
            f"[POSITION OPENED] ID: {position_id}, "
            f"Symbol: {symbol}, Size: {size} lots, "
            f"Total Open: {self.open_positions_count}"
        )

    def log_position_closed(self, position_id: str, pnl: float):
        """
        Log that a position was closed.
        Updates internal position counter and account balance.

        Parameters
        ----------
        position_id : str
            Unique position identifier
        pnl : float
            Profit/loss from the position
        """
        self.open_positions_count = max(0, self.open_positions_count - 1)
        self.account_balance += pnl
        print(
            f"[POSITION CLOSED] ID: {position_id}, "
            f"P&L: ${pnl:+.2f}, "
            f"New Balance: ${self.account_balance:.2f}, "
            f"Total Open: {self.open_positions_count}"
        )

    def get_current_stats(self) -> Dict:
        """
        Get current risk management statistics.

        Returns
        -------
        dict
            Current stats including balance, open positions, margin usage
        """
        return {
            "account_balance": self.account_balance,
            "default_risk_pct": self.default_risk_pct,
            "open_positions": self.open_positions_count,
            "max_positions": self.max_open_positions,
            "is_paper_trading": self.broker_details.get("is_virtual", False),
            "account_currency": self.broker_details.get("currency", "USD"),
        }

    def __repr__(self) -> str:
        return (
            f"RiskManager("
            f"balance=${self.account_balance:.2f}, "
            f"risk_pct={self.default_risk_pct}%, "
            f"open_positions={self.open_positions_count}/{self.max_open_positions})"
        )
