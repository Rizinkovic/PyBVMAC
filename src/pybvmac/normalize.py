"""Normalization helpers: French numeric formats, bulletin filenames, dates.

BOC bulletins use French conventions: a space (or non-breaking space) as the
thousands separator and a comma as the decimal separator, e.g. "12 345,67".
This module turns that, and the two known BOC filename patterns, into plain
Python types.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

# "no value" markers seen in French administrative bulletins.
_EMPTY_MARKERS = {"", "-", "--", "n/a", "na", "nd", "n.d.", "none"}

_NUMBER_CLEAN_RE = re.compile(r"[\s\u00a0\u202f]")  # normal, nbsp, narrow-nbsp


def parse_french_number(raw: Optional[str]) -> Optional[float]:
    """Parse a French-formatted number string into a float.

    Examples
    --------
    >>> parse_french_number("12 345,67")
    12345.67
    >>> parse_french_number("+2,50%")
    2.5
    >>> parse_french_number("-")
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _EMPTY_MARKERS:
        return None

    text = text.replace("%", "").strip()
    text = _NUMBER_CLEAN_RE.sub("", text)
    text = text.replace(",", ".")
    # A leading "+" is valid for float(); nothing else to strip.
    try:
        return float(text)
    except ValueError:
        return None


def parse_french_int(raw: Optional[str]) -> Optional[int]:
    """Parse a French-formatted integer string (e.g. volumes)."""
    value = parse_french_number(raw)
    if value is None:
        return None
    return int(round(value))


# ---------------------------------------------------------------------------
# Filenames and dates
# ---------------------------------------------------------------------------
# Recent pattern, e.g. "BOC-20260917.pdf"
_FILENAME_RE_NEW = re.compile(r"BOC[-_]?(\d{4})(\d{2})(\d{2})", re.IGNORECASE)
# Older pattern, e.g. "BOC-BVMAC-17-09-2026.pdf"
_FILENAME_RE_OLD = re.compile(
    r"BOC-BVMAC-(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE
)


def parse_boc_date_from_filename(filename: str) -> Optional[dt.date]:
    """Extract the trading session date from a BOC bulletin filename.

    Supports both known naming conventions described in the cahier des
    charges (section 6.1). Returns None if the filename does not match
    either pattern.
    """
    match = _FILENAME_RE_NEW.search(filename)
    if match:
        year, month, day = (int(g) for g in match.groups())
        return _safe_date(year, month, day)

    match = _FILENAME_RE_OLD.search(filename)
    if match:
        day, month, year = (int(g) for g in match.groups())
        return _safe_date(year, month, day)

    return None


def _safe_date(year: int, month: int, day: int) -> Optional[dt.date]:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def bulletin_filename_for_date(date: dt.date) -> str:
    """Build the current-style filename PyBVMAC expects for a given date."""
    return f"BOC-{date:%Y%m%d}.pdf"
