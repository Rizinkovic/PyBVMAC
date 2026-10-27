"""Orchestrates the five-stage pipeline described in section 9.

fetch -> classify -> parse or OCR -> normalize/validate -> store
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import NamedTuple, Optional

import pdfplumber

from . import config, fetch, storage
from .classify import has_text_layer
from .exceptions import FetchError, OCRNotAvailableError, ParseError
from .http_client import PoliteSession
from .ocr import parse_scanned_bulletin
from .parse import parse_bulletin_pdf
from .real_layout import parse_bulletin as parse_bulletin_real_layout

logger = logging.getLogger("pybvmac")


class BulletinRecords(NamedTuple):
    equities: list[dict]
    bonds: list[dict]
    market_cap: Optional[dict]
    index: Optional[dict]


def _validate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Data-quality gate: separate plausible records from ones that need a
    human to look at them, per NFR "Data quality" and FR-16.
    """
    good, review = [], []
    for record in records:
        price = record.get("close_price")
        is_trading_day = record.get("is_trading_day", True)
        confidence = record.get("confidence_score", 1.0)

        plausible_price = price is None or 0 < price < 10_000_000
        low_confidence = record.get("extraction_method") == "ocr" and (
            confidence < config.OCR_CONFIDENCE_THRESHOLD
        )

        if is_trading_day and (not plausible_price or low_confidence):
            review.append(record)
        else:
            good.append(record)
    return good, review


def process_bulletin_file(pdf_path: Path, bulletin_date: dt.date) -> BulletinRecords:
    """Run stages 2-4 on an already-downloaded bulletin PDF.

    Tries the real BVMAC export layout first (real_layout.py, calibrated
    against a genuine bulletin — see its module docstring), since it reads
    equities, bonds, and the market-cap total in one pass and is the most
    accurate for actual BOC bulletins. Falls back to the generic
    alias-based table parser (parse.py) — or OCR for scanned bulletins —
    when that layout isn't recognized, e.g. for older/different bulletin
    templates.
    """
    source_bulletin = Path(pdf_path).name
    try:
        if has_text_layer(str(pdf_path)):
            with pdfplumber.open(str(pdf_path)) as pdf:
                equities, bonds, market_cap, index = parse_bulletin_real_layout(
                    pdf, bulletin_date, source_bulletin
                )
            if not equities and not bonds:
                equities = parse_bulletin_pdf(str(pdf_path), bulletin_date, source_bulletin)
        else:
            equities = parse_scanned_bulletin(str(pdf_path), bulletin_date, source_bulletin)
            bonds, market_cap, index = [], None, None
    except OCRNotAvailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Failed to parse {source_bulletin}: {exc}") from exc

    if not equities and not bonds:
        logger.warning("No records extracted from %s", source_bulletin)
    return BulletinRecords(equities=equities, bonds=bonds, market_cap=market_cap, index=index)


def _store(records: BulletinRecords) -> None:
    good, review = _validate(records.equities)
    if good:
        storage.append(good, kind="equities")
    if review:
        storage.flag_for_review(review)
        logger.warning("%d equity record(s) flagged for manual review", len(review))

    if records.bonds:
        good_bonds, review_bonds = _validate(records.bonds)
        if good_bonds:
            storage.append(good_bonds, kind="bonds")
        if review_bonds:
            storage.flag_for_review(review_bonds)
            logger.warning("%d bond record(s) flagged for manual review", len(review_bonds))

    if records.market_cap:
        storage.append([records.market_cap], kind="market_cap")

    if records.index:
        storage.append([records.index], kind="index")


def refresh(session: Optional[PoliteSession] = None) -> BulletinRecords:
    """FR-01: fetch and store today's bulletin. Returns the parsed records."""
    session = session or PoliteSession()
    path, bulletin = fetch.fetch_today_bulletin(session)
    records = process_bulletin_file(path, bulletin.date)
    _store(records)
    return records


def backfill(
    start: dt.date,
    end: Optional[dt.date] = None,
    session: Optional[PoliteSession] = None,
) -> int:
    """FR-02: discover and process all bulletins in [start, end].

    Returns the number of bulletins successfully processed. Failures on
    individual bulletins are logged and skipped rather than aborting the
    whole backfill (an incomplete archive is expected, per section 16.1).
    """
    session = session or PoliteSession()
    end = end or dt.date.today()

    try:
        bulletins = fetch.discover_bulletins(session)
    except FetchError as exc:
        logger.error("Could not enumerate the BVMAC archive: %s", exc)
        return 0

    in_range = [b for b in bulletins if start <= b.date <= end]
    processed = 0
    for bulletin in in_range:
        try:
            path = fetch.download_bulletin(session, bulletin)
            records = process_bulletin_file(path, bulletin.date)
            _store(records)
            if records.equities or records.bonds:
                processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Skipping %s: %s", bulletin.filename, exc)
            continue

    logger.info("Backfill complete: %d/%d bulletins processed", processed, len(in_range))
    return processed
