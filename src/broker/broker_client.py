"""Read-only MetaTrader 5 account client.

The adapter intentionally exposes account and terminal information only. Order
creation, modification, and cancellation are outside this client's contract.
"""

from __future__ import annotations

import importlib
import platform
from typing import Any, Dict, Optional


class MT5ReadOnlyClient:
    """Connect to an MT5 terminal and read the active account's state."""

    def __init__(
        self,
        login: int | str,
        password: str,
        server: str,
        terminal_path: Optional[str] = None,
        timeout_ms: int = 60_000,
        mt5_api: Any = None,
    ) -> None:
        if login in (None, ""):
            raise ValueError("MT5 login is required")
        if not password:
            raise ValueError("MT5 password is required")
        if not server:
            raise ValueError("MT5 server is required")

        try:
            self.login = int(login)
        except (TypeError, ValueError) as exc:
            raise ValueError("MT5 login must be an integer account number") from exc

        self.password = password
        self.server = server
        self.terminal_path = terminal_path or None
        self.timeout_ms = int(timeout_ms)
        self._mt5 = mt5_api
        self._connected = False
        self.account_details: Optional[Dict[str, Any]] = None

    def _load_api(self) -> Any:
        """Load MetaQuotes' official package only when a connection is attempted."""
        if self._mt5 is not None:
            return self._mt5

        try:
            self._mt5 = importlib.import_module("MetaTrader5")
        except ImportError as exc:
            system = platform.system()
            platform_note = (
                " The official MetaTrader5 package provides Windows wheels only; "
                "run this bot with the MT5 terminal on Windows (or with Windows "
                "Python inside a configured Wine environment)."
                if system != "Windows"
                else " Install it with: python -m pip install MetaTrader5"
            )
            raise RuntimeError(
                f"MetaTrader5 is not available on this {system} Python environment."
                f"{platform_note}"
            ) from exc

        return self._mt5

    def connect(self) -> None:
        """Initialize the terminal connection using the configured account."""
        if self._connected:
            return

        mt5 = self._load_api()
        kwargs = {
            "login": self.login,
            "password": self.password,
            "server": self.server,
            "timeout": self.timeout_ms,
        }

        if self.terminal_path:
            initialized = mt5.initialize(self.terminal_path, **kwargs)
        else:
            initialized = mt5.initialize(**kwargs)

        if not initialized:
            error = self._last_error()
            mt5.shutdown()
            raise ConnectionError(f"MT5 initialization failed: {error}")

        self._connected = True

    def _last_error(self) -> Any:
        try:
            return self._mt5.last_error()
        except Exception:
            return "unknown MT5 error"

    def _require_connection(self) -> Any:
        if not self._connected:
            raise ConnectionError("MT5 is not connected. Call connect() first.")
        return self._mt5

    def _account_type(self, trade_mode: Any) -> str:
        mt5 = self._mt5
        modes = {
            getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0): "demo",
            getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1): "contest",
            getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2): "real",
        }
        return modes.get(trade_mode, "unknown")

    def get_account_details(self) -> Dict[str, Any]:
        """Return the MT5 account fields used by risk management and diagnostics."""
        mt5 = self._require_connection()
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"MT5 account_info() failed: {self._last_error()}")

        trade_mode = getattr(account, "trade_mode", None)
        account_type = self._account_type(trade_mode)
        details = {
            "account_id": str(getattr(account, "login", self.login)),
            "login": int(getattr(account, "login", self.login)),
            "balance": float(getattr(account, "balance", 0.0)),
            "equity": float(getattr(account, "equity", 0.0)),
            "profit": float(getattr(account, "profit", 0.0)),
            "used_margin": float(getattr(account, "margin", 0.0)),
            "free_margin": float(getattr(account, "margin_free", 0.0)),
            "margin_level": float(getattr(account, "margin_level", 0.0)),
            "currency": str(getattr(account, "currency", "")),
            "leverage": int(getattr(account, "leverage", 0)),
            "server": str(getattr(account, "server", self.server)),
            "broker": str(getattr(account, "company", "")),
            "account_type": account_type,
            "is_virtual": account_type in {"demo", "contest"},
            "trade_allowed": bool(getattr(account, "trade_allowed", False)),
        }
        self.account_details = details
        return details

    def get_terminal_details(self) -> Dict[str, Any]:
        """Return diagnostic information about the connected MT5 terminal."""
        mt5 = self._require_connection()
        terminal = mt5.terminal_info()
        if terminal is None:
            raise RuntimeError(f"MT5 terminal_info() failed: {self._last_error()}")

        if hasattr(terminal, "_asdict"):
            return dict(terminal._asdict())
        return {
            name: getattr(terminal, name)
            for name in dir(terminal)
            if not name.startswith("_") and not callable(getattr(terminal, name))
        }

    def validate_connection(self) -> bool:
        """Return whether MT5 can provide account details for the configured login."""
        try:
            details = self.get_account_details()
        except (ConnectionError, RuntimeError, ValueError):
            return False
        return details["login"] == self.login and details["balance"] >= 0

    def close(self) -> None:
        """Release the MT5 terminal connection. Safe to call more than once."""
        if self._connected and self._mt5 is not None:
            self._mt5.shutdown()
        self._connected = False

    def __enter__(self) -> "MT5ReadOnlyClient":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


# Shorter public name for callers that do not need the implementation detail.
MT5Client = MT5ReadOnlyClient
