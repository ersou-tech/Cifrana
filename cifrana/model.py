"""Estruturas de dados usadas entre o parser e os exportadores."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChordAt:
    """Um acorde e a coluna (0-based) onde ele começa na linha."""

    col: int
    name: str
    text: str = ""

    def __post_init__(self) -> None:
        if not self.text:
            self.text = self.name

    @property
    def end(self) -> int:
        return self.col + len(self.text)


@dataclass
class RawLine:
    """Uma linha da cifra, com o texto exatamente como aparece na página.

    ``text`` já inclui os caracteres dos acordes (a cifra do CifraClub é
    monoespaçada, então as colunas de ``chords`` apontam para dentro de
    ``text``).
    """

    text: str
    chords: list[ChordAt] = field(default_factory=list)


@dataclass
class Song:
    """Uma cifra completa."""

    title: str = ""
    artist: str = ""
    composer: str = ""
    key: str = ""
    tuning: str = ""
    capo: int | None = None
    tempo: int | None = None
    rhythm: str = ""
    url: str = ""
    lines: list[RawLine] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or self.artist or "cifra"
