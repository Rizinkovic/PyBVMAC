from __future__ import annotations

import datetime as dt
from pathlib import Path

from pybvmac import pipeline


def test_backfill_batches_storage_writes(monkeypatch, tmp_path):
    dates = [dt.date(2025, 1, 2), dt.date(2025, 1, 3)]
    bulletins = [
        pipeline.fetch.BulletinRef(
            url=f"https://example.test/{day.isoformat()}.pdf",
            filename=f"{day.isoformat()}.pdf",
            date=day,
        )
        for day in dates
    ]
    monkeypatch.setattr(pipeline.fetch, "discover_bulletins", lambda session: bulletins)
    monkeypatch.setattr(
        pipeline.fetch,
        "download_bulletin",
        lambda session, bulletin: tmp_path / bulletin.filename,
    )

    def parse(_path: Path, bulletin_date: dt.date):
        return pipeline.BulletinRecords(
            equities=[
                {
                    "date": bulletin_date,
                    "ticker": "SOC",
                    "name": "Example issuer",
                    "close_price": 100.0,
                    "is_trading_day": True,
                    "source_bulletin": f"{bulletin_date.isoformat()}.pdf",
                }
            ],
            bonds=[],
            market_cap=None,
            index=None,
        )

    monkeypatch.setattr(pipeline, "process_bulletin_file", parse)
    writes = []
    monkeypatch.setattr(
        pipeline.storage,
        "append",
        lambda records, kind="equities": writes.append((kind, list(records))),
    )
    monkeypatch.setattr(pipeline.storage, "flag_for_review", lambda records: None)

    count = pipeline.backfill(dates[0], dates[1], session=object())

    assert count == 2
    assert len(writes) == 1
    assert writes[0][0] == "equities"
    assert len(writes[0][1]) == 2
