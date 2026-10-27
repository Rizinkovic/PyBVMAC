"""PyBVMAC: an open source Python client for BVMAC market data.

Usage mirrors yfinance:

    import pybvmac

    pybvmac.backfill(start="2020-01-01")   # populate the local cache first
    df = pybvmac.Ticker("SOCAPALM").history(start="2020-01-01")
    df_multi = pybvmac.download(["SOCAPALM", "SAFACAM"], period="5y")
    bond_df = pybvmac.Bond("ECMR6").history(period="1y")
    bonds_df = pybvmac.bonds()
    cap_df = pybvmac.market_cap()
    index_df = pybvmac.all_share_index()

PyBVMAC is an independent, unofficial project. It is not produced by,
sponsored by, or affiliated with BVMAC.
"""

from ._version import __version__
from .api import all_share_index, backfill, bonds, download, market_cap, refresh, tickers
from .exceptions import (
    FetchError,
    OCRNotAvailableError,
    ParseError,
    PyBVMACError,
    UnknownTickerError,
)
from .ticker import Bond, Ticker

__all__ = [
    "__version__",
    "Ticker",
    "Bond",
    "download",
    "bonds",
    "market_cap",
    "all_share_index",
    "tickers",
    "refresh",
    "backfill",
    "PyBVMACError",
    "FetchError",
    "ParseError",
    "OCRNotAvailableError",
    "UnknownTickerError",
]
