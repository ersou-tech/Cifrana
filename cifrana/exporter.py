"""Escrita dos arquivos ChordPro prontos para importar no SongbookPro."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from pathlib import Path

from .model import Song

DEFAULT_EXT = ".cho"

# Caracteres proibidos em nomes de arquivo no Windows (e problemáticos no resto).
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, ascii_only: bool = False) -> str:
    """Transforma um título em um nome de arquivo seguro."""

    cleaned = _INVALID_CHARS.sub("-", name)
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if ascii_only:
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if cleaned.upper().split(".")[0] in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:120] or "cifra"


def build_filename(
    song: Song,
    template: str = "{artist} - {title}",
    ext: str = DEFAULT_EXT,
    ascii_only: bool = False,
) -> str:
    values = {
        "artist": song.artist or "Desconhecido",
        "title": song.title or "Sem titulo",
        "key": song.key or "",
    }
    try:
        base = template.format(**values)
    except (KeyError, IndexError):
        base = f"{values['artist']} - {values['title']}"
    base = base.strip(" -")
    if not ext.startswith("."):
        ext = "." + ext
    return safe_filename(base, ascii_only) + ext


def unique_path(path: Path) -> Path:
    """Acrescenta ``(2)``, ``(3)``… se o arquivo já existir."""

    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def write_song(
    content: str,
    out_dir: Path,
    filename: str,
    overwrite: bool = False,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    if path.exists() and not overwrite:
        path = unique_path(path)
    # BOM ajuda alguns importadores a reconhecer UTF-8 com acentuação
    path.write_text(content, encoding="utf-8")
    return path


def make_zip(files: list[Path], zip_path: Path) -> Path:
    """Empacota os .cho em um zip (prático para mandar ao celular)."""

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, arcname=file.name)
    return zip_path
