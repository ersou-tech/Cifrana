"""Lê um texto de cifra — acordes acima da letra — e localiza os acordes.

É o que permite editar direto na prévia: o texto que o usuário digita volta a
ser um :class:`~cifrana.model.Song`, e daí segue pelo mesmo caminho já usado
para as cifras baixadas do CifraClub.
"""

from __future__ import annotations

import re

from .model import ChordAt, RawLine

# Sufixos de acorde aceitos. Precisa ser restrito: com um "qualquer coisa"
# depois da nota, palavras comuns da letra ("Eu", "Ah", "Bem") passariam por
# acordes e a linha inteira seria lida errado.
_SUFIXO = re.compile(
    r"^(?:maj|min|dim|aug|sus|add|alt|m|M|°|º|Δ|\+|-|#|b|\d|\(|\)|/|,)*$"
)
_ACORDE = re.compile(r"^([A-G])([#b]?)(.*?)(?:/([A-G])([#b]?))?$")

# marcadores que costumam dividir espaço com os acordes numa mesma linha
_MARCADOR = re.compile(r"^(?:\(?\d+\s*[xX]\)?|[|:%.,\-~()]+)$")


def e_acorde(token: str) -> bool:
    """O token é um acorde? Restritivo de propósito."""

    token = token.strip()
    if not token or len(token) > 12:
        return False
    encontro = _ACORDE.match(token)
    if not encontro:
        return False
    return bool(_SUFIXO.match(encontro.group(3)))


def _tokens(linha: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group()) for m in re.finditer(r"\S+", linha)]


def e_linha_de_acordes(linha: str) -> bool:
    """A linha é só acordes (e talvez marcadores de repetição)?"""

    tokens = _tokens(linha)
    if not tokens:
        return False
    if not any(e_acorde(texto) for _, texto in tokens):
        return False
    return all(e_acorde(texto) or _MARCADOR.match(texto) for _, texto in tokens)


def linhas_de_cifra(
    texto: str,
    acordes_conhecidos: set[str] | None = None,
    letras_conhecidas: set[str] | None = None,
) -> list[RawLine]:
    """Converte o texto da cifra em linhas com os acordes marcados por coluna.

    Alguns versos são indistinguíveis de acordes — uma linha só com "Am", por
    exemplo. Por isso as linhas que já apareceram na prévia entram aqui com o
    papel que tinham: quem não foi mexido continua sendo o que era. Só as
    linhas novas passam pela adivinhação.
    """

    conhecidos = acordes_conhecidos or set()
    letras = letras_conhecidas or set()
    linhas: list[RawLine] = []

    for linha in texto.splitlines():
        linha = linha.rstrip()
        if linha.strip() and linha in letras:
            linhas.append(RawLine(linha))
            continue
        if linha.strip() and (linha in conhecidos or e_linha_de_acordes(linha)):
            marcados = [
                ChordAt(coluna, token)
                for coluna, token in _tokens(linha)
                if e_acorde(token)
            ]
            if marcados:
                linhas.append(RawLine(linha, marcados))
                continue
        linhas.append(RawLine(linha))

    return linhas
