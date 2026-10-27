import datetime as dt

from pybvmac import storage
from pybvmac.ticker import Bond, Ticker


def _equity_record(date, ticker="SOCAP", price=50000.0):
    return {
        "date": date,
        "ticker": ticker,
        "name": "SOCAPALM",
        "compartment": None,
        "close_price": price,
        "change_pct": 0.0,
        "volume": 6,
        "value_fcfa": 300000.0,
        "is_trading_day": True,
        "source_bulletin": "BOC-1.pdf",
        "extraction_method": "text_parse",
        "confidence_score": 1.0,
    }


def _bond_record(date, ticker="ECMR6", price=100.0):
    return {
        "date": date,
        "ticker": ticker,
        "name": "ECMR 6.25% NET 2022-2029",
        "compartment": None,
        "close_price": price,
        "change_pct": 0.0,
        "volume": 0,
        "value_fcfa": 0.0,
        "is_trading_day": True,
        "source_bulletin": "BOC-1.pdf",
        "extraction_method": "text_parse",
        "confidence_score": 1.0,
    }


def test_ticker_history_resolves_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    storage.append([_equity_record(dt.date(2026, 9, 16))], kind="equities")

    df = Ticker("SOCAPALM").history()  # alias -> canonical Mnemo "SOCAP"
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "SOCAP"


def test_ticker_history_empty_cache_returns_empty_df(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    df = Ticker("SOCAPALM").history()
    assert df.empty


def test_bond_history_uses_mnemo_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    storage.append([_bond_record(dt.date(2026, 9, 16))], kind="bonds")

    df = Bond("ecmr6").history()  # case-insensitive, no alias resolution needed
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "ECMR6"


def test_bond_history_period_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    storage.append(
        [
            _bond_record(dt.date(2020, 1, 1)),
            _bond_record(dt.date(2026, 9, 16)),
        ],
        kind="bonds",
    )

    df = Bond("ECMR6").history(period="30d", end="2026-09-16")
    assert len(df) == 1
    assert df.index[0] == dt.date(2026, 9, 16)
