"""FR-17: command line interface for manual data refresh and inspection.

Usage
-----
    pybvmac refresh
    pybvmac backfill --start 2024-01-01 --end 2024-12-31
    pybvmac tickers
    pybvmac inspect SOCAPALM --start 2025-01-01
    pybvmac inspect ECMR6 --kind bond
    pybvmac index --start 2025-01-01
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from . import api, pipeline
from .ticker import Bond, Ticker


def _cmd_refresh(_args: argparse.Namespace) -> None:
    records = pipeline.refresh()
    print(
        f"Fetched and stored {len(records.equities)} equity, "
        f"{len(records.bonds)} bond record(s) for today's bulletin."
        + (" Market cap updated." if records.market_cap else "")
        + (" Index updated." if records.index else "")
    )


def _cmd_backfill(args: argparse.Namespace) -> None:
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()
    count = pipeline.backfill(start, end)
    print(f"Processed {count} bulletin(s) between {start} and {end}.")


def _cmd_tickers(_args: argparse.Namespace) -> None:
    from . import ticker_map

    print(ticker_map.all_tickers().to_string(index=False))


def _cmd_inspect(args: argparse.Namespace) -> None:
    instrument = Bond(args.symbol) if args.kind == "bond" else Ticker(args.symbol)
    df = instrument.history(start=args.start, end=args.end)
    if df.empty:
        print(f"No data cached locally for {args.symbol}. Try `pybvmac refresh` first.")
        return
    print(df.to_string())


def _cmd_index(args: argparse.Namespace) -> None:
    df = api.all_share_index(start=args.start, end=args.end)
    if df.empty:
        print("No BVMAC-AS index data cached locally. Try `pybvmac refresh` first.")
        return
    print(df.to_string())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pybvmac", description=__doc__)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("refresh", help="fetch and store today's bulletin").set_defaults(
        func=_cmd_refresh
    )

    p_backfill = sub.add_parser("backfill", help="fetch and store historical bulletins")
    p_backfill.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_backfill.add_argument("--end", help="YYYY-MM-DD, defaults to today")
    p_backfill.set_defaults(func=_cmd_backfill)

    sub.add_parser("tickers", help="list known tickers").set_defaults(func=_cmd_tickers)

    p_inspect = sub.add_parser("inspect", help="print cached history for one instrument")
    p_inspect.add_argument("symbol", help="ticker alias (equity) or Mnemo (bond)")
    p_inspect.add_argument(
        "--kind", choices=["equity", "bond"], default="equity",
        help="equity (default, resolves aliases) or bond (Mnemo, no aliasing)",
    )
    p_inspect.add_argument("--start", help="YYYY-MM-DD")
    p_inspect.add_argument("--end", help="YYYY-MM-DD")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_index = sub.add_parser("index", help="print cached BVMAC All Share Index history")
    p_index.add_argument("--start", help="YYYY-MM-DD")
    p_index.add_argument("--end", help="YYYY-MM-DD")
    p_index.set_defaults(func=_cmd_index)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
