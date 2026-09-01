import pytest

import src as bot_module


class FakeReadOnlyClient:
    created_with = None

    def __init__(self, **kwargs):
        type(self).created_with = kwargs
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def validate_connection(self):
        return self.connected

    def close(self):
        self.closed = True


def test_trading_bot_initializes_mt5_from_config(monkeypatch):
    credentials = {
        "login": "12345678",
        "password": "investor-password",
        "server": "Broker-Demo",
        "terminal_path": None,
        "timeout_ms": 60_000,
    }
    monkeypatch.setattr(bot_module, "MT5_CREDENTIALS", credentials)
    monkeypatch.setattr(bot_module, "MT5ReadOnlyClient", FakeReadOnlyClient)
    monkeypatch.setattr(bot_module, "ENABLE_BROKER_ACCOUNT_READ", True)
    trading_bot = bot_module.TradingBot.__new__(bot_module.TradingBot)

    broker = trading_bot._initialize_broker()

    assert FakeReadOnlyClient.created_with == credentials
    assert broker.connected is True


def test_trading_bot_reports_missing_mt5_settings(monkeypatch):
    monkeypatch.setattr(
        bot_module,
        "MT5_CREDENTIALS",
        {
            "login": None,
            "password": None,
            "server": None,
            "terminal_path": None,
            "timeout_ms": 60_000,
        },
    )
    trading_bot = bot_module.TradingBot.__new__(bot_module.TradingBot)

    with pytest.raises(RuntimeError, match="MT5_LOGIN, MT5_PASSWORD, MT5_SERVER"):
        trading_bot._initialize_broker()
