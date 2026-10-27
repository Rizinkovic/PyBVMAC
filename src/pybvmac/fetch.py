"""Stage 1: fetch BOC bulletins from the BVMAC website.

FR-01/FR-02: fetch today's bulletin, and enumerate the historical archive.
Section 6.2 of the cahier des charges: discovery goes through the WordPress
REST API media endpoint first (BVMAC's site is WordPress-based); a headless
browser fallback for paginating the archive page is deliberately left out of
this v0.1 (flagged below) to avoid pulling in a heavy Selenium/Playwright
dependency until it's proven necessary.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import time

from . import config
from .exceptions import FetchError
from .http_client import PoliteSession
from .normalize import bulletin_filename_for_date, parse_boc_date_from_filename

logger = logging.getLogger("pybvmac.fetch")


@dataclass
class BulletinRef:
    """A discovered bulletin: where it lives and which session it covers."""

    url: str
    filename: str
    date: Optional[dt.date]


def discover_bulletins(
    session: PoliteSession,
    search: str = "BOC",
    per_page: int = 100,
    max_pages: int = 100,
    *,
    refresh_cache: bool = False,
    cache_ttl_seconds: Optional[float] = None,
) -> list[BulletinRef]:
    """Enumerate BOC bulletins via the WordPress REST API media endpoint.

    Returns bulletins sorted by date (oldest first). Items whose filename
    does not match either known BOC naming pattern are skipped, since we
    cannot reliably assign them a trading date.

    Note: if this endpoint stops working (e.g. BVMAC disables the REST API
    or changes its media library), the fallback described in section 6.2 is
    a headless-browser archive crawl — left as a documented extension point
    rather than implemented here, per the "no overengineering" principle:
    build the primary path first, add the fallback once it's actually needed.
    """
    if per_page < 1:
        raise ValueError("per_page must be at least 1")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    ttl = config.ARCHIVE_CACHE_TTL_SECONDS if cache_ttl_seconds is None else cache_ttl_seconds
    if ttl < 0:
        raise ValueError("cache_ttl_seconds must be non-negative")

    # Repeated backfills reuse recent archive metadata rather than paging
    # through the entire WordPress media library on every invocation.
    cache_path = config.CACHE_DIR / f"archive-index-{search}-{per_page}-{max_pages}.json"
    if not refresh_cache and ttl > 0:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            age = time.time() - float(cached["fetched_at"])
            if 0 <= age < ttl:
                bulletins = [
                    BulletinRef(
                        url=item["url"],
                        filename=item["filename"],
                        date=dt.date.fromisoformat(item["date"]),
                    )
                    for item in cached["bulletins"]
                ]
                logger.info("Archive metadata cache hit: %d bulletins (age %.0fs)", len(bulletins), age)
                return bulletins
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # Missing, expired, or malformed cache: rebuild it from the source.
            pass

    bulletins: list[BulletinRef] = []
    page = 1
    total_pages = 0
    while page <= max_pages:
        try:
            response = session.get(
                config.WP_MEDIA_ENDPOINT,
                params={"search": search, "per_page": per_page, "page": page},
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as FetchError below
            status = getattr(getattr(exc, "response", None), "status_code", None)
            # WordPress commonly answers 400 for a page beyond the last one.
            # Other failures (timeouts, 5xx, rate limits) must not silently
            # turn a partial archive into an apparently complete result.
            if status in (400, 404) and page > 1:
                break
            raise FetchError(
                f"Archive discovery failed on page {page}; results may be incomplete: {exc}"
            ) from exc

        items = response.json()
        if not items:
            break

        # WordPress normally provides X-WP-TotalPages. Respect it when
        # present, and never silently present a max_pages-truncated archive
        # as complete.
        headers = getattr(response, "headers", {}) or {}
        try:
            total_pages = int(headers.get("X-WP-TotalPages", 0))
        except (TypeError, ValueError):
            total_pages = 0
        if total_pages > max_pages:
            raise FetchError(
                f"Archive has {total_pages} pages, exceeding max_pages={max_pages}; "
                "increase max_pages to collect the full archive"
            )

        for item in items:
            source_url = item.get("source_url")
            if not source_url:
                continue
            filename = source_url.rsplit("/", 1)[-1]
            date = parse_boc_date_from_filename(filename)
            if date is None:
                continue  # not a BOC bulletin, or an unrecognized naming scheme
            bulletins.append(BulletinRef(url=source_url, filename=filename, date=date))

        page += 1

    if page > max_pages and not total_pages:
        raise FetchError(
            f"Reached max_pages={max_pages} without confirming the end of the archive; "
            "increase max_pages or inspect the WordPress pagination headers"
        )

    bulletins.sort(key=lambda b: b.date)
    # Save only a fully completed discovery; partial/error results never replace it.
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(cache_path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(
                {
                    "fetched_at": time.time(),
                    "bulletins": [
                        {"url": item.url, "filename": item.filename, "date": item.date.isoformat()}
                        for item in bulletins
                    ],
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, cache_path)
    finally:
        temporary.unlink(missing_ok=True)
    return bulletins


def download_bulletin(
    session: PoliteSession, bulletin: BulletinRef, dest_dir: Path = config.RAW_DIR
) -> Path:
    """Download one bulletin PDF, skipping the request if already cached."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / bulletin.filename

    def is_valid_pdf(path: Path) -> bool:
        try:
            if path.stat().st_size < 8:
                return False
            with path.open("rb") as stream:
                # PDF headers are normally at byte 0; allow a small leading
                # offset because some valid generators prepend metadata.
                return b"%PDF-" in stream.read(1024)
        except OSError:
            return False

    if is_valid_pdf(dest_path):
        return dest_path
    # Remove corrupt/stale cache entries so they cannot be reused forever.
    dest_path.unlink(missing_ok=True)

    response = session.get(bulletin.url)
    content = response.content
    if len(content) < 8 or b"%PDF-" not in content[:1024]:
        raise FetchError(
            f"Downloaded content for {bulletin.filename} is not a valid PDF "
            f"(HTTP {response.status_code}, {len(content)} bytes)"
        )

    temporary = dest_path.with_name(dest_path.name + ".part")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, dest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return dest_path


def fetch_today_bulletin(
    session: PoliteSession, today: Optional[dt.date] = None
) -> tuple[Path, BulletinRef]:
    """FR-01: fetch the bulletin for the current trading day.

    Tries the recent filename pattern first; raises ``FetchError`` if the
    bulletin isn't published yet (e.g. run too early) or the exchange is
    closed that day.
    """
    today = today or dt.date.today()
    filename = bulletin_filename_for_date(today)
    url = f"{config.BASE_URL}/wp-content/uploads/{today:%Y}/{today:%m}/{filename}"

    try:
        session.head(url)
    except Exception as exc:  # noqa: BLE001
        raise FetchError(
            f"No BOC bulletin found for {today.isoformat()} at {url}: {exc}"
        ) from exc

    bulletin = BulletinRef(url=url, filename=filename, date=today)
    path = download_bulletin(session, bulletin)
    return path, bulletin
