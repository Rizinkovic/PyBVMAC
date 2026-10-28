import datetime as dt

import pybvmac
from pybvmac import api, pipeline


def test_module_exposes_backfill():
    # Regression: backfill() existed in pipeline.py but was never wired
    # into api.py / __init__.py, so pybvmac.backfill raised AttributeError.
    assert hasattr(pybvmac, "backfill")
    assert callable(pybvmac.backfill)


def test_backfill_parses_dates_and_delegates(monkeypatch):
    captured = {}

    def fake_backfill(start, end=None, session=None, **kwargs):
        captured["start"] = start
        captured["end"] = end
        return 3

    monkeypatch.setattr(pipeline, "backfill", fake_backfill)

    result = api.backfill(start="2026-01-01", end="2026-01-31")

    assert result == 3
    assert captured["start"] == dt.date(2026, 1, 1)
    assert captured["end"] == dt.date(2026, 1, 31)


def test_backfill_end_defaults_to_none(monkeypatch):
    captured = {}

    def fake_backfill(start, end=None, session=None):
        captured["end"] = end
        return 0

    monkeypatch.setattr(pipeline, "backfill", fake_backfill)
    api.backfill(start="2026-01-01")
    assert captured["end"] is None


def test_download_accepts_bare_string(tmp_path, monkeypatch):
    from pybvmac import storage

    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage.config, "STORAGE_FORMAT", "csv")
    storage.append(
        [
            {
                "date": dt.date(2026, 1, 2),
                "ticker": "SOCAP",
                "name": "SOCAPALM",
                "compartment": None,
                "close_price": 50000.0,
                "change_pct": 0.0,
                "volume": 1,
                "value_fcfa": 50000.0,
                "is_trading_day": True,
                "source_bulletin": "x.pdf",
                "extraction_method": "text_parse",
                "confidence_score": 1.0,
            }
        ],
        kind="equities",
    )

    # Regression: a bare string used to be iterated character-by-character.
    df = api.download("SOCAPALM", start="2026-01-01")
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "SOCAP"
