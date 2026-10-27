"""Regression test against a genuine BOC bulletin (N°2596, 16/09/2026).

This fixture is what real_layout.py was calibrated against — see that
module's docstring. If BVMAC changes the export template, this test is the
one that will fail first.
"""
import datetime as dt
from pathlib import Path

import pdfplumber
import pytest

from pybvmac.real_layout import parse_bulletin

FIXTURE = Path(__file__).parent / "fixtures" / "BOC-20260916.pdf"
BULLETIN_DATE = dt.date(2026, 9, 16)

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="calibration fixture not present")


@pytest.fixture(scope="module")
def parsed():
    with pdfplumber.open(FIXTURE) as pdf:
        return parse_bulletin(pdf, BULLETIN_DATE, FIXTURE.name)


def test_equity_count(parsed):
    equities, _, _, _ = parsed
    assert len(equities) == 7


def test_equity_tickers_are_mnemos(parsed):
    equities, _, _, _ = parsed
    tickers = {r["ticker"] for r in equities}
    assert tickers == {"SEMC", "SAF", "SOCAP", "REG", "BANGE", "SCGRE", "BHC"}


def test_equity_close_prices(parsed):
    equities, _, _, _ = parsed
    by_ticker = {r["ticker"]: r for r in equities}
    assert by_ticker["SOCAP"]["close_price"] == 50000.0
    assert by_ticker["SOCAP"]["volume"] == 6
    assert by_ticker["SOCAP"]["value_fcfa"] == 300000.0
    assert by_ticker["BHC"]["close_price"] == 93051.0
    assert by_ticker["BHC"]["volume"] == 28
    assert by_ticker["BHC"]["value_fcfa"] == 2605428.0
    # untraded that day (Statut "NC") -> zero volume, price unchanged
    assert by_ticker["SEMC"]["volume"] == 0
    assert by_ticker["SEMC"]["close_price"] == 53000.0


def test_bond_count(parsed):
    _, bonds, _, _ = parsed
    # 20 Etats + 6 Regionales (BDEAC) + 5 Privees = 31 lines
    assert len(bonds) == 31


def test_bond_sample(parsed):
    _, bonds, _, _ = parsed
    by_ticker = {r["ticker"]: r for r in bonds}
    assert by_ticker["ECMR6"]["close_price"] == 100.0
    assert by_ticker["EBD04"]["close_price"] == 100.0  # BDEAC regional bond
    assert by_ticker["AFC03"]["close_price"] == 100.0  # Alios Finance private bond


def test_market_cap(parsed):
    _, _, market_cap, _ = parsed
    assert market_cap is not None
    assert market_cap["market_cap_fcfa"] == 1851577990435.0
    assert market_cap["date"] == BULLETIN_DATE


def test_all_share_index(parsed):
    _, _, _, index = parsed
    assert index is not None
    assert index["index_value"] == 1162.39
    assert index["change_pct"] == 0.0
    assert index["date"] == BULLETIN_DATE
