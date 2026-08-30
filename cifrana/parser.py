"""Parser da página de impressão do CifraClub.

A página ``/artista/musica/imprimir.html`` entrega a cifra em HTML puro: um
``<pre>`` por página A4, com cada acorde dentro de um ``<b data-chord-name=...>``.
Como o bloco é monoespaçado, a coluna de cada acorde no texto corresponde
exatamente à posição em que ele deve aparecer sobre a letra.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from .model import ChordAt, RawLine, Song

_CAPTURE_TAGS = {"h1", "h2", "h3", "small", "button", "p", "title"}


class _PrintPageParser(HTMLParser):
    """Extrai os blocos ``<pre>`` (com posições de acorde) e os metadados."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pages: list[list[RawLine]] = []
        self.captures: list[tuple[str, dict[str, str], str]] = []

        self._pre_depth = 0
        self._lines: list[RawLine] = []
        self._buf: list[str] = []
        self._chords: list[ChordAt] = []

        self._chord_col: int | None = None
        self._chord_name = ""
        self._chord_text: list[str] = []

        self._cap_stack: list[tuple[str, dict[str, str], list[str]]] = []

    # -- linhas do <pre> ----------------------------------------------
    def _flush_line(self) -> None:
        self._lines.append(RawLine("".join(self._buf), self._chords))
        self._buf = []
        self._chords = []

    # -- HTMLParser ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k: (v or "") for k, v in attrs}

        if tag == "pre":
            self._pre_depth += 1
            if self._pre_depth == 1:
                self._lines = []
                self._buf = []
                self._chords = []
            return

        if self._pre_depth and tag == "b":
            self._chord_col = len("".join(self._buf))
            self._chord_name = attributes.get("data-chord-name", "").strip()
            self._chord_text = []
            return

        if tag in _CAPTURE_TAGS:
            self._cap_stack.append((tag, attributes, []))

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
            if self._pre_depth == 0:
                if self._buf or self._chords:
                    self._flush_line()
                self.pages.append(self._lines)
                self._lines = []
            return

        if self._pre_depth and tag == "b" and self._chord_col is not None:
            text = "".join(self._chord_text)
            name = self._chord_name or text.strip()
            if name:
                self._chords.append(ChordAt(self._chord_col, name, text or name))
            self._chord_col = None
            self._chord_text = []
            return

        if tag in _CAPTURE_TAGS:
            for index in range(len(self._cap_stack) - 1, -1, -1):
                if self._cap_stack[index][0] == tag:
                    name, attributes, chunks = self._cap_stack.pop(index)
                    self.captures.append((name, attributes, "".join(chunks)))
                    break

    def handle_data(self, data: str) -> None:
        if self._pre_depth:
            pieces = data.split("\n")
            for index, piece in enumerate(pieces):
                if index:
                    self._flush_line()
                    # um acorde nunca atravessa quebra de linha, mas se
                    # acontecer preservamos a coluna reiniciada
                    if self._chord_col is not None:
                        self._chord_col = 0
                if piece:
                    self._buf.append(piece)
                    if self._chord_col is not None:
                        self._chord_text.append(piece)
            return

        for _tag, _attrs, chunks in self._cap_stack:
            chunks.append(data)


def _first_capture(
    captures: list[tuple[str, dict[str, str], str]],
    tag: str | None = None,
    *,
    attr: str | None = None,
    value: str | None = None,
    contains: str | None = None,
) -> str:
    for name, attributes, text in captures:
        if tag and name != tag:
            continue
        if attr is not None and attributes.get(attr) != value:
            continue
        if contains and contains.lower() not in text.lower():
            continue
        cleaned = re.sub(r"\s+", " ", text).strip()
        if cleaned:
            return cleaned
    return ""


def _capo_from_captures(captures: list[tuple[str, dict[str, str], str]]) -> int | None:
    for name, attributes, text in captures:
        is_capo_button = name == "button" and attributes.get("id") == "capo"
        is_capo_anchor = attributes.get("data-anchor") == "--capo"
        if not (is_capo_button or is_capo_anchor):
            continue
        cleaned = re.sub(r"\s+", " ", text).strip()
        if re.search(r"sem\s+capotraste", cleaned, re.IGNORECASE):
            return None
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
    return None


