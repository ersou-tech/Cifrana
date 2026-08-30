"""Conversão da cifra do CifraClub para ChordPro (formato lido pelo SongbookPro).

O CifraClub usa acordes em uma linha acima da letra. O SongbookPro (como todo
leitor ChordPro) espera acordes embutidos entre colchetes na própria linha da
letra. A conversão é posicional: cada acorde é inserido na coluna em que estava
na linha de cima.
"""

from __future__ import annotations

import re

from .chords import prefer_flats_for, transpose_chord, transpose_key
from .model import ChordAt, RawLine, Song

BLANK = "blank"
SECTION = "section"
SECTION_CHORDS = "section+chords"
TAB = "tab"
CHORDS = "chords"
LYRICS = "lyrics"

_SECTION_RE = re.compile(r"^\[([^\[\]]{1,80})\]$")
_LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_TAB_RE = re.compile(r"^\s*[A-Ga-g]?[#b]?\s*\|[-\d\s|hpbvrstx~/\\()\[\].*+^]*$")
# marcadores de repetição que podem sobrar numa linha só de acordes
_REPEAT_TOKENS_RE = re.compile(r"\(?\s*\d+\s*[xX]\s*\)?|[|:.\-,;/()%\s\d]")

_CHORUS_WORDS = ("refrão", "refrao", "chorus", "estribilho")


def residual_text(line: RawLine) -> str:
    """Texto da linha com os acordes apagados (vira espaço em branco)."""

    chars = list(line.text)
    for chord in line.chords:
        for index in range(chord.col, min(chord.end, len(chars))):
            chars[index] = " "
    return "".join(chars)


def _is_tab_line(residual: str) -> bool:
    stripped = residual.strip()
    if "|" not in stripped or stripped.count("-") < 3:
        return False
    return bool(_TAB_RE.match(residual))


def classify(line: RawLine) -> str:
    residual = residual_text(line)
    stripped = residual.strip()

    if not stripped and not line.chords:
        return BLANK
    if _SECTION_RE.match(stripped):
        return SECTION_CHORDS if line.chords else SECTION
    if _is_tab_line(residual):
        return TAB
    if line.chords and not _LETTER_RE.search(_REPEAT_TOKENS_RE.sub("", residual)):
        return CHORDS
    if not stripped:
        return BLANK
    return LYRICS


def _section_label(line: RawLine) -> str:
    match = _SECTION_RE.match(residual_text(line).strip())
    return match.group(1).strip() if match else ""


def _sanitize_lyric(text: str) -> str:
    """Colchetes soltos na letra viriam a ser acordes; viram parênteses."""

    return text.replace("[", "(").replace("]", ")")


def _chord_name(chord: ChordAt, semitones: int, prefer_flats: bool) -> str:
    return transpose_chord(chord.name, semitones, prefer_flats) if semitones else chord.name


def _inline_chords(line: RawLine, semitones: int, prefer_flats: bool) -> str:
    """Substitui, na própria linha, o texto de cada acorde por ``[Acorde]``."""

    out = _sanitize_lyric(line.text)
    for chord in sorted(line.chords, key=lambda c: c.col, reverse=True):
        name = _chord_name(chord, semitones, prefer_flats)
        end = min(chord.end, len(out))
        out = out[: chord.col] + f"[{name}]" + out[end:]
    return out.rstrip()


def _merge(chord_line: RawLine, lyric_line: RawLine, semitones: int, prefer_flats: bool) -> str:
    """Insere os acordes da linha de cima nas colunas da linha de letra."""

    out = _sanitize_lyric(lyric_line.text.rstrip())
    for chord in sorted(chord_line.chords, key=lambda c: c.col, reverse=True):
        name = _chord_name(chord, semitones, prefer_flats)
        col = chord.col
        if col > len(out):
            out = out + " " * (col - len(out))
        out = out[:col] + f"[{name}]" + out[col:]
    return out.rstrip()


def _next_kind(kinds: list[str], index: int, skip: set[str]) -> str | None:
    for kind in kinds[index:]:
        if kind not in skip:
            return kind
    return None


def _tab_blocks(kinds: list[str]) -> set[int]:
    """Índices que fazem parte de um bloco de tablatura."""

    in_block: set[int] = set()
    total = len(kinds)
    for index, kind in enumerate(kinds):
        if kind != TAB or index in in_block:
            continue

        start = index
        while start - 1 >= 0 and kinds[start - 1] in (CHORDS, TAB):
            start -= 1

        end = index
        while end + 1 < total:
            following = kinds[end + 1]
            if following == TAB:
                end += 1
                continue
            if following in (CHORDS, BLANK) and _next_kind(
                kinds, end + 2, {BLANK, CHORDS}
            ) == TAB:
                end += 1
                continue
            break

        in_block.update(range(start, end + 1))
    return in_block


