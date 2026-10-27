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
    monkeypatch.setattr(pipeline.fetch, "discover_bulletins", lambda session, **kwargs: bulletins)
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

    count = pipeline.backfill(
        dates[0], dates[1], session=object(), state_path=tmp_path / "checkpoint.json"
    )

    assert count == 2
    assert len(writes) == 1
    assert writes[0][0] == "equities"
    assert len(writes[0][1]) == 2



def test_backfill_resumes_from_checkpoint_without_reprocessing(monkeypatch, tmp_path):
    day = dt.date(2025, 1, 2)
    bulletin = pipeline.fetch.BulletinRef(
        url="https://example.test/2025-01-02.pdf",
        filename="2025-01-02.pdf",
        date=day,
    )
    monkeypatch.setattr(pipeline.fetch, "discover_bulletins", lambda session, **kwargs: [bulletin])
    monkeypatch.setattr(
        pipeline.fetch, "download_bulletin", lambda session, item: tmp_path / item.filename
    )
    parse_calls = []

    def parse(path, bulletin_date):
        parse_calls.append(path)
        return pipeline.BulletinRecords(
            equities=[{
                "date": bulletin_date,
                "ticker": "SOC",
                "close_price": 100.0,
                "is_trading_day": True,
                "source_bulletin": "2025-01-02.pdf",
            }],
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
    state_path = tmp_path / "checkpoint.json"

    assert pipeline.backfill(day, day, session=object(), state_path=state_path) == 1
    assert state_path.exists()
    assert pipeline.backfill(day, day, session=object(), state_path=state_path) == 0
    assert len(parse_calls) == 1
    assert len(writes) == 1
