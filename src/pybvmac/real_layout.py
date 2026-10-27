"""Parser for the real BOC bulletin layout.

Calibrated against a genuine bulletin (BOC-20260916.pdf, N°2596 du
16/09/2026). Real BVMAC bulletins turn out to have a fixed, wide,
multi-row-header table template for both the equities ("MARCHE DES
ACTIONS") and bond ("MARCHE DES OBLIGATIONS", split into "OBLIGATIONS DES
ETATS" / "OBLIGATIONS REGIONALES" / "OBLIGATIONS PRIVEES") sections, and a
separate "CAPITALISATION BOURSIERE" table with the market-cap total.

Rather than parse the (multi-row, often visually-garbled — see grid.py's
docstring) header text, this module recognizes data rows structurally: a
row belongs to the equities table if it has the equities column count and
a valid date in the equities "Date" column position, and likewise for
bonds. This sidesteps needing to reliably OCR/read the header at all,
which is the fragile part of this particular export format.

The ticker used throughout is the bulletin's own "Mnemo" column — the
short code BVMAC itself uses to identify the instrument (e.g. "SOCAP" for
SOCAPALM, "ECMR6" for the 2029 Cameroon government bond) — per BVMAC
convention, not the longer display name.

Column layout note
-------------------
This is the layout observed in the calibration bulletin. If a future
bulletin adds/removes a column, row classification (date-in-expected-slot)
will simply stop matching for the shifted layout and the function returns
no rows for that page — a silent miss rather than silently wrong data. If
that starts happening, re-run the inspection in this module's companion
notes against a fresh sample and update the *_COLUMNS indices below.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from .grid import extract_grid, squeeze
from .normalize import parse_french_int, parse_french_number

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_STATUT_VALUES = {"NC", "PEq", "PEQ", "SUS", "RES"}

# Column indices (0-based) in the real BOC "MARCHE DES ACTIONS" table.
EQUITY_COLUMNS = {
    "isin": 1,
    "mnemo": 2,
    "name": 3,
    "prev_close": 4,
    "prev_date": 5,
    "volume": 8,
    "value_fcfa": 9,
    "nbr_trans": 10,
    "statut": 11,
    "close_price": 13,
    "change_pct": 16,
}
EQUITY_NCOLS = 21

# Column indices (0-based) in the real BOC bond tables (OBLIGATIONS DES
# ETATS / REGIONALES / PRIVEES all share this layout).
BOND_COLUMNS = {
    "name": 1,
    "isin": 2,
    "mnemo": 3,
    "prev_date": 4,
    "volume": 11,
    "value_fcfa": 12,
    "nbr_trans": 13,
    "statut": 14,
    "close_price": 16,
    "change_pct": 19,
}
BOND_NCOLS = 21


_CID_ARTIFACT_RE = re.compile(r"\(cid:\d+\)")


def _cell(row: list[str], idx: int) -> str:
    if idx >= len(row):
        return ""
    text = squeeze(row[idx])
    # pdfplumber renders a handful of glyphs it can't map (typically an
    # apostrophe in these bulletins) as a literal "(cid:N)" placeholder.
    return _CID_ARTIFACT_RE.sub("", text)


def _is_equity_row(row: list[str]) -> bool:
    return len(row) == EQUITY_NCOLS and bool(
        _DATE_RE.match(_cell(row, EQUITY_COLUMNS["prev_date"]))
    )


def _is_bond_row(row: list[str]) -> bool:
    return len(row) == BOND_NCOLS and bool(
        _DATE_RE.match(_cell(row, BOND_COLUMNS["prev_date"]))
    )


def _build_record(row: list[str], cols: dict, bulletin_date: dt.date, source_bulletin: str) -> dict:
    ticker = _cell(row, cols["mnemo"])
    return {
        "date": bulletin_date,
        "ticker": ticker,
        "name": _cell(row, cols["name"]) or None,
        "compartment": None,
        "close_price": parse_french_number(row[cols["close_price"]]),
        "change_pct": parse_french_number(row[cols["change_pct"]]),
        "volume": parse_french_int(row[cols["volume"]]) or 0,
        "value_fcfa": parse_french_number(row[cols["value_fcfa"]]) or 0.0,
        "is_trading_day": True,
        "source_bulletin": source_bulletin,
        "extraction_method": "text_parse",
        "confidence_score": 1.0,
    }


def parse_equities_page(page, bulletin_date: dt.date, source_bulletin: str) -> list[dict]:
    """Extract equity records from a page containing "MARCHE DES ACTIONS"."""
    records = []
    for row in extract_grid(page):
        if _is_equity_row(row) and _cell(row, EQUITY_COLUMNS["mnemo"]):
            records.append(_build_record(row, EQUITY_COLUMNS, bulletin_date, source_bulletin))
    return records


def parse_bonds_page(page, bulletin_date: dt.date, source_bulletin: str) -> list[dict]:
    """Extract bond records from a page containing any of the "OBLIGATIONS
    DES ETATS / REGIONALES / PRIVEES" tables (any number of them per page).
    """
    records = []
    for row in extract_grid(page):
        if _is_bond_row(row) and _cell(row, BOND_COLUMNS["mnemo"]):
            records.append(_build_record(row, BOND_COLUMNS, bulletin_date, source_bulletin))
    return records


def parse_market_cap_page(
    page, bulletin_date: dt.date, source_bulletin: str
) -> Optional[dict]:
    """Extract the market-cap total from the "CAPITALISATION BOURSIERE" page.

    Looks for the totals row (its last cell, before squeezing, the second
    to last is "Total") and reads the final column — the global
    ("Globale") capitalization figure.
    """
    for row in extract_grid(page):
        if len(row) < 3:
            continue
        if any(squeeze(cell) == "Total" for cell in row):
            value = parse_french_number(row[-1])
            if value:
                return {
                    "date": bulletin_date,
                    "market_cap_fcfa": value,
                    "source_bulletin": source_bulletin,
                }
    return None


def parse_index_page(
    page, bulletin_date: dt.date, source_bulletin: str
) -> Optional[dict]:
    """Extract the BVMAC All Share Index (BVMAC-AS) value from the cover
    page. The bulletin also plots a small history chart there, but that's a
    rendered image with no underlying data table — only the current day's
    level and day-over-day variation are extractable.
    """
    index_value = None
    change_pct = None
    for row in extract_grid(page):
        if len(row) < 2:
            continue
        label = squeeze(row[0])
        if label == "BVMAC-AS":
            index_value = parse_french_number(row[1])
        elif label == "Variationjour":
            change_pct = parse_french_number(row[1])

    if index_value is None:
        return None
    return {
        "date": bulletin_date,
        "index_value": index_value,
        "change_pct": change_pct,
        "source_bulletin": source_bulletin,
    }


def parse_bulletin(
    pdf, bulletin_date: dt.date, source_bulletin: str
) -> tuple[list[dict], list[dict], Optional[dict], Optional[dict]]:
    """Parse every page of an already-open pdfplumber PDF for equities,
    bonds, the market-cap total, and the BVMAC-AS index. Pages that don't
    contain a matching table simply contribute nothing — this scans the
    whole document rather than assuming a fixed page layout, since
    bulletins vary in length with the number of listed bonds.
    """
    equities: list[dict] = []
    bonds: list[dict] = []
    market_cap: Optional[dict] = None
    index: Optional[dict] = None

    for page in pdf.pages:
        equities.extend(parse_equities_page(page, bulletin_date, source_bulletin))
        bonds.extend(parse_bonds_page(page, bulletin_date, source_bulletin))
        text_upper = (page.extract_text() or "").upper()
        if market_cap is None and "CAPITALISATION BOURSIERE" in text_upper:
            market_cap = parse_market_cap_page(page, bulletin_date, source_bulletin)
        if index is None and "ALL SHARE INDEX" in text_upper:
            index = parse_index_page(page, bulletin_date, source_bulletin)

    return equities, bonds, market_cap, index