def _directive(name: str, value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return f"{{{name}: {text}}}" if text else None


def header_lines(song: Song, semitones: int = 0, source: bool = True) -> list[str]:
    key = transpose_key(song.key, semitones) if semitones else song.key
    candidates = [
        _directive("title", song.title),
        _directive("artist", song.artist),
        _directive("composer", song.composer),
        _directive("key", key),
        _directive("capo", song.capo),
        _directive("tempo", song.tempo),
    ]
    if song.tuning and song.tuning.replace(" ", "").upper() != "EADGBE":
        candidates.append(_directive("comment", f"Afinação: {song.tuning}"))
    if song.rhythm:
        candidates.append(_directive("comment", song.rhythm))
    if semitones:
        original = song.key or "?"
        candidates.append(
            _directive("comment", f"Transposto {semitones:+d} semitom(ns) do tom original {original}")
        )
    if source and song.url:
        candidates.append(_directive("comment", f"Fonte: {song.url}"))
    return [line for line in candidates if line]


def song_to_chordpro(
    song: Song,
    *,
    transpose: int = 0,
    chorus_directives: bool = False,
    keep_tabs: bool = True,
    source: bool = True,
) -> str:
    """Renderiza a cifra como texto ChordPro."""

    semitones = transpose % 12
    prefer_flats = prefer_flats_for(song.key, semitones) if semitones else False

    lines = song.lines
    kinds = [classify(line) for line in lines]
    tab_indices = _tab_blocks(kinds)

    out: list[str] = header_lines(song, semitones, source)
    if out:
        out.append("")

    in_tab = False
    in_chorus = False
    index = 0
    total = len(lines)

    while index < total:
        line, kind = lines[index], kinds[index]

        # --- tablaturas: vão literais, para não perder o alinhamento ---
        if index in tab_indices:
            if not keep_tabs:
                while index in tab_indices:
                    index += 1
                continue
            if not in_tab:
                if in_chorus:
                    out.append("{end_of_chorus}")
                    in_chorus = False
                out.append("{start_of_tab}")
                in_tab = True
            out.append(line.text.rstrip())
            index += 1
            if index not in tab_indices:
                out.append("{end_of_tab}")
                in_tab = False
            continue

        if in_tab:
            out.append("{end_of_tab}")
            in_tab = False

        # --- cabeçalhos de seção ---------------------------------------
        if kind in (SECTION, SECTION_CHORDS):
            label = _section_label(line)
            is_chorus = any(word in label.lower() for word in _CHORUS_WORDS)
            if in_chorus:
                out.append("{end_of_chorus}")
                in_chorus = False
            if chorus_directives and is_chorus:
                out.append(f"{{start_of_chorus: {label}}}")
                in_chorus = True
            else:
                out.append(f"{{comment: {label}}}")
            if kind == SECTION_CHORDS:
                chords_only = RawLine(" " * len(line.text), line.chords)
                out.append(_inline_chords(chords_only, semitones, prefer_flats))
            index += 1
            continue

        # --- linha só de acordes ---------------------------------------
        if kind == CHORDS:
            following = kinds[index + 1] if index + 1 < total else None
            if following == LYRICS and (index + 1) not in tab_indices and not lines[index + 1].chords:
                out.append(_merge(line, lines[index + 1], semitones, prefer_flats))
                index += 2
                continue
            out.append(_inline_chords(line, semitones, prefer_flats))
            index += 1
            continue

        # --- letra (com ou sem acordes embutidos) -----------------------
        if kind == LYRICS:
            out.append(_inline_chords(line, semitones, prefer_flats))
            index += 1
            continue

        # --- linha em branco -------------------------------------------
        if in_chorus:
            following = _next_kind(kinds[index:], 0, {BLANK})
            if following is None:
                out.append("{end_of_chorus}")
                in_chorus = False
        out.append("")
        index += 1

    if in_tab:
        out.append("{end_of_tab}")
    if in_chorus:
        out.append("{end_of_chorus}")

    # colapsa linhas em branco repetidas e remove sobras no fim
    cleaned: list[str] = []
    for entry in out:
        if not entry and cleaned and not cleaned[-1]:
            continue
        cleaned.append(entry)
    while cleaned and not cleaned[-1]:
        cleaned.pop()

    return "\n".join(cleaned) + "\n"
