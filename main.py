# main.py

from src import TradingBot
from src.config import ACTIVE_CATEGORIES, DATA_API_CREDENTIALS, MT5_CREDENTIALS
from src.data import MultiAssetDataFetcher


def main():
    configured = {
        key: bool(value)
        for key, value in MT5_CREDENTIALS.items()
        if key != "timeout_ms"
    }
    print("MT5 configuration present:", configured)

    fetcher = MultiAssetDataFetcher(DATA_API_CREDENTIALS)

    print(f"\nActive Categories: {ACTIVE_CATEGORIES}")
    print(f"Loaded Symbols: {list(fetcher.symbol_category_map.keys())}\n")

    # User input
    user_symbol = input("Enter symbol (e.g., EURUSD): ").strip()
    user_mode = input("Enter mode (scalping/day_trading/swing): ").strip()

    # Create bot (broker connection happens inside TradingBot)
    bot = None
    try:
        bot = TradingBot(symbol=user_symbol, mode=user_mode)
        bot.run_system_check()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if bot is not None:
            bot.close()


if __name__ == "__main__":
    main()
