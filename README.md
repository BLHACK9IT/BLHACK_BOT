# BLHACK_BOT

Python trading-bot research project with multi-timeframe strategy analysis,
Twelve Data market history, and read-only MetaTrader 5 account information for
risk sizing.

## Current safety boundary

The MT5 integration can read account and terminal information only. The broker
client has no order placement, modification, or cancellation methods, and
`ENABLE_ORDER_EXECUTION` remains `False`. Use the MT5 investor/read-only
password whenever your broker provides one.

The account payload includes balance, equity, profit, margin, free margin,
currency, leverage, broker/server, and an account type derived from MT5's
`trade_mode` (`demo`, `contest`, or `real`). The risk manager uses the live
balance and defaults to 1% risk per trade.

## Unix development setup

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`, then run the test suite:

```bash
python -m pytest -q
```

The official `MetaTrader5` Python distribution provides Windows wheels only.
The conditional dependency in `requirements.txt` therefore leaves Unix
development and testing usable. For a live account connection, run the bot
with Windows Python on the same Windows environment as the MT5 terminal. A
Wine setup must likewise run both the terminal and Windows Python within the
configured Wine environment. See the official
[MT5 Python integration documentation](https://www.mql5.com/en/docs/python_metatrader5)
and [`initialize()` reference](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).

## Configuration

Copy `.env.example` to `.env`. Required values are:

- `TWELVE_DATA_API_KEY`
- `MT5_LOGIN`
- `MT5_PASSWORD` (prefer an investor/read-only password)
- `MT5_SERVER` (must exactly match the server name shown by MT5)

`MT5_TERMINAL_PATH` is optional when the package can locate the terminal.
`MT5_TIMEOUT_MS` defaults to 60,000 milliseconds.

Secrets, virtual environments, caches, logs, archives, and local scratch files
are excluded by `.gitignore`.

## Run

Start the MT5 terminal, confirm it is signed in, then run:

```bash
source venv/bin/activate
python main.py
```

The startup output reports only whether configuration values are present; it
does not print credentials or the MT5 login.
