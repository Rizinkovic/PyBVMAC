import datetime as dt
import logging

import pytest

from pybvmac import real_layout


class FakePage:
    def __init__(self, label, text):
        self.label = label
        self._text = text

    def extract_text(self):
        return self._text


class FakePdf:
    def __init__(self, pages):
        self.pages = pages


def test_parser_stops_at_spaced_commentary_heading_and_reports_counts(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    pages = [
        FakePage("index", "ALL SHARE INDEX"),
        FakePage("equities", "MARCHE DES ACTIONS"),
        FakePage("bonds", "MARCHE DES OBLIGATIONS"),
        FakePage("bond-continuation-1", "OBLIGATIONS DES ETATS"),
        FakePage("bond-continuation-2", ""),
        FakePage("bond-continuation-3", "O B L IG A T IO N S R E G IO N A L E S"),
        FakePage("commentary", "COMMENTAIR ES DU BULLETIN OFFICIEL DE LA COTE"),
        FakePage("notice-after-commentary", "AVIS AU PUBLIC"),
        FakePage("profile", "PROFIL DE LA SOCIETE"),
    ]
    grid_pages = []
    monkeypatch.setattr(
        real_layout,
        "extract_grid",
        lambda page: grid_pages.append(page.label) or [],
    )

    result = real_layout.parse_bulletin(
        FakePdf(pages), dt.date(2026, 3, 19), "BOC-20260319.pdf"
    )

    assert result == ([], [], None, None)
    assert grid_pages == [
        "index",
        "equities",
        "bonds",
        "bond-continuation-1",
        "bond-continuation-2",
        "bond-continuation-3",
    ]
    assert "Real-layout parser visited 7/9 pages and extracted grids from 6 for BOC-20260319.pdf" in caplog.text



@pytest.mark.parametrize(
    "heading",
    [
        "COMMENTAIR ES DU BULLETIN OFFICIEL DE LA COTE",
        "C O M M E N T A I R E S D U B U L L E T I N O F F I C I E L D E L A C O T E",
        "COMMENTAIRES DU BULLETIN OFFICIEL DE LA COTÉ",
    ],
)
def test_heading_normalization_handles_spacing_and_accents(heading):
    assert real_layout._compact_heading(heading) == "COMMENTAIRESDUBULLETINOFFICIELDELACOTE"



def test_extracted_instrument_name_preserves_spaces_between_words():
    row = [""] * real_layout.EQUITY_NCOLS
    row[real_layout.EQUITY_COLUMNS["mnemo"]] = "S C E"
    row[real_layout.EQUITY_COLUMNS["name"]] = "SOCIETE CAMEROUNAISE DES EAUX"
    row[real_layout.EQUITY_COLUMNS["close_price"]] = "1 234"
    row[real_layout.EQUITY_COLUMNS["change_pct"]] = "2,5"
    row[real_layout.EQUITY_COLUMNS["volume"]] = "10"
    row[real_layout.EQUITY_COLUMNS["value_fcfa"]] = "12 340"

    record = real_layout._build_record(
        row, real_layout.EQUITY_COLUMNS, dt.date(2026, 1, 2), "BOC-20260102.pdf"
    )

    assert record["ticker"] == "SCE"
    assert record["name"] == "SOCIETE CAMEROUNAISE DES EAUX"
