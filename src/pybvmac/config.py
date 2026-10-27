"""Central configuration for PyBVMAC.

Every path, URL and tunable constant used across the package lives here so
contributors have a single place to look when BVMAC changes something.
"""
from __future__ import annotations

import os
from pathlib import Path

from ._version import __version__

# ---------------------------------------------------------------------------
# Source website
# ---------------------------------------------------------------------------
BASE_URL = "https://bvm-ac.org"
WP_MEDIA_ENDPOINT = f"{BASE_URL}/wp-json/wp/v2/media"
ROBOTS_URL = f"{BASE_URL}/robots.txt"

# PyBVMAC is an independent project, not affiliated with BVMAC. We identify
# ourselves clearly and keep request rates low, as required by NFR "Legal and
# ethical compliance" in the cahier des charges.
USER_AGENT = (
    f"PyBVMAC/{__version__} "
    "(+https://github.com/song-richard/pybvmac; "
    "independent open-source project, not affiliated with BVMAC)"
)

# Minimum delay, in seconds, enforced between two outgoing HTTP requests.
MIN_REQUEST_INTERVAL_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# Local storage
# ---------------------------------------------------------------------------
_home_env = os.environ.get("PYBVMAC_HOME")
CACHE_DIR = Path(_home_env).expanduser() if _home_env else Path.home() / ".pybvmac"
RAW_DIR = CACHE_DIR / "raw"          # downloaded bulletin PDFs
DATA_DIR = CACHE_DIR / "data"        # parsed, canonical datasets
REVIEW_LOG_PATH = CACHE_DIR / "manual_review.csv"

for _dir in (CACHE_DIR, RAW_DIR, DATA_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Preferred on-disk format for canonical datasets. Falls back to CSV
# automatically if pyarrow is not installed (see storage.py).
STORAGE_FORMAT = os.environ.get("PYBVMAC_STORAGE_FORMAT", "parquet")

# ---------------------------------------------------------------------------
# Parsing / OCR
# ---------------------------------------------------------------------------
MIN_TEXT_LAYER_CHARS = 200   # below this, a bulletin is treated as scanned
OCR_LANGUAGE = "fra"
OCR_DPI = 300
# Records with an OCR confidence below this threshold (0-100) are flagged
# for manual review instead of silently accepted (FR-16).
OCR_CONFIDENCE_THRESHOLD = 60.0

NO_TRANSACTION_KEYWORDS = (
    "aucune transaction",
    "neant",
    "néant",
    "pas de transaction",
    "sans transaction",
)
