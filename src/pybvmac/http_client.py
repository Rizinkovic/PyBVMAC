"""A small, polite HTTP client.

Wraps requests.Session with three things the cahier des charges asks for
explicitly (NFR "Legal and ethical compliance"):

1. A descriptive User-Agent that identifies the project and states it is
   independent / unofficial.
2. A minimum delay enforced between requests (simple client-side rate limit).
3. A robots.txt check before fetching a URL.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

logger = logging.getLogger("pybvmac.http_client")


class PoliteSession:
    """requests.Session wrapper enforcing rate limiting and robots.txt."""

    def __init__(
        self,
        user_agent: str = config.USER_AGENT,
        min_interval: float = config.MIN_REQUEST_INTERVAL_SECONDS,
        timeout: int = config.REQUEST_TIMEOUT_SECONDS,
        respect_robots: bool = True,
    ):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.min_interval = min_interval
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._last_request_ts: float = 0.0
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    # -- politeness helpers -------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()

    def _robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots_cache.get(origin)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            started = time.perf_counter()
            try:
                # RobotFileParser.read() has no convenient per-call timeout.
                # Fetch explicitly so an unreachable robots.txt cannot stall
                # a backfill indefinitely on a weak connection.
                response = self.session.get(
                    f"{origin}/robots.txt",
                    timeout=min(self.timeout, 10),
                )
                response.raise_for_status()
                parser.parse(response.text.splitlines())
                logger.info(
                    "robots.txt fetched for %s in %.2fs",
                    origin, time.perf_counter() - started,
                )
            except (OSError, requests.RequestException) as exc:
                logger.warning(
                    "Could not fetch robots.txt for %s after %.2fs (%s); continuing conservatively",
                    origin, time.perf_counter() - started, exc,
                )
                parser = None
            self._robots_cache[origin] = parser
        if parser is None:
            return True
        return parser.can_fetch(self.session.headers["User-Agent"], url)

    # -- public API -----------------------------------------------------
    def get(self, url: str, **kwargs) -> requests.Response:
        if not self._robots_allows(url):
            raise PermissionError(f"robots.txt disallows fetching: {url}")
        self._throttle()
        kwargs.setdefault("timeout", self.timeout)
        started = time.perf_counter()
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
        except Exception:
            logger.warning("HTTP GET %s failed after %.2fs", urlparse(url).path, time.perf_counter() - started)
            raise
        logger.info(
            "HTTP GET %s completed in %.2fs (status %s)",
            urlparse(url).path, time.perf_counter() - started, response.status_code,
        )
        return response

    def head(self, url: str, **kwargs) -> requests.Response:
        if not self._robots_allows(url):
            raise PermissionError(f"robots.txt disallows fetching: {url}")
        self._throttle()
        kwargs.setdefault("timeout", self.timeout)
        started = time.perf_counter()
        try:
            response = self.session.head(url, **kwargs)
            response.raise_for_status()
        except Exception:
            logger.warning("HTTP HEAD %s failed after %.2fs", urlparse(url).path, time.perf_counter() - started)
            raise
        logger.info(
            "HTTP HEAD %s completed in %.2fs (status %s)",
            urlparse(url).path, time.perf_counter() - started, response.status_code,
        )
        return response
