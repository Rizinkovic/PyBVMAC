import datetime as dt

import pandas as pd
import pytest

from pybvmac import config, storage


def test_audit_reports_duplicate_keys_missing_prices_and_invalid_values(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE_FORMAT", "csv")
    storage.save_all(
        pd.DataFrame(
            [
                {
                    "date": dt.date(2026, 1, 2),
                    "ticker": "SOCAP",
                    "close_price": None,
                    "volume": 1,
                    "value_fcfa": 50000,
                    "source_bulletin": "BOC-20260102.pdf",
                },
                {
                    "date": dt.date(2026, 1, 2),
                    "ticker": "SOCAP",
                    "close_price": -1,
                    "volume": 1,
                    "value_fcfa": 50000,
                    "source_bulletin": "BOC-20260102.pdf",
                },
            ]
        ),
        "equities",
    )

    report = storage.audit("equities")["equities"]

    assert report["rows"] == 2
    assert report["duplicate_keys"] == 2
    assert report["missing_close_prices"] == 1
    assert report["invalid_numeric_values"] == 2
    assert report["unique_tickers"] == 1


def test_audit_empty_dataset_reports_zero_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE_FORMAT", "csv")

    report = storage.audit("all")

    assert set(report) == {"equities", "bonds", "market_cap", "index"}
    assert all(item["rows"] == 0 for item in report.values())


def test_audit_rejects_unknown_dataset_kind():
    with pytest.raises(ValueError, match="kind must be"):
        storage.audit("stocks")



def test_cli_audit_command_accepts_dataset_filter(monkeypatch, capsys):
    from pybvmac import cli

    monkeypatch.setattr(
        cli.storage,
        "audit",
        lambda kind: {"equities": {"rows": 7}, "requested_kind": kind},
    )

    cli.main(["audit", "--kind", "equities"])

    output = capsys.readouterr().out
    assert '"rows": 7' in output
    assert '"requested_kind": "equities"' in output
