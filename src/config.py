# src/config.py

"""
Central configuration for the TradingBot.

Responsibilities:
    - Load environment variables from .env
    - Store external API credentials
    - Define market categories and symbols
    - Define supported timeframes
    - Define global risk defaults
    - Define broker/data-provider integration settings

IMPORTANT:
    The MT5 account type is read from the connected terminal. Configuration
    never assumes that an account is demo or real.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# ============================================================
# ENVIRONMENT
# ============================================================

# Load values from the project's .env file.
load_dotenv()


# ============================================================
# DATA PROVIDER
# ============================================================

DATA_API_CREDENTIALS = {
    "twelve_data": {
        "api_key": os.getenv("TWELVE_DATA_API_KEY"),
    }
}


# ============================================================
# BROKER
# ============================================================

MT5_CREDENTIALS = {
    "login": os.getenv("MT5_LOGIN"),
    "password": os.getenv("MT5_PASSWORD"),
    "server": os.getenv("MT5_SERVER"),
    "terminal_path": os.getenv("MT5_TERMINAL_PATH") or None,
    "timeout_ms": int(os.getenv("MT5_TIMEOUT_MS", "60000")),
}


# ============================================================
# LIVE STREAM
# ============================================================

ENABLE_LIVE_STREAM = os.getenv("ENABLE_LIVE_STREAM", "False").strip().lower() in (
    "true",
    "1",
    "t",
    "yes",
)


# ============================================================
# MARKET DATA SOURCE
# ============================================================

# Twelve Data remains our market-data provider for now.
#
# MT5 is used only for broker account information at this stage.
MARKET_DATA_PROVIDER = "twelve_data"

# Broker used for read-only account information.
BROKER_PROVIDER = "mt5"


# ============================================================
# MARKET CATEGORIES
# ============================================================

MARKET_CATEGORIES = {
    "stocks": {
        "description": "US Equities",
        "symbols": [
            "AAPL",
            "MSFT",
            "TSLA",
        ],
        "active_session": "9:30-16:00 EST",
    },
    "metals": {
        "description": "Precious Metals",
        "symbols": [
            "XAUUSD",
            "XAGUSD",
        ],
        "active_session": "24/5",
    },
    "forex": {
        "description": "Foreign Exchange Currency Pairs",
        "symbols": [
            "EURUSD",
            "GBPUSD",
            "USDJPY",
        ],
        "active_session": "24/5",
    },
    "crypto": {
        "description": "Cryptocurrency Pairs",
        "symbols": [
            "BTC/USDT",
            "ETH/USDT",
        ],
        "active_session": "24/7",
    },
    "indices": {
        "description": "Global Market Indices",
        "symbols": [
            "SPX",
            "NDX",
            "DJI",
            "DAX",
        ],
        "active_session": "Market Dependent",
    },
}


# ============================================================
# ACTIVE MARKET CATEGORIES
# ============================================================

# Categories currently enabled for this bot session.
ACTIVE_CATEGORIES = [
    "metals",
    "forex",
    "indices",
]


# ============================================================
# SUPPORTED TIMEFRAMES
# ============================================================

TIMEFRAMES = [
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
]


# ============================================================
# GLOBAL RISK DEFAULTS
# ============================================================

# IMPORTANT:
# This is only a fallback/default configuration.
#
# RiskManager obtains the actual account balance from MT5 when broker account
# reads are enabled. This value remains an explicit offline fallback only.

DEFAULT_ACCOUNT_BALANCE = 10000.0

# Maximum percentage of account equity allowed to be risked
# on a single trade.
DEFAULT_RISK_PCT = 1.0

# Maximum number of simultaneously open positions.
MAX_OPEN_POSITIONS = 3


# ============================================================
# BROKER INTEGRATION SAFETY
# ============================================================

# Trading is intentionally disabled at this stage.
#
# We are currently integrating and validating the broker
# connection/account layer before allowing order placement.
ENABLE_ORDER_EXECUTION = False

# Account information may be read when broker integration is
# enabled, but this does NOT authorize order placement.
ENABLE_BROKER_ACCOUNT_READ = True
