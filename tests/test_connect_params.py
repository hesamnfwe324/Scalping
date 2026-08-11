"""Regression tests for mt5rest ConnectEx query parameters."""


def test_connect_ex_boolean_flags_are_query_string_values():
    from live_trading.mt5.connector import _connect_params

    params = _connect_params("123", "secret", "AMarkets-Demo")

    assert params["downloadOrderHistory"] == "true"
    assert params["reconnectOnSymbolUpdate"] == "true"
    assert all(not isinstance(params[name], bool) for name in (
        "downloadOrderHistory",
        "reconnectOnSymbolUpdate",
    ))