"""Low-level table extraction for BOC bulletins.

Why this exists
----------------
Real BOC bulletins (see the sample calibrated against:
BOC-20260916.pdf) are exported from a spreadsheet in a way that defeats
pdfplumber's default ``extract_tables()``: row/column separators are drawn
as tiny filled rectangles rather than stroked lines (pdfplumber files these
as "curves", not "lines"), and header/company-name cells wrap across many
sub-lines whose baselines interleave with neighbouring columns. Both defeat
plain ``page.extract_text()`` for the wide market tables.

The fix used here reconstructs the table grid directly from the page's
vector geometry (both ``lines`` and flat/thin ``curves``) and extracts each
cell's text individually via a tight crop, which sidesteps the
cross-column interleaving entirely. Numeric cells still come out with
stray spaces between digits (a font-metrics quirk of the export, e.g.
"5 3 0 0 0" for 53000) — ``normalize.parse_french_number`` already strips
all whitespace, so this is harmless for numbers. For short identifier
cells (tickers/Mnemo codes), use ``squeeze()`` below to remove the same
stray spacing.
"""
from __future__ import annotations


def _cluster(values: list[float], tol: float = 1.5) -> list[float]:
    """Merge nearly-identical coordinates (within ``tol`` points) into one."""
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def _row_boundaries(page, y0: float, y1: float) -> list[float]:
    """Horizontal (row) separator positions within [y0, y1]."""
    horiz: set[float] = set()
    for line in page.lines:
        if line["x0"] != line["x1"] and y0 - 2 <= line["top"] <= y1 + 2:
            horiz.add(line["top"])
    for curve in page.curves:
        width = curve["x1"] - curve["x0"]
        height = curve["bottom"] - curve["top"]
        if height < 2 and width > 3 and y0 - 2 <= curve["top"] <= y1 + 2:
            horiz.add(curve["top"])
    return _cluster(horiz) if horiz else []


def _col_boundaries(page, top: float, bottom: float) -> list[float]:
    """Vertical (column) separator positions overlapping row-band [top, bottom].

    Deliberately scoped to a single row band rather than the whole page:
    different tables sharing a page (e.g. "OBLIGATIONS REGIONALES" and
    "OBLIGATIONS PRIVEES" stacked on one page) use different column widths,
    so collecting columns globally would interleave two incompatible grids.
    """
    vert: set[float] = set()
    for line in page.lines:
        if line["x0"] == line["x1"] and line["top"] <= bottom and line["bottom"] >= top:
            vert.add(line["x0"])
    for curve in page.curves:
        width = curve["x1"] - curve["x0"]
        height = curve["bottom"] - curve["top"]
        if width < 2 and height > 3 and curve["top"] <= bottom and curve["bottom"] >= top:
            vert.add(curve["x0"])
    return _cluster(vert) if vert else []


def extract_grid(page, y0: float = 0, y1: float | None = None) -> list[list[str]]:
    """Reconstruct table row bands as a list of rows of cell text within
    [y0, y1]. Column boundaries are (re)computed independently for each row
    band, so multiple differently-shaped tables stacked on one page are each
    read with their own grid instead of a merged, misaligned one.

    Each cell's text is whitespace-normalized (runs of whitespace collapsed
    to a single space) but not de-spaced — see module docstring for why
    that's the caller's job for identifier columns.
    """
    y1 = page.height if y1 is None else y1
    horiz = _row_boundaries(page, y0, y1)
    rows: list[list[str]] = []
    for i in range(len(horiz) - 1):
        top, bottom = horiz[i], horiz[i + 1]
        vert = _col_boundaries(page, top, bottom)
        row = []
        for j in range(len(vert) - 1):
            left, right = vert[j], vert[j + 1]
            cell = page.within_bbox((left, top, right, bottom))
            text = cell.extract_text() or ""
            row.append(" ".join(text.split()))
        rows.append(row)
    return rows


def squeeze(text: str) -> str:
    """Remove ALL whitespace, for identifier cells (Mnemo/ticker codes)
    whose glyphs render with a stray space between every character in
    these bulletins. Never use this on free-text/company-name cells you
    need genuine word spaces in.
    """
    return "".join((text or "").split())
