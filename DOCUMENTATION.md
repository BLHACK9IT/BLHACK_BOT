# Trading Bot Project Documentation

## The Trading Bot Execution Pipeline
                
[1. Account & Safety Check] 
         │
         ▼
[2. Trading Mode & Strategy Selector] (Scalping / Day Trading / Position Trading)
         │
         ▼
[3. Market Analysis & Setup Identification] (Tailored to the chosen mode)
         │
         ▼
[4. Risk & SL/TP Calculation] (Using our RiskManager & Lot-Step rules)
         │
         ▼
[5. Order Execution] (Sending market/limit orders via the correct API route)
## Overview
This is a multi-asset trading bot designed to trade Stocks (via Alpaca), Cryptocurrency, and Forex/Metals. 

## Project Structure
- `main.py`: The entry point and system check script to test the components.
- `src/config.py`: Centralized configuration holding API credentials, market categories, active categories, supported timeframes, and global risk defaults.
- `src/data_fetcher.py`: Contains the `MultiAssetDataFetcher` class that builds a symbol-to-category mapping and dynamically routes data fetching requests to the correct API based on the asset type.
- `src/risk_manager.py`: Contains the `RiskManager` class which handles position sizing calculations based on account balance, default risk percentage, stop loss distance, and pip value.
- `requirements.txt`: Project dependencies (`alpaca-py`, `pandas`, `requests`).
- `index.py` & `Pandas.py`: Scratchpad/learning files for Pandas experiments.

## Progress Log

### Initial Setup - 2026-08-25
- Created a Python virtual environment (`.venv`).
- Added initial project files: `index.py`, `Pandas.py`, and `requirements.txt`.
- Implemented `RiskManager` in `src/risk_manager.py` to calculate exact position sizes with lot stepping.
- Implemented `MultiAssetDataFetcher` in `src/data_fetcher.py` to route data fetching by market category.
- Created `src/config.py` to store API credentials and market configurations.
- Added `main.py` to run a system check across the data fetcher and risk manager components.
- Created this `DOCUMENTATION.md` file to track progress.

### Update - 2026-08-27
- Added `.env` file for environment variables and API key management.
- Added `.gitignore` to prevent tracking of unnecessary or sensitive files.
- Added `code_file.txt` containing the latest codebase snapshot.
- Removed experimental scratchpad files (`index.py` and `Pandas.py`).
- Outlined "Intensive Algorithm" in documentation focusing on a mathematical edge over market bias.

# Twelve Data websocket api 
wss://[ws.twelvedata.com/v1/quotes/price](https://ws.twelvedata.com/v1/quotes/price)
---

# Basic Simple Trading Logic Sample for only market analysis and entry 

1. The Higher Timeframe = The Compass (Directional Bias)
Your 1-hour, 4-hour, or daily charts act as your compass. They tell you which direction you are allowed to trade. If those higher charts are bearish, your rule is simple: "We only look for short/sell opportunities." This prevents your bot from fighting the main trend.

2. The 30-Second Window = The Trigger (Timing)
Because higher timeframes move slowly, entering a trade right when a 1-hour candle closes can sometimes mean you missed the move or got in at a bad price. This is where your 30-second live window shines:

It acts as your timing mechanism.

Instead of guessing, your bot waits for the micro-structure (the 30-second momentum) to align with the macro-trend (the 1h/4h or 5m/15m charts).

Once the 30-second window prints a sharp drop that matches the overall bearish bias, it pulls the trigger.

By combining a higher timeframe filter with a fast micro-trigger, you drastically cut down on false breakouts and trade alongside institutional momentum. You've got the exact right mindset for building this system!

# Stop Loss Calc
$$\text{EV} = (\text{Win Rate} \times \text{Avg Win}) - (\text{Loss Rate} \times \text{Avg Loss})$$

# Intensive Algorithm 
Math Edge over market bias and direction 


MARKET DATA
    ↓
FEATURE / SIGNAL ENGINE
    ↓
REGIME DETECTION
    ↓
TRADE SIGNAL
    ↓
EXECUTION MODEL
    ↓
RISK ENGINE  ←────────┐
    ↓                  │
ORDER                  │
    ↓                  │
POSITION MONITOR ──────┘
    ↓
PERFORMANCE / RESEARCH LOG


                    TWELVE DATA
                         │
                         ▼
                ┌─────────────────┐
                │ DATA ENGINE     │
                │                 │
                │ 1m              │
                │ 5m              │
                │ 15m             │
                │ 1h              │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ FEATURE ENGINE  │
                │                 │
                │ momentum        │
                │ volatility      │
                │ volume          │
                │ structure       │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ REGIME ENGINE   │
                │                 │
                │ 1H bias         │
                │ 15M regime      │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ SETUP ENGINE    │
                │                 │
                │ 5M setup        │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ ENTRY ENGINE    │
                │                 │
                │ 1M trigger      │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ EDGE ENGINE     │
                │                 │
                │ probability     │
                │ payoff          │
                │ costs           │
                │ EV              │
                └────────┬────────┘
                         │
                  EDGE SUFFICIENT?
                    /          \
                  NO            YES
                  │              │
                WAIT             ▼
                           ┌─────────────┐
                           │ RISK ENGINE │
                           └──────┬──────┘
                                  │
                                  ▼
                           ┌─────────────┐
                           │ PAPER      │
                           │ EXECUTION  │
                           └──────┬──────┘
                                  │
                                  ▼
                           ┌─────────────┐
                           │ POSITION    │
                           │ MANAGER     │
                           └──────┬──────┘
                                  │
                                  ▼
                           ┌─────────────┐
                           │ TRADE LOG   │
                           └─────────────┘

# Trading Mode:
- Scalping 
- Day Trading 
- Position Trading

# Multi-Timeframe Confluence



- Use a Cent Account: On a Cent Account, $10 displays as 1,000 cents. A $0.10 risk per trade is equal to 1% risk, allowing you to withstand losing streaks without blowing up.
- Session Filtering: Scalp ONLY during high-liquidity sessions (London/NY overlap: 13:00 to 16:00 UTC). Outside these hours, low volume causes wide spreads that destroy scalping setups.
- Fixed Daily Limit: Stop the bot if it loses 3 trades in a row in a single session to protect against strong trending market runs.


# Day Trading





# Position Trading

*Note: Whenever you say "update", this Progress Log will be updated with the latest changes made to the project.*

    