import datetime as dt

from pybvmac import storage


def _record(date, ticker, price, source="BOC-1.pdf"):
    return {
        "date": date,
        "ticker": ticker,
        "name": ticker,
        "compartment": None,
        "close_price": price,
        "change_pct": 0.0,
        "volume": 100,
        "value_fcfa": 1000.0,
        "is_trading_day": True,
        "source_bulletin": source,
        "extraction_method": "text_parse",
        "confidence_score": 1.0,
    }


def test_append_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    records = [_record(dt.date(2026, 9, 17), "SOCAPALM", 29500.0)]
    storage.append(records, kind="equities")

    df = storage.load("equities")
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "SOCAPALM"


def test_append_deduplicates_on_natural_key(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    date = dt.date(2026, 9, 17)
    storage.append([_record(date, "SOCAPALM", 29500.0)], kind="equities")
    storage.append([_record(date, "SOCAPALM", 29999.0)], kind="equities")  # corrected re-parse

    df = storage.load("equities")
    assert len(df) == 1
    assert df.iloc[0]["close_price"] == 29999.0


def test_index_and_market_cap_kinds_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")

    date = dt.date(2026, 9, 16)
    storage.append(
        [{"date": date, "index_value": 1162.39, "change_pct": 0.0, "source_bulletin": "BOC-1.pdf"}],
        kind="index",
    )
    storage.append(
        [{"date": date, "market_cap_fcfa": 1851577990435.0, "source_bulletin": "BOC-1.pdf"}],
        kind="market_cap",
    )

    index_df = storage.load("index")
    cap_df = storage.load("market_cap")
    assert len(index_df) == 1 and index_df.iloc[0]["index_value"] == 1162.39
    assert len(cap_df) == 1 and cap_df.iloc[0]["market_cap_fcfa"] == 1851577990435.0
