"""FR-09: the Ticker class, modeled on yfinance.Ticker."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

import pandas as pd

from . import storage, ticker_map

_PERIOD_RE = re.compile(r"^(\d+)(d|mo|y)$")


def _period_to_start(period: str, end: dt.date) -> dt.date:
    match = _PERIOD_RE.match(period.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid period: {period!r}. Use a form like '5d', '6mo', '5y', or 'max'."
        )
    n, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return end - dt.timedelta(days=n)
    if unit == "mo":
        return end - dt.timedelta(days=int(n * 30.44))
    return end - dt.timedelta(days=int(n * 365.25))


class Ticker:
    """A single BVMAC-listed equity.

    Examples
    --------
    >>> import pybvmac
    >>> t = pybvmac.Ticker("SOCAPALM")
    >>> df = t.history(start="2025-01-01")
    """

    _STORAGE_KIND = "equities"

    def __init__(self, symbol: str):
        self.symbol = ticker_map.resolve(symbol)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Ticker({self.symbol!r})"

    def history(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return this instrument's price history as a pandas DataFrame.

        Parameters
        ----------
        start, end:
            ISO date strings (YYYY-MM-DD). ``end`` defaults to today.
        period:
            Alternative to ``start``: a relative window such as "5d", "6mo",
            "5y", or "max". Ignored if ``start`` is given.

        Notes
        -----
        This reads from the local cache only (FR-12) — it never hits the
        network. Populate the cache first with ``pybvmac.refresh()`` (today's
        bulletin) or ``pybvmac.backfill(start=...)`` (a historical range);
        an empty cache returns an empty DataFrame, not an error.
        """
        return _history_from_storage(self._STORAGE_KIND, self.symbol, start, end, period)

    def info(self) -> dict:
        """Static metadata about this instrument (name, compartment, ...)."""
        table = ticker_map.all_tickers()
        row = table.loc[table["ticker"] == self.symbol]
        if row.empty:
            return {"ticker": self.symbol}
        return row.iloc[0].to_dict()


class Bond:
    """A single BVMAC-listed bond, identified by its Mnemo (e.g. "ECMR6",
    "EBD04", "AFC03") — BVMAC bulletins don't publish a separate friendly
    name per bond the way they do for equities, so unlike ``Ticker`` this
    takes the Mnemo directly rather than resolving an alias.

    Examples
    --------
    >>> import pybvmac
    >>> b = pybvmac.Bond("ECMR6")
    >>> df = b.history(period="1y")
    """

    _STORAGE_KIND = "bonds"

    def __init__(self, mnemo: str):
        self.symbol = mnemo.strip().upper()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Bond({self.symbol!r})"

    def history(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """Same contract as ``Ticker.history`` — see its docstring."""
        return _history_from_storage(self._STORAGE_KIND, self.symbol, start, end, period)

    def info(self) -> dict:
        """Static fields for this bond (name, coupon rate, maturity, ...)
        from the most recent cached record, if any.
        """
        df = storage.load(self._STORAGE_KIND)
        rows = df[df["ticker"] == self.symbol]
        if rows.empty:
            return {"ticker": self.symbol}
        return rows.sort_values("date").iloc[-1].to_dict()


def _history_from_storage(
    kind: str,
    symbol: str,
    start: Optional[str],
    end: Optional[str],
    period: Optional[str],
) -> pd.DataFrame:
    df = storage.load(kind)
    df = df[df["ticker"] == symbol].copy()
    if df.empty:
        return df.set_index("date")

    end_date = dt.date.fromisoformat(end) if end else dt.date.today()
    if start:
        start_date = dt.date.fromisoformat(start)
    elif period and period != "max":
        start_date = _period_to_start(period, end_date)
    else:
        start_date = df["date"].min()

    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    result = df.loc[mask].sort_values("date").reset_index(drop=True)
    return result.set_index("date")
