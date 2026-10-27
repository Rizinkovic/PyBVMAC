"""FR-07: reconcile ticker/name variants across bulletins.

Ships a small seed CSV (``data/ticker_map.csv``) with the handful of
instruments explicitly named in the cahier des charges. Real coverage of the
BVMAC listing is expected to grow via contributor pull requests as bulletins
are parsed and new aliases are observed — see CONTRIBUTING notes in the
README.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional

import pandas as pd

from .exceptions import UnknownTickerError

_SEED_CSV = "ticker_map.csv"


def _normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().upper()


@lru_cache(maxsize=1)
def load_ticker_map(extra_csv: Optional[str] = None) -> pd.DataFrame:
    """Load the ticker mapping table.

    Parameters
    ----------
    extra_csv:
        Optional path to a CSV with the same columns
        (ticker, alias, name, compartment, asset_class) to append user- or
        organization-specific aliases on top of the seed table.
    """
    with resources.as_file(resources.files("pybvmac.data") / _SEED_CSV) as path:
        df = pd.read_csv(path)

    if extra_csv:
        extra = pd.read_csv(Path(extra_csv))
        df = pd.concat([df, extra], ignore_index=True)

    df["_alias_key"] = df["alias"].map(_normalize_key)
    return df


def resolve(symbol_or_alias: str) -> str:
    """Resolve any known alias to its canonical ticker code.

    Raises ``UnknownTickerError`` if the symbol is not in the ticker map,
    rather than guessing — an unresolved ticker is a signal that the map
    needs a new alias, not that the module should invent a match.
    """
    table = load_ticker_map()
    key = _normalize_key(symbol_or_alias)
    matches = table.loc[table["_alias_key"] == key, "ticker"]
    if matches.empty:
        raise UnknownTickerError(
            f"Unknown ticker or alias: {symbol_or_alias!r}. "
            "It may be missing from pybvmac's ticker map — see "
            "src/pybvmac/data/ticker_map.csv."
        )
    return str(matches.iloc[0])


def all_tickers() -> pd.DataFrame:
    """Return the canonical ticker list as a DataFrame (one row per ticker)."""
    table = load_ticker_map()
    return (
        table.drop(columns=["_alias_key", "alias"])
        .drop_duplicates(subset="ticker")
        .reset_index(drop=True)
    )
