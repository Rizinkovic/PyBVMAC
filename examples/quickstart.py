"""Quick start: refresh the local dataset, then plot one instrument.

Run once to populate the cache:
    python examples/quickstart.py --refresh

Then, any time, to plot from the local cache:
    python examples/quickstart.py
"""
from __future__ import annotations

import argparse

import matplotlib.pyplot as plt

import pybvmac


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="fetch today's bulletin first")
    parser.add_argument("--ticker", default="SOCAPALM")
    args = parser.parse_args()

    if args.refresh:
        records = pybvmac.refresh()
        print(
            f"Stored {len(records.equities)} equity and "
            f"{len(records.bonds)} bond record(s) from today's bulletin."
        )

    df = pybvmac.Ticker(args.ticker).history(period="1y")
    if df.empty:
        print(
            f"No cached data for {args.ticker} yet. "
            "Run with --refresh, or `pybvmac backfill --start 2020-01-01` first."
        )
        return

    print(df.tail())
    df["close_price"].plot(title=f"{args.ticker} closing price")
    plt.xlabel("Date")
    plt.ylabel("FCFA")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
