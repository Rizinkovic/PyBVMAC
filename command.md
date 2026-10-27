# PyBVMAC — Commands & Local Testing

Quick reference for testing the package on your machine before deploying
(e.g. before wiring up the GitHub Actions cron job).

## 1. Install locally (editable)

```bash
cd pybvmac_pkg
pip install -e ".[dev,ocr,parquet]"
```

`-e` (editable) means code changes take effect immediately, no reinstall
needed. `[dev,ocr,parquet]` are optional extras — `dev` for pytest,
`parquet` for the preferred storage format, `ocr` only if you'll test
scanned/historical bulletins.

## 2. Run the automated test suite

```bash
pytest
```

Should show `38 passed`. This runs entirely offline — no BVMAC access
needed. It includes a regression test (`tests/test_real_layout.py`) run
against a real bulletin shipped in `tests/fixtures/BOC-20260916.pdf`, which
is the fastest way to know if a code change broke parsing.

## 3. Test against a real bulletin without touching the network

This is the recommended way to test end-to-end before deploying, since it
never calls BVMAC:

```bash
# Set an isolated cache dir so you don't pollute ~/.pybvmac
export PYBVMAC_HOME=/tmp/pybvmac_test

python3 -c "
from pybvmac import pipeline
import datetime as dt

# Point this at any real BOC PDF you have on disk (the shipped fixture,
# or one you download by hand once from bvm-ac.org)
records = pipeline.process_bulletin_file(
    'tests/fixtures/BOC-20260916.pdf', dt.date(2026, 9, 16)
)
print('equities:', len(records.equities))
print('bonds:', len(records.bonds))
print('market_cap:', records.market_cap)
print('index:', records.index)

pipeline._store(records)   # writes into \$PYBVMAC_HOME
"
```

Then query it through the normal API:

```bash
python3 -c "
import pybvmac
print(pybvmac.Ticker('SOCAPALM').history())
print(pybvmac.Bond('ECMR6').history())
print(pybvmac.all_share_index())
"
```

Or via the CLI (also reads `\$PYBVMAC_HOME`):

```bash
pybvmac inspect SOCAPALM
pybvmac inspect ECMR6 --kind bond
pybvmac index
pybvmac tickers
```

## 4. Test the live network path (fetch/refresh/backfill)

Only do this once you're ready to actually hit bvm-ac.org — it respects
robots.txt and rate-limits itself, but it's still a real request.

```bash
export PYBVMAC_HOME=/tmp/pybvmac_test
pybvmac refresh -v          # fetch + parse + store TODAY's bulletin
pybvmac backfill --start 2026-09-01 -v
```

`-v` turns on debug logging so you can see each HTTP request and what got
parsed/skipped.

## 5. Reset between test runs

```bash
rm -rf /tmp/pybvmac_test
```

Nothing under your real `~/.pybvmac` is touched as long as `PYBVMAC_HOME`
is set to a test path.

---

## Essential commands (CLI)

| Command | What it does |
|---|---|
| `pybvmac refresh` | Fetch + parse + store **today's** bulletin (network) |
| `pybvmac backfill --start YYYY-MM-DD [--end YYYY-MM-DD]` | Fetch + parse + store a historical range (network) |
| `pybvmac tickers` | List known equity tickers (Mnemo, name, compartment) |
| `pybvmac inspect SYMBOL [--start] [--end]` | Print cached equity history (SYMBOL is an alias, e.g. `SOCAPALM`) |
| `pybvmac inspect SYMBOL --kind bond [--start] [--end]` | Print cached bond history (SYMBOL is the Mnemo, e.g. `ECMR6`) |
| `pybvmac index [--start] [--end]` | Print cached BVMAC All Share Index history |
| `pybvmac -v <command>` | Any command with debug logging |

## Essential commands (Python API)

| Call | Returns |
|---|---|
| `pybvmac.refresh()` | `BulletinRecords(equities, bonds, market_cap, index)` for today, fetched live and stored |
| `pybvmac.backfill(start="YYYY-MM-DD", end=None)` | int count of bulletins fetched, parsed and stored over a range (network) |
| `pybvmac.Ticker("SOCAPALM").history(start=, end=, period=)` | Equity price history, cache only, no network |
| `pybvmac.Bond("ECMR6").history(start=, end=, period=)` | Bond price history, cache only, no network |
| `pybvmac.download(["SOCAPALM", "SAFACAM"], period="5y")` | Combined equity history for several tickers (a bare string also works for one ticker) |
| `pybvmac.bonds(ticker=None, start=, end=)` | All bonds, or one bond by Mnemo |
| `pybvmac.market_cap(start=, end=)` | Bulletin-wide market cap total, by date |
| `pybvmac.all_share_index(start=, end=)` | BVMAC-AS level + daily change, by date |
| `pybvmac.tickers()` | DataFrame of known equity tickers/aliases |

**Key thing to remember:** `Ticker`/`Bond`/`download`/`bonds`/`market_cap`/
`all_share_index` all read the **local cache only** — call `refresh()` or
`backfill()` first (or use `pipeline.process_bulletin_file()` directly on a
PDF you already have, as in section 3) or you'll just get empty results.
