"""Normalização de URLs do CifraClub."""

from __future__ import annotations

import re
from urllib.parse import urlparse

BASE = "https://www.cifraclub.com.br"

# Segmentos que aparecem depois de /artista/musica/ e que não fazem parte do slug.
_TAIL_SEGMENTS = {
    "imprimir.html",
    "simplificada.html",
    "letra",
    "letras",
    "escutar",
    "video",
    "videoaula",
    "tab",
    "teclado",
    "baixo",
    "violao",
    "cavaco",
    "harmonica",
}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


class InvalidURL(ValueError):
    """URL que não aponta para uma cifra do CifraClub."""


def split_song(url: str) -> tuple[str, str]:
    """Devolve ``(artista, musica)`` a partir de uma URL ou de ``artista/musica``."""

    raw = (url or "").strip()
    if not raw:
        raise InvalidURL("URL vazia")

    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        if "cifraclub" not in host:
            raise InvalidURL(f"não é uma URL do CifraClub: {raw}")
        path = parsed.path
    else:
        path = raw

    parts = [p for p in path.split("/") if p and p not in _TAIL_SEGMENTS]
    if len(parts) < 2:
        raise InvalidURL(
            f"não consegui identificar artista/musica em: {raw!r} "
            "(esperado algo como https://www.cifraclub.com.br/artista/musica/)"
        )

    artist, song = parts[0], parts[1]
    if not _SLUG_RE.match(artist) or not _SLUG_RE.match(song):
        raise InvalidURL(f"caminho inesperado em: {raw!r}")
    return artist, song


def print_url(url: str) -> str:
    """URL da versão para impressão, que traz a cifra em HTML puro."""

    artist, song = split_song(url)
    return f"{BASE}/{artist}/{song}/imprimir.html"


def song_url(url: str) -> str:
    artist, song = split_song(url)
    return f"{BASE}/{artist}/{song}/"


def artist_slug(url: str) -> str:
    """Devolve o slug do artista a partir de uma URL de artista ou de música."""

    raw = (url or "").strip()
    path = urlparse(raw).path if "://" in raw else raw
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise InvalidURL(f"não consegui identificar o artista em: {raw!r}")
    slug = parts[0]
    if not _SLUG_RE.match(slug):
        raise InvalidURL(f"slug de artista inválido: {slug!r}")
    return slug


def artist_url(url: str) -> str:
    return f"{BASE}/{artist_slug(url)}/"
