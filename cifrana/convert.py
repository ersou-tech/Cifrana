"""Baixar e converter uma cifra — o caminho comum entre o terminal e a interface."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .chordpro import song_to_chordpro
from .chords import transpose_key
from .exporter import DEFAULT_EXT, build_filename
from .fetcher import Fetcher
from .model import Song
from .parser import parse_print_page
from .urls import print_url


@dataclass
class Options:
    """As escolhas do usuário sobre como converter e nomear a cifra."""

    transpose: int = 0
    chorus: bool = False
    tabs: bool = True
    source: bool = True
    name_template: str = "{artist} - {title}"
    ext: str = DEFAULT_EXT
    ascii_only: bool = False


@dataclass
class Converted:
    """O resultado pronto para gravar."""

    song: Song
    content: str
    filename: str


def render(song: Song, options: Options) -> Converted:
    """Converte um :class:`Song` já baixado, sem tocar na rede."""

    content = song_to_chordpro(
        song,
        transpose=options.transpose,
        chorus_directives=options.chorus,
        keep_tabs=options.tabs,
        source=options.source,
    )

    nomeado = song
    if options.transpose:
        # o nome do arquivo deve refletir o tom realmente exportado
        nomeado = replace(song, key=transpose_key(song.key, options.transpose))

    filename = build_filename(nomeado, options.name_template, options.ext, options.ascii_only)
    return Converted(song, content, filename)


def fetch_and_render(url: str, fetcher: Fetcher, options: Options) -> Converted:
    """Baixa a cifra de ``url`` e a converte para ChordPro."""

    page = fetcher.get(print_url(url))
    return render(parse_print_page(page, url=url), options)
