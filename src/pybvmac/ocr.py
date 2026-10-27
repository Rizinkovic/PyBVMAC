"""Stage 3 (scanned branch): OCR pipeline for historical bulletins.

Implements section 12 of the cahier des charges. This is an optional
dependency (``pip install pybvmac[ocr]``) because it requires the Tesseract
binary to be installed on the host system in addition to Python packages.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from . import config
from .exceptions import OCRNotAvailableError
from .parse import parse_bulletin_text

try:
    import pytesseract
    from pdf2image import convert_from_path

    _OCR_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without extras installed
    _OCR_AVAILABLE = False


def _require_ocr() -> None:
    if not _OCR_AVAILABLE:
        raise OCRNotAvailableError(
            "OCR dependencies are not installed. Run: pip install pybvmac[ocr] "
            "and make sure the Tesseract binary (with the French language "
            "pack) is available on PATH."
        )


def ocr_pdf(
    pdf_path: str, lang: str = config.OCR_LANGUAGE, dpi: int = config.OCR_DPI
) -> tuple[str, float]:
    """Run OCR over every page of a scanned PDF.

    Returns a tuple of (full_text, average_confidence) where confidence is
    on a 0-100 scale, aggregated from Tesseract's per-word confidences
    (words with confidence -1, meaning "no text", are ignored).
    """
    _require_ocr()

    images = convert_from_path(pdf_path, dpi=dpi)
    text_parts: list[str] = []
    confidences: list[float] = []

    for image in images:
        text_parts.append(pytesseract.image_to_string(image, lang=lang))
        data = pytesseract.image_to_data(
            image, lang=lang, output_type=pytesseract.Output.DICT
        )
        confidences.extend(
            float(c) for c in data.get("conf", []) if _is_valid_conf(c)
        )

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(text_parts), avg_confidence


def _is_valid_conf(raw_conf) -> bool:
    try:
        return float(raw_conf) >= 0
    except (TypeError, ValueError):
        return False


def parse_scanned_bulletin(
    pdf_path: str,
    bulletin_date: dt.date,
    source_bulletin: Optional[str] = None,
) -> list[dict]:
    """OCR a scanned bulletin and parse it with the shared table logic.

    Note: pdfplumber's ``extract_tables`` needs a text layer, which a scan
    does not have, so table structure has to be reconstructed from the OCR
    text. As a pragmatic v0.1 approach we rely on Tesseract's own layout
    analysis (``image_to_string`` preserves whitespace-aligned columns
    reasonably well for simple bulletin tables) and treat whitespace-split
    lines as table rows. This is the part of the pipeline most likely to
    need iteration once real scanned bulletins are available (see FR-16 and
    the manual review queue in storage.py).
    """
    source_bulletin = source_bulletin or pdf_path
    full_text, confidence = ocr_pdf(pdf_path)

    tables = [_lines_to_pseudo_table(full_text)]
    return parse_bulletin_text(
        full_text=full_text,
        tables=tables,
        bulletin_date=bulletin_date,
        source_bulletin=source_bulletin,
        extraction_method="ocr",
        confidence_score=round(confidence, 2),
    )


def _lines_to_pseudo_table(text: str) -> list[list[str]]:
    """Very simple fallback: split each OCR'd line on runs of whitespace.

    Produces a "table" pdfplumber-style (list of rows, each a list of
    cells) that ``parse.rows_to_records`` can consume. The first
    line-with-multiple-columns is treated as the header.
    """
    import re

    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        cells = re.split(r"\s{2,}", line)
        if len(cells) >= 2:
            rows.append(cells)
    return rows