def _tempo_from_captures(captures: list[tuple[str, dict[str, str], str]]) -> int | None:
    for name, _attrs, text in captures:
        if name != "p":
            continue
        match = re.search(r"(\d{2,3})\s*bpm", re.sub(r"\s+", " ", text), re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _rhythm_from_captures(captures: list[tuple[str, dict[str, str], str]]) -> str:
    for name, _attrs, text in captures:
        if name != "p":
            continue
        cleaned = re.sub(r"\s+", " ", text).strip()
        match = re.match(r"^\[(.+)\]$", cleaned)
        if match and "ritmo" in match.group(1).lower():
            return match.group(1).strip()
    return ""


def _title_artist_from_title_tag(raw_title: str) -> tuple[str, str]:
    parts = [p.strip() for p in raw_title.split(" - ")]
    if parts and parts[-1].lower() in {"cifra club", "cifraclub"}:
        parts = parts[:-1]
    if len(parts) >= 2:
        return parts[0], " - ".join(parts[1:])
    if parts:
        return parts[0], ""
    return "", ""


def _trim_blank_edges(lines: list[RawLine]) -> list[RawLine]:
    start, end = 0, len(lines)
    while start < end and not lines[start].text.strip() and not lines[start].chords:
        start += 1
    while end > start and not lines[end - 1].text.strip() and not lines[end - 1].chords:
        end -= 1
    return lines[start:end]


class ParseError(RuntimeError):
    """A página não continha uma cifra reconhecível."""


def parse_print_page(page_html: str, url: str = "") -> Song:
    """Converte o HTML da página de impressão em um :class:`Song`."""

    parser = _PrintPageParser()
    parser.feed(page_html)
    parser.close()

    if not parser.pages:
        raise ParseError(
            "não encontrei o bloco da cifra nesta página "
            "(a música pode ser só vídeo-aula, PDF ou ter sido removida)"
        )

    lines: list[RawLine] = []
    for page in parser.pages:
        lines.extend(_trim_blank_edges(page))
        lines.append(RawLine(""))
    lines = _trim_blank_edges(lines)

    captures = parser.captures
    title = _first_capture(captures, "h1")
    artist = _first_capture(captures, "h2")
    if not title or not artist:
        raw_title = _first_capture(captures, "title") or _extract_title_tag(page_html)
        fallback_title, fallback_artist = _title_artist_from_title_tag(raw_title)
        title = title or fallback_title
        artist = artist or fallback_artist

    composer = _first_capture(captures, "small", contains="composi")
    composer = re.sub(r"^composi[çc][aã]o\s+de:?\s*", "", composer, flags=re.IGNORECASE)

    key = _first_capture(captures, "button", attr="data-anchor", value="--chord-tone")
    tuning = _first_capture(captures, "button", attr="data-anchor", value="--chord-tuning")

    return Song(
        title=title,
        artist=artist,
        composer=composer,
        key=key,
        tuning=tuning,
        capo=_capo_from_captures(captures),
        tempo=_tempo_from_captures(captures),
        rhythm=_rhythm_from_captures(captures),
        url=url,
        lines=lines,
    )


def _extract_title_tag(page_html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.S | re.I)
    return html.unescape(match.group(1)).strip() if match else ""


_SONG_LINK_RE = re.compile(r'href="/([a-z0-9][a-z0-9._-]*)/([a-z0-9][a-z0-9._-]*)/"')

_NOT_A_SONG = {
    "musicas",
    "discografia",
    "letras",
    "album",
    "albuns",
    "fotos",
    "videos",
    "aulas",
    "cifras",
    "top",
    "novidades",
    "playlist",
    "playlists",
    "artistas",
    "generos",
    "genero",
    "colecoes",
    "curso",
    "cursos",
    "academy",
    "podcast",
    "loja",
    "app",
    "sobre",
    "contato",
}


def parse_artist_page(page_html: str, slug: str) -> list[str]:
    """Lista as URLs de música encontradas na página de um artista."""

    found: list[str] = []
    seen: set[str] = set()
    for artist, song in _SONG_LINK_RE.findall(page_html):
        if artist != slug or song in _NOT_A_SONG or song in seen:
            continue
        seen.add(song)
        found.append(f"https://www.cifraclub.com.br/{artist}/{song}/")
    return found
