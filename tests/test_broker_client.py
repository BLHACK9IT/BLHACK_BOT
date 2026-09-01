from collections import namedtuple

import pytest

from src.broker import MT5ReadOnlyClient

AccountInfo = namedtuple(
    "AccountInfo",
    [
        "login",
        "trade_mode",
        "balance",
        "equity",
        "profit",
        "margin",
        "margin_free",
        "margin_level",
        "currency",
        "leverage",
        "server",
        "company",
        "trade_allowed",
    ],
)
TerminalInfo = namedtuple("TerminalInfo", ["connected", "trade_allowed"])


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, initialize_result=True, account=None):
        self.initialize_result = initialize_result
        self.account = account or AccountInfo(
            login=12345678,
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO,
            balance=10_000.0,
            equity=10_050.0,
            profit=50.0,
            margin=200.0,
            margin_free=9_850.0,
            margin_level=5_025.0,
            currency="USD",
            leverage=100,
            server="Broker-Demo",
            company="Example Broker",
            trade_allowed=False,
        )
        self.initialize_args = None
        self.initialize_kwargs = None
        self.shutdown_calls = 0

    def initialize(self, *args, **kwargs):
        self.initialize_args = args
        self.initialize_kwargs = kwargs
        return self.initialize_result

    def account_info(self):
        return self.account

    def terminal_info(self):
        return TerminalInfo(connected=True, trade_allowed=False)

    def last_error(self):
        return (-1, "test error")

    def shutdown(self):
        self.shutdown_calls += 1


def make_client(api, **overrides):
    values = {
        "login": 12345678,
        "password": "investor-password",
        "server": "Broker-Demo",
        "mt5_api": api,
    }
    values.update(overrides)
    return MT5ReadOnlyClient(**values)


def test_connect_passes_account_credentials_and_optional_terminal_path():
    api = FakeMT5()
    client = make_client(api, terminal_path="C:/MT5/terminal64.exe", timeout_ms=15_000)

    client.connect()

    assert api.initialize_args == ("C:/MT5/terminal64.exe",)
    assert api.initialize_kwargs == {
        "login": 12345678,
        "password": "investor-password",
        "server": "Broker-Demo",
        "timeout": 15_000,
    }


def test_get_account_details_returns_risk_fields_and_demo_type():
    client = make_client(FakeMT5())
    client.connect()

    details = client.get_account_details()

    assert details["balance"] == 10_000.0
    assert details["equity"] == 10_050.0
    assert details["used_margin"] == 200.0
    assert details["free_margin"] == 9_850.0
    assert details["account_type"] == "demo"
    assert details["is_virtual"] is True
    assert details["trade_allowed"] is False


def test_real_trade_mode_is_reported_as_real():
    api = FakeMT5()
    api.account = api.account._replace(trade_mode=api.ACCOUNT_TRADE_MODE_REAL)
    client = make_client(api)
    client.connect()

    details = client.get_account_details()

    assert details["account_type"] == "real"
    assert details["is_virtual"] is False


def test_client_exposes_no_order_send_method():
    client = make_client(FakeMT5())

    assert not hasattr(client, "order_send")


def test_account_reads_require_a_connection():
    client = make_client(FakeMT5())

    with pytest.raises(ConnectionError, match="Call connect"):
        client.get_account_details()


def test_initialize_failure_shuts_down_and_raises_last_error():
    api = FakeMT5(initialize_result=False)
    client = make_client(api)

    with pytest.raises(ConnectionError, match="test error"):
        client.connect()

    assert api.shutdown_calls == 1


def test_missing_account_info_fails_validation():
    api = FakeMT5()
    api.account = None
    client = make_client(api)
    client.connect()

    assert client.validate_connection() is False


def test_close_is_idempotent():
    api = FakeMT5()
    client = make_client(api)
    client.connect()

    client.close()
    client.close()

    assert api.shutdown_calls == 1
