"""Stage 3 (digital branch) and 4: parse a BOC bulletin into records.

IMPORTANT / open item for contributors
---------------------------------------
This module was written from the field list and the general description of
the BOC bulletin given in the cahier des charges (sections 6 and 10), not
from a real bulletin sample. The column *header* aliases in
``EQUITY_COLUMN_ALIASES`` are a best-effort starting point and will need to
be calibrated against real BOC PDFs during Phase 2 ("Core parser") of the
project. The row-parsing logic itself (``rows_to_records``) is
format-agnostic: it only needs the alias table updated, not rewriting, once
real bulletins are available. This is intentional so the parser degrades
into "flag for review" instead of guessing silently.
"""
from __future__ import annotations

import datetime as dt
import unicodedata
from typing import Optional

import pdfplumber

from . import config
from .normalize import parse_french_int, parse_french_number

# Canonical field -> list of header aliases that may appear in a BOC table.
# Matching is case/accent-insensitive substring matching (see _normalize_header).
EQUITY_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker": ("code", "valeur", "titre", "symbole"),
    "name": ("libelle", "designation", "nom", "societe"),
    "close_price": ("cours", "dernier cours", "cours de cloture", "cours jour"),
    "change_pct": ("variation", "var %", "var.", "evolution"),
    "volume": ("volume", "quantite", "titres echanges", "qte echangee"),
    "value_fcfa": ("valeur echangee", "capitaux echanges", "montant"),
}

REQUIRED_FIELDS = ("ticker", "close_price")


def _normalize_header(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().lower()


def _map_columns(header_row: list[Optional[str]]) -> dict[str, int]:
    """Match each canonical field to a column index in a table header row."""
    normalized = [_normalize_header(cell or "") for cell in header_row]
    column_map: dict[str, int] = {}
    for field, aliases in EQUITY_COLUMN_ALIASES.items():
        for idx, cell in enumerate(normalized):
            if idx in column_map.values():
                continue
            if any(alias in cell for alias in aliases):
                column_map[field] = idx
                break
    return column_map


def rows_to_records(
    table: list[list[Optional[str]]],
    bulletin_date: dt.date,
    source_bulletin: str,
    extraction_method: str = "text_parse",
    confidence_score: float = 1.0,
) -> list[dict]:
    """Convert one extracted table (header + data rows) into equity records.

    Returns an empty list if the table's header does not look like an
    equities table (i.e. we can't confidently map the required columns) —
    the caller is expected to skip such tables (bulletins contain several
    tables: equities, bonds, notices, etc.) rather than fabricate data.
    """
    if not table or len(table) < 2:
        return []

    column_map = _map_columns(table[0])
    if not all(field in column_map for field in REQUIRED_FIELDS):
        return []

    records: list[dict] = []
    for row in table[1:]:
        if row is None or all(cell in (None, "") for cell in row):
            continue

        def cell(field: str) -> Optional[str]:
            idx = column_map.get(field)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        ticker_raw = (cell("ticker") or "").strip()
        if not ticker_raw:
            continue

        close_price = parse_french_number(cell("close_price"))
        record = {
            "date": bulletin_date,
            "ticker": ticker_raw,
            "name": (cell("name") or "").strip() or None,
            "close_price": close_price,
            "change_pct": parse_french_number(cell("change_pct")),
            "volume": parse_french_int(cell("volume")) or 0,
            "value_fcfa": parse_french_number(cell("value_fcfa")) or 0.0,
            "is_trading_day": True,
            "source_bulletin": source_bulletin,
            "extraction_method": extraction_method,
            "confidence_score": confidence_score,
        }
        records.append(record)
    return records


def _is_no_transaction_bulletin(full_text: str) -> bool:
    lowered = _normalize_header(full_text)
    return any(keyword in lowered for keyword in config.NO_TRANSACTION_KEYWORDS)


def parse_bulletin_text(
    full_text: str,
    tables: list[list[list[Optional[str]]]],
    bulletin_date: dt.date,
    source_bulletin: str,
    extraction_method: str = "text_parse",
    confidence_score: float = 1.0,
) -> list[dict]:
    """Parse already-extracted text/tables into equity records.

    Kept separate from ``parse_bulletin_pdf`` so the OCR pipeline (which
    extracts text differently) can reuse the same downstream logic, per
    section 12 step 4 of the cahier des charges.
    """
    if _is_no_transaction_bulletin(full_text):
        return [
            {
                "date": bulletin_date,
                "ticker": None,
                "name": None,
                "close_price": None,
                "change_pct": None,
                "volume": 0,
                "value_fcfa": 0.0,
                "is_trading_day": False,
                "source_bulletin": source_bulletin,
                "extraction_method": extraction_method,
                "confidence_score": confidence_score,
            }
        ]

    records: list[dict] = []
    for table in tables:
        records.extend(
            rows_to_records(
                table,
                bulletin_date=bulletin_date,
                source_bulletin=source_bulletin,
                extraction_method=extraction_method,
                confidence_score=confidence_score,
            )
        )
    return records


def parse_bulletin_pdf(
    pdf_path: str,
    bulletin_date: dt.date,
    source_bulletin: Optional[str] = None,
) -> list[dict]:
    """Parse a digital (text-layer) BOC bulletin PDF into equity records."""
    source_bulletin = source_bulletin or pdf_path
    full_text_parts: list[str] = []
    tables: list[list[list[Optional[str]]]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text_parts.append(page.extract_text() or "")
            tables.extend(page.extract_tables() or [])

    return parse_bulletin_text(
        full_text="\n".join(full_text_parts),
        tables=tables,
        bulletin_date=bulletin_date,
        source_bulletin=source_bulletin,
        extraction_method="text_parse",
        confidence_score=1.0,
    )
