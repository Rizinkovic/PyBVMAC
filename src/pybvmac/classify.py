"""Stage 2 of the pipeline: classify a bulletin as digital or scanned.

FR-03: detect whether a bulletin PDF contains a text layer or is a scanned
image, so stage 3 can route it to the direct parser or to OCR.
"""
from __future__ import annotations

import pdfplumber

from . import config


def has_text_layer(pdf_path: str, min_chars: int = config.MIN_TEXT_LAYER_CHARS) -> bool:
    """Return True if the PDF has enough extractable text to skip OCR.

    We sum the extracted text length across the first few pages rather than
    the whole document, since even a scanned bulletin's metadata or a stray
    text box could otherwise create a false positive.
    """
    total_chars = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:3]:
            text = page.extract_text() or ""
            total_chars += len(text.strip())
            if total_chars >= min_chars:
                return True
    return total_chars >= min_chars
