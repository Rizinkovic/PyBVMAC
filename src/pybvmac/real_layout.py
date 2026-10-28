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
import unicodedata
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


def _compact_heading(text: str) -> str:
    """Normalize a PDF heading despite spacing, punctuation, or accents."""
    decomposed = unicodedata.normalize("NFKD", text.upper())
    without_accents = "".join(
        character for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^A-Z0-9]", "", without_accents)


_CID_ARTIFACT_RE = re.compile(r"\(cid:\d+\)")


def _cell(row: list[str], idx: int) -> str:
    """Read a compact identifier/numeric cell, removing PDF glyph spacing."""
    if idx >= len(row):
        return ""
    text = squeeze(row[idx])
    # pdfplumber renders a handful of glyphs it can't map (typically an
    # apostrophe in these bulletins) as a literal "(cid:N)" placeholder.
    return _CID_ARTIFACT_RE.sub("", text)


def _text_cell(row: list[str], idx: int) -> str:
    """Read a free-text cell while preserving real spaces between words."""
    if idx >= len(row):
        return ""
    text = " ".join((row[idx] or "").split())
    return _CID_ARTIFACT_RE.sub("", text).strip()


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
        "name": _text_cell(row, cols["name"]) or None,
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


def parse_equities_page(
    page, bulletin_date: dt.date, source_bulletin: str,
    rows: Optional[list[list[str]]] = None,
) -> list[dict]:
    """Extract equity records; accept precomputed grid rows to avoid repeat work."""
    records = []
    for row in extract_grid(page) if rows is None else rows:
        if _is_equity_row(row) and _cell(row, EQUITY_COLUMNS["mnemo"]):
            records.append(_build_record(row, EQUITY_COLUMNS, bulletin_date, source_bulletin))
    return records


def parse_bonds_page(
    page, bulletin_date: dt.date, source_bulletin: str,
    rows: Optional[list[list[str]]] = None,
) -> list[dict]:
    """Extract bond records; accept precomputed grid rows to avoid repeat work."""
    records = []
    for row in extract_grid(page) if rows is None else rows:
        if _is_bond_row(row) and _cell(row, BOND_COLUMNS["mnemo"]):
            records.append(_build_record(row, BOND_COLUMNS, bulletin_date, source_bulletin))
    return records


def parse_market_cap_page(
    page, bulletin_date: dt.date, source_bulletin: str,
    rows: Optional[list[list[str]]] = None,
) -> Optional[dict]:
    """Extract the market-cap total from the "CAPITALISATION BOURSIERE" page.

    Looks for the totals row (its last cell, before squeezing, the second
    to last is "Total") and reads the final column — the global
    ("Globale") capitalization figure.
    """
    for row in extract_grid(page) if rows is None else rows:
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
    page, bulletin_date: dt.date, source_bulletin: str,
    rows: Optional[list[list[str]]] = None,
) -> Optional[dict]:
    """Extract the BVMAC All Share Index (BVMAC-AS) value from the cover
    page. The bulletin also plots a small history chart there, but that's a
    rendered image with no underlying data table — only the current day's
    level and day-over-day variation are extractable.
    """
    index_value = None
    change_pct = None
    for row in extract_grid(page) if rows is None else rows:
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

    bond_section_active = False
    pages_with_tables = 0
    pages_visited = 0

    for page in pdf.pages:
        pages_visited += 1
        # Text extraction is much cheaper than reconstructing every cell from
        # vector geometry. Some continuation-page headings are spaced out by
        # pdfplumber, so compare a whitespace-free copy as well.
        page_text = page.extract_text() or ""
        text_upper = page_text.upper()
        compact_text = _compact_heading(text_upper)

        # The market tables precede the bulletin commentary and company
        # profiles. Stop at the commentary divider rather than allowing a
        # bond heading on an earlier page to trigger grid extraction for the
        # rest of the document.
        if "COMMENTAIRESDUBULLETINOFFICIELDELACOTE" in compact_text:
            break

        has_equity_heading = (
            "MARCHE DES ACTIONS" in text_upper
            or "MARCHEDESACTIONS" in compact_text
        )
        has_bond_heading = (
            "MARCHEDESOBLIGATIONS" in compact_text
            or (
                "OBLIGATIONS" in compact_text
                and any(term in compact_text for term in ("ETATS", "REGIONALES", "PRIVEES"))
            )
        )
        has_market_cap_heading = (
            "CAPITALISATION BOURSIERE" in text_upper
            or "CAPITALISATIONBOURSIERE" in compact_text
        )
        has_index_heading = (
            "ALL SHARE INDEX" in text_upper
            or "ALLSHAREINDEX" in compact_text
        )

        if has_bond_heading:
            bond_section_active = True
        if has_market_cap_heading:
            bond_section_active = False

        needs_grid = (
            has_equity_heading
            or (bond_section_active and not has_market_cap_heading)
            or has_market_cap_heading
            or has_index_heading
            or not text_upper.strip()
        )
        if not needs_grid:
            continue

        rows = extract_grid(page)
        pages_with_tables += 1

        if has_equity_heading:
            equities.extend(
                parse_equities_page(page, bulletin_date, source_bulletin, rows=rows)
            )
        if bond_section_active and not has_market_cap_heading:
            bonds.extend(
                parse_bonds_page(page, bulletin_date, source_bulletin, rows=rows)
            )
        if market_cap is None and has_market_cap_heading:
            market_cap = parse_market_cap_page(
                page, bulletin_date, source_bulletin, rows=rows
            )
        if index is None and has_index_heading:
            index = parse_index_page(
                page, bulletin_date, source_bulletin, rows=rows
            )

    # Kept as a debug-level diagnostic so normal runs remain readable.
    import logging
    logging.getLogger("pybvmac").info(
        "Real-layout parser visited %d/%d pages and extracted grids from %d for %s",
        pages_visited, len(pdf.pages), pages_with_tables, source_bulletin,
    )

    return equities, bonds, market_cap, index
