import datetime as dt

import pytest

from pybvmac.normalize import (
    bulletin_filename_for_date,
    parse_boc_date_from_filename,
    parse_french_int,
    parse_french_number,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("12 345,67", 12345.67),
        ("1\u00a0234,5", 1234.5),
        ("+2,50%", 2.5),
        ("-1,20%", -1.2),
        ("100", 100.0),
        ("-", None),
        ("", None),
        (None, None),
        ("n/a", None),
    ],
)
def test_parse_french_number(raw, expected):
    assert parse_french_number(raw) == expected


def test_parse_french_int():
    assert parse_french_int("12 345") == 12345
    assert parse_french_int("-") is None


def test_parse_boc_date_new_pattern():
    assert parse_boc_date_from_filename("BOC-20260917.pdf") == dt.date(2026, 9, 17)


def test_parse_boc_date_old_pattern():
    assert parse_boc_date_from_filename("BOC-BVMAC-17-09-2022.pdf") == dt.date(
        2022, 9, 17
    )


def test_parse_boc_date_unrecognized():
    assert parse_boc_date_from_filename("communique-bvmac.pdf") is None


def test_bulletin_filename_roundtrip():
    date = dt.date(2026, 9, 17)
    filename = bulletin_filename_for_date(date)
    assert filename == "BOC-20260917.pdf"
    assert parse_boc_date_from_filename(filename) == date
