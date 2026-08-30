"""Busca de músicas e artistas no CifraClub.

O site expõe um endpoint de autocomplete que devolve JSON embrulhado em uma
chamada de função (JSONP). É o mesmo que a caixa de busca do site usa.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass

from .fetcher import Fetcher

SEARCH_ENDPOINT = "https://solr.sscdn.co/cc/h2/"

# tipos devolvidos pelo endpoint
_TYPE_ARTIST = "1"
_TYPE_SONG = "2"

_JSONP_RE = re.compile(r"\(\s*(\{.*\})\s*\)\s*;?\s*$", re.S)


@dataclass(frozen=True)
class SearchResult:
    """Uma música ou um artista encontrado na busca."""

    kind: str  # "musica" ou "artista"
    title: str
    artist: str
    artist_slug: str
    song_slug: str = ""

    @property
    def is_song(self) -> bool:
        return self.kind == "musica"

    @property
    def url(self) -> str:
        base = f"https://www.cifraclub.com.br/{self.artist_slug}/"
        return f"{base}{self.song_slug}/" if self.song_slug else base

    @property
    def label(self) -> str:
        if self.is_song:
            return f"{self.title} — {self.artist}"
        return f"{self.title} (artista)"


class SearchError(RuntimeError):
    """Falha ao consultar a busca do CifraClub."""


def _parse_jsonp(body: str) -> dict:
    match = _JSONP_RE.search(body.strip())
    payload = match.group(1) if match else body.strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SearchError("resposta inesperada da busca do CifraClub") from exc


def parse_search_payload(body: str) -> list[SearchResult]:
    """Converte a resposta do endpoint em uma lista de resultados."""

    data = _parse_jsonp(body)
    docs = data.get("response", {}).get("docs", [])

    results: list[SearchResult] = []
    for doc in docs:
        artist_slug = (doc.get("d") or "").strip()
        if not artist_slug:
            continue
        kind = doc.get("t")
        name = (doc.get("m") or "").strip()
        artist = (doc.get("a") or "").strip()

        if kind == _TYPE_SONG:
            song_slug = (doc.get("u") or "").strip()
            if not song_slug:
                continue
            results.append(
                SearchResult("musica", name, artist or name, artist_slug, song_slug)
            )
        elif kind == _TYPE_ARTIST:
            results.append(SearchResult("artista", name or artist, artist or name, artist_slug))
    return results


def search(term: str, fetcher: Fetcher | None = None) -> list[SearchResult]:
    """Busca ``term`` no CifraClub e devolve músicas e artistas."""

    term = (term or "").strip()
    if not term:
        return []

    fetcher = fetcher or Fetcher(cache_dir=None, delay=0.0)
    url = SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"q": term})
    return parse_search_payload(fetcher.get(url))


def only_songs(results: list[SearchResult]) -> list[SearchResult]:
    return [r for r in results if r.is_song]


def only_artists(results: list[SearchResult]) -> list[SearchResult]:
    return [r for r in results if not r.is_song]
