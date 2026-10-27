"""Orchestrates the five-stage pipeline described in section 9.

fetch -> classify -> parse or OCR -> normalize/validate -> store
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
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
_CHECKPOINT_EVERY = 25


class BulletinRecords(NamedTuple):
    equities: list[dict]
    bonds: list[dict]
    market_cap: Optional[dict]
    index: Optional[dict]


def _validate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate plausible records from those needing human review."""
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
    """Parse an already-downloaded bulletin PDF."""
    source_bulletin = Path(pdf_path).name
    try:
        if has_text_layer(str(pdf_path)):
            with pdfplumber.open(str(pdf_path)) as pdf:
                equities, bonds, market_cap, index = parse_bulletin_real_layout(
                    pdf, bulletin_date, source_bulletin
                )
            if not equities:
                equities = parse_bulletin_pdf(
                    str(pdf_path), bulletin_date, source_bulletin
                )
        else:
            equities = parse_scanned_bulletin(
                str(pdf_path), bulletin_date, source_bulletin
            )
            bonds, market_cap, index = [], None, None
    except OCRNotAvailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Failed to parse {source_bulletin}: {exc}") from exc

    if not equities and not bonds and not market_cap and not index:
        logger.warning("No records extracted from %s", source_bulletin)
    return BulletinRecords(equities, bonds, market_cap, index)


def _store(records: BulletinRecords) -> None:
    for kind, items in (
        ("equities", records.equities),
        ("bonds", records.bonds),
        ("market_cap", [records.market_cap] if records.market_cap else []),
        ("index", [records.index] if records.index else []),
    ):
        good, review = _validate(items)
        if good:
            storage.append(good, kind=kind)
        if review:
            storage.flag_for_review(review)
            logger.warning("%d %s record(s) flagged for manual review", len(review), kind)


def refresh(session: Optional[PoliteSession] = None) -> BulletinRecords:
    """Fetch and store today's bulletin."""
    session = session or PoliteSession()
    started = time.perf_counter()
    path, bulletin = fetch.fetch_today_bulletin(session)
    download_seconds = time.perf_counter() - started
    parse_started = time.perf_counter()
    records = process_bulletin_file(path, bulletin.date)
    parse_seconds = time.perf_counter() - parse_started
    store_started = time.perf_counter()
    _store(records)
    store_seconds = time.perf_counter() - store_started
    logger.info(
        "Refresh timings for %s: download/cache %.2fs, parse %.2fs, store %.2fs",
        bulletin.filename, download_seconds, parse_seconds, store_seconds,
    )
    return records


def _manifest_path(start: dt.date, end: dt.date) -> Path:
    """Use a range-specific checkpoint so unrelated backfills never collide."""
    return config.CACHE_DIR / f"backfill-{start.isoformat()}-{end.isoformat()}.json"


def _read_manifest(path: Path, resume: bool) -> set[str]:
    if not resume or not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            logger.warning("Ignoring unsupported backfill checkpoint: %s", path)
            return set()
        completed = payload.get("completed", [])
        if not isinstance(completed, list) or not all(
            isinstance(name, str) for name in completed
        ):
            logger.warning("Ignoring malformed backfill checkpoint: %s", path)
            return set()
        return set(completed)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read checkpoint %s; restarting range: %s", path, exc)
        return set()


def _write_manifest(path: Path, completed: set[str]) -> None:
    """Atomically persist the successful bulletin names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(
                {"schema_version": 1, "completed": sorted(completed)},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def backfill(
    start: dt.date,
    end: Optional[dt.date] = None,
    session: Optional[PoliteSession] = None,
    *,
    resume: bool = True,
    checkpoint_every: int = _CHECKPOINT_EVERY,
    state_path: Optional[Path] = None,
) -> int:
    """Discover and process bulletins in [start, end], checkpointing progress.

    Successful batches are stored before their bulletin names are checkpointed.
    If interrupted between those operations, replay is safe because storage
    de-duplicates by bulletin identity. Failed/empty bulletins are retried on
    the next run. Returns successful bulletins processed in this invocation.
    """
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be at least 1")
    session = session or PoliteSession()
    end = end or dt.date.today()

    discovery_started = time.perf_counter()
    try:
        bulletins = fetch.discover_bulletins(session)
    except FetchError as exc:
        logger.error("Could not enumerate the BVMAC archive: %s", exc)
        return 0
    discovery_seconds = time.perf_counter() - discovery_started
    in_range = [b for b in bulletins if b.date and start <= b.date <= end]
    manifest = Path(state_path) if state_path else _manifest_path(start, end)
    completed = _read_manifest(manifest, resume)
    todo = [b for b in in_range if b.filename not in completed]
    logger.info(
        "Archive discovery: %.2fs; %d bulletins in range, %d already checkpointed, "
        "%d to process",
        discovery_seconds, len(in_range), len(in_range) - len(todo), len(todo),
    )

    pending: dict[str, list[dict]] = {
        "equities": [], "bonds": [], "market_cap": [], "index": []
    }
    pending_review: list[dict] = []
    pending_names: set[str] = set()
    processed_this_run = 0
    timings = {"download_cache": 0.0, "parse": 0.0, "storage": 0.0}
    failures = 0

    def checkpoint() -> None:
        if not pending_names:
            return
        store_started = time.perf_counter()
        for kind, items in pending.items():
            if items:
                storage.append(items, kind=kind)
        if pending_review:
            storage.flag_for_review(pending_review)
        timings["storage"] += time.perf_counter() - store_started
        # Persist completion only after records are safely stored. Replaying
        # after a crash before this write is safe because storage append is idempotent.
        completed.update(pending_names)
        _write_manifest(manifest, completed)
        logger.info(
            "Checkpoint saved: %d new bulletins; %d total completed in range",
            len(pending_names), len(completed.intersection(b.filename for b in in_range)),
        )
        for values in pending.values():
            values.clear()
        pending_review.clear()
        pending_names.clear()

    for position, bulletin in enumerate(todo, start=1):
        try:
            stage_started = time.perf_counter()
            path = fetch.download_bulletin(session, bulletin)
            timings["download_cache"] += time.perf_counter() - stage_started

            stage_started = time.perf_counter()
            records = process_bulletin_file(path, bulletin.date)
            timings["parse"] += time.perf_counter() - stage_started

            has_records = bool(
                records.equities or records.bonds or records.market_cap or records.index
            )
            if not has_records:
                failures += 1
                logger.warning("No market records extracted from %s; will retry later", bulletin.filename)
                continue

            for kind, items in (
                ("equities", records.equities),
                ("bonds", records.bonds),
                ("market_cap", [records.market_cap] if records.market_cap else []),
                ("index", [records.index] if records.index else []),
            ):
                good, review = _validate(items)
                pending[kind].extend(good)
                pending_review.extend(review)
            pending_names.add(bulletin.filename)
            processed_this_run += 1

            if len(pending_names) >= checkpoint_every:
                checkpoint()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            logger.error("Failed %s; it will be retried on the next run: %s", bulletin.filename, exc)

        if position % 10 == 0 or position == len(todo):
            logger.info(
                "Backfill progress: %d/%d pending bulletins visited; %d successful this run",
                position, len(todo), processed_this_run,
            )

    checkpoint()
    logger.info(
        "Backfill summary: discovery %.2fs, download/cache %.2fs, parse/OCR %.2fs, "
        "storage %.2fs; %d/%d processed this run, %d failed/empty, %d checkpointed",
        discovery_seconds, timings["download_cache"], timings["parse"], timings["storage"],
        processed_this_run, len(todo), failures, len(completed.intersection(b.filename for b in in_range)),
    )
    return processed_this_run
