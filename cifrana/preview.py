"""Transforma o ChordPro na visualização com os acordes acima da letra.

É o caminho inverso do chordpro.py: lá os acordes entram no meio da linha,
aqui eles voltam para cima dela, como aparecem no SongbookPro e no CifraClub.

Fica separado da interface para poder ser testado sem abrir janela nenhuma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TITULO = "titulo"
SUBTITULO = "subtitulo"
INFO = "info"
SECAO = "secao"
ACORDES = "acordes"
LETRA = "letra"
TAB = "tab"
VAZIO = "vazio"

_DIRETIVA_RE = re.compile(r"^\s*\{\s*([a-zA-Z_]+)\s*:?\s*(.*?)\s*\}\s*$")
_ACORDE_RE = re.compile(r"\[([^\]]*)\]")

# nomes curtos aceitos pelo ChordPro
_EQUIVALENTES = {
    "t": "title",
    "st": "subtitle",
    "c": "comment",
    "soc": "start_of_chorus",
    "eoc": "end_of_chorus",
    "sot": "start_of_tab",
    "eot": "end_of_tab",
    "sov": "start_of_verse",
    "eov": "end_of_verse",
}

_ROTULOS = {
    "key": "Tom",
    "capo": "Capotraste",
    "tempo": "BPM",
    "composer": "Composição",
    "album": "Álbum",
    "duration": "Duração",
    "time": "Compasso",
}


@dataclass
class Bloco:
    """Uma linha pronta para desenhar, com o papel que ela cumpre."""

    tipo: str
    texto: str = ""
    refrao: bool = False


def separar_linha(texto: str) -> tuple[str, str]:
    """Divide uma linha ChordPro em ``(linha de acordes, linha de letra)``.

    Os acordes são posicionados na coluna em que estavam embutidos. Quando dois
    acordes ficariam colados, a letra ganha espaços para abrir lugar — é o que
    todo leitor de ChordPro faz, e o que mantém o acorde sobre a sílaba certa.
    """

    acordes = ""
    letra = ""
    posicao = 0

    for encontro in _ACORDE_RE.finditer(texto):
        letra += texto[posicao : encontro.start()]
        posicao = encontro.end()

        nome = encontro.group(1).strip()
        if not nome:
            continue

        alvo = len(letra)
        if acordes and alvo <= len(acordes):
            alvo = len(acordes) + 1  # pelo menos um espaço entre acordes
        if alvo > len(letra):
            letra += " " * (alvo - len(letra))
        acordes += " " * (alvo - len(acordes)) + nome

    letra += texto[posicao:]
    return acordes.rstrip(), letra.rstrip()


def _rotulo_diretiva(nome: str, valor: str) -> str:
    rotulo = _ROTULOS.get(nome, nome.capitalize())
    if nome == "capo" and valor.isdigit():
        return f"{rotulo}: {valor}ª casa"
    return f"{rotulo}: {valor}"


def render(chordpro: str, *, ja_comecou: bool = False) -> list[Bloco]:
    """Converte o texto ChordPro em blocos prontos para exibição.

    ``ja_comecou`` diz que o cabeçalho já foi consumido em outro lugar, então
    todo comentário daqui em diante é rótulo de trecho, e não informação.
    """

    blocos: list[Bloco] = []
    metadados: list[str] = []
    em_tab = False
    em_refrao = False
    # comentários antes da primeira linha de música são cabeçalho (afinação,
    # ritmo, fonte); depois dela são rótulos de trecho ("Refrão", "Solo")
    comecou_a_musica = ja_comecou

    def despejar_metadados() -> None:
        if not metadados:
            return
        # junta os curtos numa linha só; o que for longo (uma URL, por exemplo)
        # fica sozinho, senão a linha estoura a largura da janela
        curtos = [m for m in metadados if len(m) <= 40]
        longos = [m for m in metadados if len(m) > 40]
        if curtos:
            blocos.append(Bloco(INFO, " · ".join(curtos)))
        for item in longos:
            blocos.append(Bloco(INFO, item))
        metadados.clear()

    for linha in chordpro.splitlines():
        if em_tab:
            diretiva = _DIRETIVA_RE.match(linha)
            nome = _EQUIVALENTES.get(diretiva.group(1).lower(), diretiva.group(1).lower()) if diretiva else ""
            if nome == "end_of_tab":
                em_tab = False
                continue
            blocos.append(Bloco(TAB, linha.rstrip(), em_refrao))
            comecou_a_musica = True
            continue

        diretiva = _DIRETIVA_RE.match(linha)
        if diretiva:
            nome = diretiva.group(1).lower()
            nome = _EQUIVALENTES.get(nome, nome)
            valor = diretiva.group(2).strip()

            if nome == "title":
                despejar_metadados()
                blocos.append(Bloco(TITULO, valor))
            elif nome in ("artist", "subtitle"):
                despejar_metadados()
                blocos.append(Bloco(SUBTITULO, valor))
            elif nome in _ROTULOS:
                if valor:
                    metadados.append(_rotulo_diretiva(nome, valor))
            elif nome == "comment":
                if not valor:
                    continue
                if comecou_a_musica:
                    despejar_metadados()
                    blocos.append(Bloco(SECAO, valor, em_refrao))
                else:
                    metadados.append(valor)
            elif nome == "start_of_chorus":
                despejar_metadados()
                comecou_a_musica = True
                em_refrao = True
                blocos.append(Bloco(SECAO, valor or "Refrão", True))
            elif nome == "end_of_chorus":
                em_refrao = False
            elif nome == "start_of_tab":
                despejar_metadados()
                em_tab = True
                comecou_a_musica = True
            elif nome in ("start_of_verse", "end_of_verse", "end_of_tab"):
                pass
            elif valor:
                metadados.append(_rotulo_diretiva(nome, valor))
            continue

        if not linha.strip():
            despejar_metadados()
            blocos.append(Bloco(VAZIO, "", em_refrao))
            continue

        despejar_metadados()
        comecou_a_musica = True
        acordes, letra = separar_linha(linha)
        if acordes:
            blocos.append(Bloco(ACORDES, acordes, em_refrao))
        if letra.strip() or not acordes:
            blocos.append(Bloco(LETRA, letra, em_refrao))

    despejar_metadados()

    # sem linhas em branco sobrando no fim
    while blocos and blocos[-1].tipo == VAZIO:
        blocos.pop()
    return blocos


def como_texto(chordpro: str) -> str:
    """A prévia como texto puro — usada nos testes e para conferência rápida."""

    linhas = []
    for bloco in render(chordpro):
        prefixo = "  " if bloco.refrao and bloco.tipo != SECAO else ""
        linhas.append(prefixo + bloco.texto if bloco.texto else "")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# edição na própria prévia
# ---------------------------------------------------------------------------

def dividir(chordpro: str) -> tuple[list[str], list[str]]:
    """Separa as diretivas de cabeçalho do corpo da cifra.

    O cabeçalho é a sequência de diretivas do começo do arquivo, até a primeira
    linha em branco. Ele é preservado palavra por palavra na ida e na volta, em
    vez de ser remontado — assim nada se perde no caminho.
    """

    linhas = chordpro.splitlines()
    fim = 0
    for indice, linha in enumerate(linhas):
        if not linha.strip() or not _DIRETIVA_RE.match(linha):
            break
        fim = indice + 1
    return linhas[:fim], linhas[fim:]


@dataclass
class Conhecidas:
    """As linhas que a prévia gerou, com o papel de cada uma.

    Serve para a volta não precisar adivinhar o que já se sabe.
    """

    acordes: set[str] = field(default_factory=set)
    letras: set[str] = field(default_factory=set)


def corpo_editavel(chordpro: str) -> tuple[str, Conhecidas]:
    """O corpo da cifra como texto editável, com acordes acima da letra."""

    _, corpo = dividir(chordpro)
    linhas: list[str] = []
    conhecidas = Conhecidas()

    for bloco in render("\n".join(corpo), ja_comecou=True):
        if bloco.tipo == SECAO:
            linhas.append(f"[{bloco.texto}]")
        elif bloco.tipo == VAZIO:
            linhas.append("")
        else:
            # sem recuo no refrão: o espaço viraria parte da letra na volta
            linhas.append(bloco.texto)
            if bloco.tipo == ACORDES:
                conhecidas.acordes.add(bloco.texto)
            elif bloco.tipo == LETRA and bloco.texto.strip():
                conhecidas.letras.add(bloco.texto)

    # sem linhas em branco nas pontas: a separação do cabeçalho é reposta em
    # para_chordpro, e contá-la aqui também faria o texto crescer a cada volta
    while linhas and not linhas[0].strip():
        linhas.pop(0)
    while linhas and not linhas[-1].strip():
        linhas.pop()

    return "\n".join(linhas), conhecidas


def para_chordpro(
    cabecalho: list[str],
    corpo: str,
    *,
    chorus_directives: bool = False,
    keep_tabs: bool = True,
    conhecidas: "Conhecidas | None" = None,
) -> str:
    """Refaz o ChordPro a partir do corpo editado na prévia."""

    from . import sheet
    from .chordpro import render_body

    conhecidas = conhecidas or Conhecidas()
    linhas = render_body(
        sheet.linhas_de_cifra(corpo, conhecidas.acordes, conhecidas.letras),
        chorus_directives=chorus_directives,
        keep_tabs=keep_tabs,
    )

    partes = [linha for linha in cabecalho]
    if partes and linhas:
        partes.append("")
    partes.extend(linhas)
    return "\n".join(partes).rstrip() + "\n"
