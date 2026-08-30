"""Onde estão as diretivas, os acordes e as tablaturas em um texto ChordPro.

Fica separado da interface para poder ser testado sem abrir janela nenhuma.
As posições são deslocamentos de caractere no texto inteiro, contando as
quebras de linha — é o que o widget de texto do Tk consome.
"""

from __future__ import annotations

import re

DIRETIVA = "diretiva"
ACORDE = "acorde"
TABLATURA = "tablatura"

_DIRETIVA_RE = re.compile(r"\{[^}\n]*\}")
_ACORDE_RE = re.compile(r"\[[^\]\n]*\]")

_ABRE_TAB = re.compile(r"^\s*\{\s*(start_of_tab|sot)\b", re.IGNORECASE)
_FECHA_TAB = re.compile(r"^\s*\{\s*(end_of_tab|eot)\b", re.IGNORECASE)


def spans(text: str) -> list[tuple[str, int, int]]:
    """Devolve ``(marcador, início, fim)`` para cada trecho a destacar."""

    encontrados: list[tuple[str, int, int]] = []

    for match in _DIRETIVA_RE.finditer(text):
        encontrados.append((DIRETIVA, match.start(), match.end()))
    for match in _ACORDE_RE.finditer(text):
        encontrados.append((ACORDE, match.start(), match.end()))

    # o miolo das tablaturas, para ficar visualmente distinto da letra
    posicao = 0
    dentro = False
    for linha in text.splitlines(keepends=True):
        fim = posicao + len(linha.rstrip("\n"))
        if _ABRE_TAB.match(linha):
            dentro = True
        elif _FECHA_TAB.match(linha):
            dentro = False
        elif dentro and linha.strip():
            encontrados.append((TABLATURA, posicao, fim))
        posicao += len(linha)

    return encontrados
