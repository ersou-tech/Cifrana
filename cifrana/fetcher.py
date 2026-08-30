"""Download das páginas do CifraClub, com cache em disco e retentativas."""

from __future__ import annotations

import gzip
import hashlib
import logging
import random
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


class FetchError(RuntimeError):
    """Falha ao baixar uma página."""


def _decode(raw: bytes, encoding_header: str, charset: str | None) -> str:
    if encoding_header == "gzip":
        raw = gzip.decompress(raw)
    elif encoding_header == "deflate":
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode(charset or "utf-8", errors="replace")


class Fetcher:
    """Busca HTML com cache opcional, espera entre requisições e retentativas."""

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        delay: float = 1.0,
        timeout: float = 30.0,
        retries: int = 4,
        refresh: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.retries = max(1, retries)
        self.refresh = refresh
        self._last_request = 0.0

    # -- cache ---------------------------------------------------------
    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{digest}.html"

    def _read_cache(self, url: str) -> str | None:
        path = self._cache_path(url)
        if path and not self.refresh and path.is_file():
            log.debug("cache: %s", url)
            return path.read_text(encoding="utf-8")
        return None

    def _write_cache(self, url: str, body: str) -> None:
        path = self._cache_path(url)
        if path:
            path.write_text(body, encoding="utf-8")

    # -- rede ----------------------------------------------------------
    def _throttle(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, url: str) -> str:
        cached = self._read_cache(url)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            request = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    charset = response.headers.get_content_charset()
                    encoding = (response.headers.get("Content-Encoding") or "").lower()
                self._last_request = time.monotonic()
                body = _decode(raw, encoding, charset)
                self._write_cache(url, body)
                return body
            except urllib.error.HTTPError as exc:
                self._last_request = time.monotonic()
                if exc.code in (404, 410):
                    raise FetchError(f"página não encontrada (HTTP {exc.code}): {url}") from exc
                last_error = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._last_request = time.monotonic()
                last_error = exc

            if attempt < self.retries:
                wait = min(2**attempt, 16) + random.uniform(0, 0.5)
                log.warning(
                    "falha ao baixar %s (tentativa %d/%d): %s — nova tentativa em %.1fs",
                    url,
                    attempt,
                    self.retries,
                    last_error,
                    wait,
                )
                time.sleep(wait)

        raise FetchError(f"não consegui baixar {url}: {last_error}")
