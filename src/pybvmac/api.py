"""FR-10/FR-11: module-level functions mirroring yfinance's free functions."""
from __future__ import annotations

import datetime as dt
from typing import Optional, Sequence

import pandas as pd

from . import pipeline, storage
from .ticker import Ticker


def download(
    tickers: Sequence[str] | str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
) -> pd.DataFrame:
    """FR-10: fetch history for several equities at once.

    Returns a single long-format DataFrame (one row per ticker per date)
    indexed by date, with a ``ticker`` column — the simplest shape to filter,
    pivot, or group with pandas. Mirrors ``yfinance.download`` in spirit,
    not byte-for-byte in output shape.

    ``tickers`` is normally a list (``["SOCAPALM", "SAFACAM"]``); passing a
    single ticker as a bare string (``"SOCAPALM"``) also works — it's
    treated as one ticker, not iterated character by character.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    frames = []
    for symbol in tickers:
        df = Ticker(symbol).history(start=start, end=end, period=period)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def bonds(
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """FR-11: bond data, including coupon and maturity information.

    With no ``ticker``, returns every bond's price history (same shape as
    ``download()`` for equities). Pass a bond's Mnemo (e.g. "ECMR6") to get
    just that one — equivalent to ``pybvmac.Bond(ticker).history(...)``.
    """
    if ticker:
        from .ticker import Bond

        return Bond(ticker).history(start=start, end=end)
    df = storage.load("bonds")
    return _filter_by_date(df, start, end)


def market_cap(start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """FR-11: historical market capitalization series (bulletin total)."""
    df = storage.load("market_cap")
    return _filter_by_date(df, start, end)


def all_share_index(start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """Historical BVMAC All Share Index (BVMAC-AS) level and day change."""
    df = storage.load("index")
    return _filter_by_date(df, start, end)


def tickers() -> pd.DataFrame:
    """List all known tickers with their canonical names and compartments."""
    from . import ticker_map

    return ticker_map.all_tickers()


def refresh():
    """Force a live fetch and parse of today's bulletin, bypassing the cache.

    Returns a ``pipeline.BulletinRecords`` namedtuple of
    ``(equities, bonds, market_cap, index)`` — the records that were just
    parsed and stored (``market_cap``/``index`` are ``None`` if that table
    wasn't found in the bulletin).
    """
    return pipeline.refresh()


def backfill(
    start: str, end: Optional[str] = None, *, refresh_archive: bool = False
) -> int:
    """FR-02: fetch, parse and store every bulletin BVMAC publishes between
    ``start`` and ``end`` (inclusive), populating the local cache for
    ``Ticker``/``Bond``/``download``/``bonds``/``market_cap``/
    ``all_share_index`` to read from. ``end`` defaults to today.

    Returns the number of bulletins successfully processed. Archive metadata
    is cached temporarily; set ``refresh_archive=True`` to force a fresh listing.
    """
    start_date = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end) if end else None
    return pipeline.backfill(start_date, end_date, refresh_archive=refresh_archive)


def _filter_by_date(
    df: pd.DataFrame, start: Optional[str], end: Optional[str]
) -> pd.DataFrame:
    if df.empty:
        return df.set_index("date") if "date" in df.columns else df
    if start:
        df = df[df["date"] >= dt.date.fromisoformat(start)]
    if end:
        df = df[df["date"] <= dt.date.fromisoformat(end)]
    return df.sort_values("date").reset_index(drop=True).set_index("date")
