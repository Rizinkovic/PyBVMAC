import datetime as dt

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
