# src/__init__.py

import sys
import os
import pandas as pd
from src.config import (
    DATA_API_CREDENTIALS,
    DEFAULT_RISK_PCT,
    ACTIVE_CATEGORIES,
    ENABLE_LIVE_STREAM,
    ENABLE_BROKER_ACCOUNT_READ,
    MAX_OPEN_POSITIONS,
    MT5_CREDENTIALS,
)
from src.data import MultiAssetDataFetcher
from src.risk_manager.risk_manager import RiskManager
from src.broker import MT5ReadOnlyClient

# Reconfigure standard output to use UTF-8 encoding safely without detaching
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.makedirs("logs", exist_ok=True)


class TradingBot:
    def __init__(self, symbol: str, mode: str):
        """
        Initialize TradingBot with:
        1. Symbol and mode validation
        2. BROKER CONNECTION (reads real account balance)
        3. RiskManager initialized from broker
        4. Data fetcher setup
        """
        self.symbol = symbol.strip().upper()
        self.mode = mode.lower().strip()

        # 1. Resolve multi-timeframe hierarchy based on mode
        self.timeframes = self._resolve_timeframe_hierarchy(self.mode)

        # 2. CONNECT TO READ-ONLY BROKER ACCOUNT
        print("🔗 Connecting to MetaTrader 5 (account read-only)...")
        self.broker = self._initialize_broker()

        try:
            # 3. INITIALIZE DATA FETCHER
            self.fetcher = MultiAssetDataFetcher(DATA_API_CREDENTIALS)

            # 4. INITIALIZE RISK MANAGER FROM BROKER
            print("💼 Initializing RiskManager with the MT5 account balance...")
            self.risk_manager = self._initialize_risk_manager()
        except Exception:
            self.broker.close()
            raise

        print(
            f"\n✅ Bot Initialized | Asset: {self.symbol} | Mode: {self.mode.upper()}"
        )
        print(f"📊 Timeframe Hierarchy: {self.timeframes}")
        print(f"💰 Risk Per Trade: {DEFAULT_RISK_PCT}%")
        print(f"📍 Max Concurrent Positions: {MAX_OPEN_POSITIONS}\n")

    def _initialize_broker(self) -> MT5ReadOnlyClient:
        """
        Connect to MT5 using credentials from config.

        Returns
        -------
        MT5ReadOnlyClient
            Connected account-information client
        """
        try:
            missing = [
                name
                for name in ("login", "password", "server")
                if not MT5_CREDENTIALS.get(name)
            ]
            if missing:
                raise ValueError(
                    "Missing MT5 configuration: "
                    + ", ".join(f"MT5_{name.upper()}" for name in missing)
                )
            if not ENABLE_BROKER_ACCOUNT_READ:
                raise RuntimeError("Broker account reads are disabled in configuration")

            broker = MT5ReadOnlyClient(**MT5_CREDENTIALS)
            broker.connect()

            if not broker.validate_connection():
                broker.close()
                raise ConnectionError("Failed to validate the MT5 account connection")

            print("✓ Connected to MetaTrader 5 in account read-only mode")
            return broker

        except Exception as e:
            raise RuntimeError(f"Broker initialization failed: {str(e)}")

    def _initialize_risk_manager(self) -> RiskManager:
        """
        Create RiskManager using REAL account balance from broker.

        Returns
        -------
        RiskManager
            Initialized with real broker account balance (not default)
        """
        try:
            # Create RiskManager from broker (reads real balance)
            risk_manager = RiskManager.from_broker(
                broker_client=self.broker,
                default_risk_pct=DEFAULT_RISK_PCT,
                max_open_positions=MAX_OPEN_POSITIONS,
            )

            # Print account info without exposing the login or credentials.
            account_details = self.broker.get_account_details()
            print(
                f"✓ Account Balance: ${account_details['balance']:.2f} {account_details['currency']}"
            )
            print(f"✓ Account Type: {account_details['account_type'].title()}")

            return risk_manager

        except Exception as e:
            raise RuntimeError(f"RiskManager initialization failed: {str(e)}")

    def close(self) -> None:
        """Close external connections held by the bot."""
        if getattr(self, "broker", None) is not None:
            self.broker.close()

    def _resolve_timeframe_hierarchy(self, mode: str) -> dict:
        """Maps out the multi-timeframe architecture required for each specific trading style."""
        mapping = {
            "scalping": {
                "entry": "1min",
                "lookout": "5min",
                "trend": "15min",
                "bias": "1h",
            },
            "day_trading": {
                "entry": "5min",
                "lookout": "15min",
                "trend": "1h",
                "bias": "4h",
            },
            "swing": {"entry": "1h", "lookout": "4h", "trend": "1d", "bias": "1w"},
        }
        if mode not in mapping:
            raise ValueError(
                f"Invalid mode '{mode}'. Choose from: {list(mapping.keys())}"
            )
        return mapping[mode]

    def run_system_check(self):
        """Executes full diagnostic validation checks, multi-timeframe data fetches, and polling loops."""
        print("--- Starting Trading Bot System Check ---")

        pd.set_option("display.max_rows", 15)
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 1000)
        pd.set_option("display.colheader_justify", "right")

        print(f"Active Categories from Config: {ACTIVE_CATEGORIES}")
        print(
            f"Loaded Symbol Lookup Map: {list(self.fetcher.symbol_category_map.keys())}\n"
        )

        # Initial warm-up data fetch for system check inspection
        for role, tf in self.timeframes.items():
            try:
                df = self.fetcher.fetch_data(
                    symbol=self.symbol, timeframe=tf, outputsize=500
                )
            except Exception as e:
                print(f"\n==================================================")
                print(f" NETWORK ERROR | {self.symbol} [{role.upper()} - {tf}]")
                print(f"==================================================")
                print(f"Failed to fetch data: {e}")
                print(f"\n-> Skipping timeframe {tf} due to connection issue.")
                print("\n" + "=" * 50 + "\n")
                continue

            print(f"\n==================================================")
            print(f" PANDAS OUTPUT TABLE | {self.symbol} [{role.upper()} - {tf}]")
            print(f"==================================================")

            if df is not None and not df.empty:
                print(df.to_string())
                print(
                    f"\n-> Success! Pulled and printed {role} data ({tf}) for {self.symbol}."
                )
            else:
                print(
                    f"\n-> Warning: Dataframe for {self.symbol} [{role} - {tf}] came back empty."
                )
            print("\n" + "=" * 50 + "\n")

        # Risk Manager Test Execution
        stop_loss = 50.0
        pip_val = 1.0
        position_size = self.risk_manager.calculate_position_size(
            stop_loss_distance=stop_loss, pip_value=pip_val
        )

        print("--- Risk Management Test ---")
        account_stats = self.risk_manager.get_current_stats()
        print(f"Account Balance: ${account_stats['account_balance']:,.2f}")
        print(f"Risk Percentage: {account_stats['default_risk_pct']}%")
        print(f"Stop Loss Distance: {stop_loss} units")
        print(f"Calculated Position Size: {position_size} lots")
        print("--- System Check Complete ---\n")

        # Live Stream vs Polling Loop Execution
        if ENABLE_LIVE_STREAM:
            print("--- Initializing Live Stream Mode ---")
            streaming_symbols = [self.symbol]
            self.fetcher.start_live_stream(symbols=streaming_symbols)
        else:
            print(
                "--- Initializing Continuous Polling Engine using Multi-Timeframe stack ---"
            )
            print(
                "💡 Note: Terminal will display incoming candle updates and data content as the loop runs.\n"
            )

            self._run_terminal_printing_polling_loop(interval_seconds=5)

    def _run_terminal_printing_polling_loop(self, interval_seconds: int = 5):
        """Continuously runs the polling loop and prints incoming table data directly to the terminal."""
        import time
        from datetime import datetime, timezone

        try:
            while True:
                current_time = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
                print(
                    f"\n[{current_time}] 🔄 Running Polling Cycle for {self.symbol} across timeframes: {list(self.timeframes.values())}"
                )

                for role, tf in self.timeframes.items():
                    # This triggers the candle-synchronized fetch
                    df = self.fetcher.fetch_candle_synchronized_data(
                        symbol=self.symbol, timeframe=tf
                    )

                    if not df.empty:
                        print(f"\n┌──────────────────────────────────────────────────┐")
                        print(
                            f"│ NEW INCOMING DATA | {self.symbol} [{role.upper()} - {tf}]"
                            + " " * max(0, 18 - len(self.symbol) - len(role) - len(tf))
                            + "│"
                        )
                        print(f"└──────────────────────────────────────────────────┘")
                        print(df.to_string())
                        print("-" * 60)
                    else:
                        print(
                            f"   💤 [{role.upper()} - {tf}] No new candle closed yet. Holding state."
                        )

                print(
                    f"⏳ Sleeping for {interval_seconds} seconds before next check...\n"
                )
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print(
                "\n🛑 Polling loop manually stopped by user. Shutting down gracefully."
            )
