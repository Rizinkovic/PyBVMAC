# PyBVMAC

An open source Python module for **BVMAC** (Bourse des Valeurs Mobilieres de
l'Afrique Centrale) market data — the `yfinance` of Central Africa's regional
stock exchange.

> **Independent project.** PyBVMAC is not produced by, sponsored by, or
> affiliated with BVMAC. It reads the same public PDF bulletins any visitor
> to bvm-ac.org can download, and republishes them as structured data.

BVMAC does not expose a machine-readable market data API. Information is
published as the **Bulletin Officiel de la Cote (BOC)**, a daily PDF. PyBVMAC
downloads, parses (with OCR for older scanned bulletins), and caches those
bulletins locally, then exposes them through a small API modeled on
`yfinance` so they drop straight into `pandas` / `numpy` / `matplotlib`
workflows.

## Install

```bash
pip install pybvmac          # core
pip install pybvmac[ocr]     # + OCR for scanned historical bulletins
                              #   also requires the Tesseract binary + French
                              #   language pack on your system
pip install pybvmac[parquet] # + Parquet storage (recommended)
```

## Quick start

```python
import pybvmac

# Populate the local cache with today's bulletin (or use the CLI/cron job below)
pybvmac.refresh()

# Single equity, pandas DataFrame indexed by date
df = pybvmac.Ticker("SOCAPALM").history(start="2020-01-01", end="2026-09-17")

# Multiple equities at once
df_multi = pybvmac.download(["SOCAPALM", "SAFACAM"], period="5y")

# A single bond, by its BVMAC Mnemo (not a friendly name -- see "Real bulletin
# layout" below for why)
bond_df = pybvmac.Bond("ECMR6").history(period="1y")

# All bonds, or one bond via the module function
bonds_df = pybvmac.bonds()
one_bond_df = pybvmac.bonds(ticker="ECMR6", start="2025-01-01")

# Market capitalization (bulletin total) and the BVMAC All Share Index
cap_df = pybvmac.market_cap(start="2023-01-01")
index_df = pybvmac.all_share_index(start="2023-01-01")

# Standard downstream analysis
import matplotlib.pyplot as plt
df["close_price"].plot(title="SOCAPALM closing price")
plt.show()
```

See `examples/quickstart.py` for a runnable version.

## Command line

```bash
pybvmac refresh                              # fetch & store today's bulletin
pybvmac backfill --start 2020-01-01          # backfill the historical archive
pybvmac tickers                              # list known equity tickers
pybvmac inspect SOCAPALM --start 2025-01-01  # equity history (alias resolved)
pybvmac inspect ECMR6 --kind bond            # bond history (Mnemo, no alias)
pybvmac index                                # BVMAC All Share Index history
```

## How it works

Five-stage pipeline (see `src/pybvmac/pipeline.py`):

1. **Fetch** (`fetch.py`) — discover bulletins via the BVMAC WordPress REST
   API media endpoint; download today's bulletin or the full archive.
2. **Classify** (`classify.py`) — does the PDF have a usable text layer, or
   is it a scanned image?
3. **Parse or OCR** — for text-layer bulletins, `real_layout.py` is the
   primary parser (see "Real bulletin layout" below); `parse.py`'s generic
   alias-based table parser is a fallback for other templates, and `ocr.py`
   handles scanned pages with `pytesseract` (French model).
4. **Normalize & validate** (`normalize.py`, `pipeline._validate`) — French
   number formats, ticker aliasing (`ticker_map.py`), plausibility checks.
   Low-confidence OCR records are flagged to a manual review log instead of
   silently stored.
5. **Store & serve** (`storage.py`) — a local, versioned Parquet/CSV dataset
   under `$PYBVMAC_HOME` (defaults to `~/.pybvmac`), read by `Ticker` and the
   module-level functions.

A scheduled GitHub Actions workflow (`.github/workflows/daily_update.yml`)
runs `pybvmac refresh` after market close on trading days.

## Real bulletin layout

`real_layout.py` is calibrated against a genuine BOC bulletin
(`tests/fixtures/BOC-20260916.pdf`, N°2596 du 16/09/2026 — a regression
test, `tests/test_real_layout.py`, pins its output). Two things about real
bulletins weren't obvious from the cahier des charges alone:

- **The ticker BVMAC itself uses is the "Mnemo" column** (e.g. `SOCAP` for
  SOCAPALM, `ECMR6` for a 2029 Cameroon government bond), not the longer
  display name. `pybvmac`'s stored `ticker` field is always the Mnemo;
  `ticker_map.py` resolves friendlier aliases (`"SOCAPALM"`) to it.
- **The PDF export defeats naive table extraction.** Row/column
  separators are drawn as tiny filled shapes rather than stroked lines,
  and wrapped company-name cells interleave with neighbouring columns
  under plain text extraction. `grid.py` reconstructs the table grid from
  the page's vector geometry instead (see its module docstring), and
  `real_layout.py` classifies rows structurally (by column count and a
  valid date in the expected slot) rather than by parsing the — also
  visually garbled — multi-row header text.

If BVMAC changes the export template, `test_real_layout.py` is the test
that will catch it; `real_layout.py`'s docstring explains what to
recalibrate.

## Known limitations / open items for contributors

- **Bond static fields** (`coupon_rate`, `maturity_date`,
  `outstanding_amount`) are in the schema but not yet populated — they live
  on a *different* BOC table ("...LIGNES OBLIGATAIRES", the encours/outstanding-debt table) that `real_layout.py` doesn't parse yet.
- **Per-instrument market cap** — the "CAPITALISATION BOURSIERE" page also
  has a per-equity breakdown (Flottante/Globale); only the bulletin-wide
  total is stored today (`pybvmac.market_cap()`).
- **All Share Index history chart** — the bulletin plots a week of
  BVMAC-AS history as an image; only the current day's level and change
  are extractable text, not the chart's underlying series.
- **OCR-to-table reconstruction** in `ocr.py` — for scanned historical
  bulletins, currently a simple whitespace-column heuristic; the real
  bulletins are digital PDFs (this project's OCR path is for pre-digital
  archive scans, not yet sampled).
- **Archive pagination fallback** — section 6.2's headless-browser fallback
  (for if the WordPress REST API becomes unavailable) is intentionally not
  implemented yet, to avoid a Selenium/Playwright dependency until it's
  actually needed.
- **Ticker map coverage** (`src/pybvmac/data/ticker_map.csv`) — seeded with
  the 7 equities seen in the calibration bulletin; extend it as new
  tickers are observed (bonds don't need an entry — `pybvmac.Bond(...)`/
  `bonds()` are queried directly by Mnemo, no alias resolution).

## Development

```bash
git clone https://github.com/song-richard/pybvmac
cd pybvmac
pip install -e ".[dev,ocr,parquet]"
pytest
```

## License

MIT — see `LICENSE`. Please use PyBVMAC responsibly: it respects
`robots.txt`, rate-limits requests, and identifies itself with a descriptive
User-Agent when talking to bvm-ac.org.
