import pytest

from pybvmac.exceptions import UnknownTickerError
from pybvmac.ticker_map import all_tickers, resolve


def test_resolve_known_ticker():
    assert resolve("SOCAP") == "SOCAP"


def test_resolve_alias_to_canonical_mnemo():
    assert resolve("SOCAPALM") == "SOCAP"


def test_resolve_case_and_accent_insensitive():
    assert resolve("socapalm") == "SOCAP"


def test_resolve_unknown_raises():
    with pytest.raises(UnknownTickerError):
        resolve("NOT-A-REAL-TICKER")


def test_all_tickers_has_expected_columns():
    df = all_tickers()
    assert {"ticker", "name", "compartment", "asset_class"}.issubset(df.columns)
    assert "SOCAP" in df["ticker"].values
