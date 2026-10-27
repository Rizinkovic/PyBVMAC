from __future__ import annotations

import datetime as dt

import pytest
import requests

from pybvmac.exceptions import FetchError
from pybvmac.fetch import BulletinRef, discover_bulletins, download_bulletin


class FakeResponse:
    def __init__(self, content: bytes = b"", items=None, status_code: int = 200):
        self.content = content
        self._items = items
        self.status_code = status_code

    def json(self):
        return self._items


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_download_rejects_non_pdf_and_does_not_cache_it(tmp_path):
    session = FakeSession([FakeResponse(b"<html>temporary server error</html>")])
    bulletin = BulletinRef(
        url="https://example.test/boc.pdf",
        filename="boc.pdf",
        date=dt.date(2025, 1, 2),
    )

    with pytest.raises(FetchError, match="not a valid PDF"):
        download_bulletin(session, bulletin, tmp_path)

    assert not (tmp_path / "boc.pdf").exists()
    assert not (tmp_path / "boc.pdf.part").exists()


def test_download_atomically_caches_pdf_and_reuses_valid_cache(tmp_path):
    session = FakeSession([FakeResponse(b"%PDF-1.7\nvalid enough for header check")])
    bulletin = BulletinRef(
        url="https://example.test/boc.pdf",
        filename="boc.pdf",
        date=dt.date(2025, 1, 2),
    )

    path = download_bulletin(session, bulletin, tmp_path)
    assert path.read_bytes().startswith(b"%PDF-")
    assert session.calls == 1

    second_path = download_bulletin(session, bulletin, tmp_path)
    assert second_path == path
    assert session.calls == 1


def test_download_replaces_corrupt_cached_file(tmp_path):
    cached = tmp_path / "boc.pdf"
    cached.write_bytes(b"not a pdf")
    session = FakeSession([FakeResponse(b"%PDF-1.7\nvalid replacement")])
    bulletin = BulletinRef(
        url="https://example.test/boc.pdf",
        filename="boc.pdf",
        date=dt.date(2025, 1, 2),
    )

    path = download_bulletin(session, bulletin, tmp_path)
    assert path.read_bytes().startswith(b"%PDF-")
    assert session.calls == 1


def test_discovery_does_not_silently_accept_partial_archive():
    first_page = FakeResponse(
        items=[
            {
                "source_url": "https://example.test/BOC-02-01-2025.pdf",
            }
        ]
    )
    session = FakeSession([first_page, requests.Timeout("temporary timeout")])

    with pytest.raises(FetchError, match="results may be incomplete"):
        discover_bulletins(session, per_page=1, max_pages=3)


def test_discovery_stops_on_wordpress_end_of_pagination():
    first_page = FakeResponse(items=[])
    session = FakeSession([first_page])

    assert discover_bulletins(session, max_pages=3) == []
    assert session.calls == 1
