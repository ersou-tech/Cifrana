"""Reconhecimento e transposição de acordes (notação latina/americana)."""

from __future__ import annotations

import re

SHARP_SCALE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_SCALE = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

_PITCH = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4,
    "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
    "A#": 10, "Bb": 10, "B": 11, "Cb": 11, "B#": 0,
}

# raiz + acidente + sufixo (+ baixo opcional)
_CHORD_RE = re.compile(
    r"^(?P<root>[A-G])(?P<acc>[#b]?)(?P<suffix>[^/\s]*)"
    r"(?:/(?P<bass_root>[A-G])(?P<bass_acc>[#b]?))?$"
)


def is_chord(token: str) -> bool:
    return bool(_CHORD_RE.match(token.strip()))


def _render_pitch(pitch: int, prefer_flats: bool) -> str:
    scale = FLAT_SCALE if prefer_flats else SHARP_SCALE
    return scale[pitch % 12]


def _prefers_flats(key: str) -> bool:
    """Tonalidades que costumam ser escritas com bemol."""

    if not key:
        return False
    match = re.match(r"^([A-G])([#b]?)", key.strip())
    if not match:
        return False
    root, accidental = match.group(1), match.group(2)
    if accidental == "b":
        return True
    if accidental == "#":
        return False
    return root == "F"


def transpose_chord(chord: str, semitones: int, prefer_flats: bool = False) -> str:
    """Transpõe um acorde. Devolve o original se não for um acorde válido."""

    if semitones % 12 == 0:
        return chord
    match = _CHORD_RE.match(chord.strip())
    if not match:
        return chord

    root = match.group("root") + match.group("acc")
    pitch = _PITCH.get(root)
    if pitch is None:
        return chord
    out = _render_pitch(pitch + semitones, prefer_flats) + match.group("suffix")

    if match.group("bass_root"):
        bass = match.group("bass_root") + (match.group("bass_acc") or "")
        bass_pitch = _PITCH.get(bass)
        if bass_pitch is not None:
            out += "/" + _render_pitch(bass_pitch + semitones, prefer_flats)
        else:
            out += "/" + bass
    return out


def transpose_key(key: str, semitones: int) -> str:
    """Transpõe uma tonalidade como ``Em``, ``F#m`` ou ``Bb``."""

    if not key or semitones % 12 == 0:
        return key
    match = re.match(r"^([A-G][#b]?)(.*)$", key.strip())
    if not match:
        return key
    pitch = _PITCH.get(match.group(1))
    if pitch is None:
        return key
    target = (pitch + semitones) % 12
    prefer_flats = _prefers_flats(_render_pitch(target, False))
    return _render_pitch(target, prefer_flats) + match.group(2)


def prefer_flats_for(key: str, semitones: int) -> bool:
    """Decide entre sustenidos e bemóis a partir da tonalidade de destino."""

    return _prefers_flats(transpose_key(key, semitones) if key else "")
