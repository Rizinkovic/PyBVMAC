"""Stage 5: store validated records in a versioned local dataset.

FR-08: store parsed records in Parquet, SQLite, or CSV. We use Parquet when
pyarrow is available (the default, best for size and speed) and transparently
fall back to CSV otherwise, so the module works with the base install.

FR-16: records below the OCR confidence threshold are appended to a manual
review log instead of the main dataset.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
import os

import pandas as pd

from . import config

EQUITY_COLUMNS = [
    "date",
    "ticker",
    "name",
    "compartment",
    "close_price",
    "change_pct",
    "volume",
    "value_fcfa",
    "is_trading_day",
    "source_bulletin",
    "extraction_method",
    "confidence_score",
]
BOND_COLUMNS = EQUITY_COLUMNS + ["coupon_rate", "maturity_date", "outstanding_amount"]
MARKET_CAP_COLUMNS = ["date", "market_cap_fcfa", "source_bulletin"]
INDEX_COLUMNS = ["date", "index_value", "change_pct", "source_bulletin"]

_DEDUPE_KEYS = {
    "equities": ["date", "ticker", "source_bulletin"],
    "bonds": ["date", "ticker", "source_bulletin"],
    "market_cap": ["date", "source_bulletin"],
    "index": ["date", "source_bulletin"],
}


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401

        return True
    except ImportError:
        return False


def _dataset_path(kind: str) -> Path:
    use_parquet = config.STORAGE_FORMAT == "parquet" and _pyarrow_available()
    ext = "parquet" if use_parquet else "csv"
    return config.DATA_DIR / f"{kind}.{ext}"


def load(kind: str = "equities") -> pd.DataFrame:
    """Load the full local dataset for a given kind ('equities', 'bonds',
    'market_cap'). Returns an empty, correctly-typed DataFrame if nothing has
    been collected yet.
    """
    path = _dataset_path(kind)
    columns = {
        "equities": EQUITY_COLUMNS,
        "bonds": BOND_COLUMNS,
        "market_cap": MARKET_CAP_COLUMNS,
        "index": INDEX_COLUMNS,
    }.get(kind, EQUITY_COLUMNS)

    if not path.exists():
        return pd.DataFrame(columns=columns)

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def save_all(df: pd.DataFrame, kind: str = "equities") -> Path:
    """Atomically replace a canonical dataset with ``df``.

    Write to a sibling temporary file first. If serialization or the process
    fails, the previous complete dataset remains available.
    """
    path = _dataset_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        if path.suffix == ".parquet":
            df.to_parquet(temporary, index=False)
        else:
            df.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        # A failed write may leave a partial temporary file behind.
        if temporary.exists():
            temporary.unlink()
    return path


def append(records: Iterable[dict], kind: str = "equities") -> pd.DataFrame:
    """Append new records to the dataset, de-duplicating on the natural key.

    Later records win on conflict (e.g. a corrected re-parse of the same
    bulletin), matching the "manual correction log" idea in section 12.
    """
    new_df = pd.DataFrame(list(records))
    if new_df.empty:
        return load(kind)

    existing = load(kind)
    combined = pd.concat([existing, new_df], ignore_index=True, sort=False)

    dedupe_keys = [k for k in _DEDUPE_KEYS.get(kind, ["date"]) if k in combined.columns]
    if dedupe_keys:
        combined = combined.drop_duplicates(subset=dedupe_keys, keep="last")

    combined = combined.sort_values("date").reset_index(drop=True)
    save_all(combined, kind)
    return combined


def flag_for_review(records: Iterable[dict]) -> None:
    """Append low-confidence OCR records to the manual review log (FR-16)."""
    records = list(records)
    if not records:
        return
    new_df = pd.DataFrame(records)
    if config.REVIEW_LOG_PATH.exists():
        existing = pd.read_csv(config.REVIEW_LOG_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True, sort=False)
    else:
        combined = new_df
    combined.to_csv(config.REVIEW_LOG_PATH, index=False)
