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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from . import config
from .exceptions import FetchError
from .http_client import PoliteSession
from .normalize import bulletin_filename_for_date, parse_boc_date_from_filename


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
    bulletins: list[BulletinRef] = []
    page = 1
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
            if status in (400, 404):
                break
            raise FetchError(
                f"Archive discovery failed on page {page}; results may be incomplete: {exc}"
            ) from exc

        items = response.json()
        if not items:
            break

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

    bulletins.sort(key=lambda b: b.date)
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
