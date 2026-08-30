"""Interface de linha de comando do Cifrana."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .chordpro import song_to_chordpro
from .chords import transpose_key
from .exporter import DEFAULT_EXT, build_filename, make_zip, write_song
from .fetcher import Fetcher, FetchError
from .parser import ParseError, parse_artist_page, parse_print_page
from .urls import InvalidURL, artist_slug, artist_url, print_url, song_url

log = logging.getLogger("cifrana")

EPILOG = """\
exemplos:
  cifrana https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/
  cifrana legiao-urbana/tempo-perdido -o ./cifras --zip cifras.zip
  cifrana --artista https://www.cifraclub.com.br/legiao-urbana/ -o ./cifras
  cifrana --lista minhas-musicas.txt -o ./cifras --transpor 2
  cifrana legiao-urbana/tempo-perdido --stdout

Os arquivos .cho gerados são ChordPro: no SongbookPro use
Menu > Import > (Files / Folder) e escolha os arquivos ou o zip.
"""


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cifrana",
        description="Baixa cifras do CifraClub e exporta em ChordPro para o SongbookPro.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        metavar="URL",
        help="URL da cifra (ou apenas 'artista/musica')",
    )
    parser.add_argument(
        "--lista",
        "--from-file",
        dest="lista",
        metavar="ARQUIVO",
        help="arquivo texto com uma URL por linha (# vira comentário)",
    )
    parser.add_argument(
        "--artista",
        "--artist",
        dest="artistas",
        action="append",
        default=[],
        metavar="URL",
        help="baixa as músicas listadas na página do artista (pode repetir)",
    )
    parser.add_argument(
        "-o",
        "--saida",
        "--out",
        dest="saida",
        default="cifras",
        metavar="PASTA",
        help="pasta de saída (padrão: ./cifras)",
    )
    parser.add_argument(
        "--zip",
        metavar="ARQUIVO",
        help="também gera um .zip com todas as cifras exportadas",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="imprime o ChordPro no terminal em vez de gravar arquivos",
    )
    parser.add_argument(
        "--transpor",
        "--transpose",
        dest="transpor",
        type=int,
        default=0,
        metavar="N",
        help="transpõe N semitons (ex.: 2 ou -3)",
    )
    parser.add_argument(
        "--refrao",
        "--chorus",
        dest="refrao",
        action="store_true",
        help="usa {start_of_chorus}/{end_of_chorus} nos refrões",
    )
    parser.add_argument(
        "--sem-tabs",
        dest="sem_tabs",
        action="store_true",
        help="descarta os blocos de tablatura",
    )
    parser.add_argument(
        "--sem-fonte",
        dest="sem_fonte",
        action="store_true",
        help="não inclui o comentário com a URL de origem",
    )
    parser.add_argument(
        "--nome",
        default="{artist} - {title}",
        metavar="MODELO",
        help="modelo do nome do arquivo (campos: {artist}, {title}, {key})",
    )
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXT,
        help=f"extensão dos arquivos (padrão: {DEFAULT_EXT})",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="remove acentos dos nomes de arquivo",
    )
    parser.add_argument(
        "--sobrescrever",
        "--overwrite",
        dest="sobrescrever",
        action="store_true",
        help="sobrescreve arquivos existentes em vez de criar '(2)'",
    )
    parser.add_argument(
        "--intervalo",
        "--delay",
        dest="intervalo",
        type=float,
        default=1.0,
        metavar="SEGUNDOS",
        help="espera entre requisições (padrão: 1.0)",
    )
    parser.add_argument(
        "--cache",
        metavar="PASTA",
        default=".cifrana-cache",
        help="pasta de cache do HTML baixado (use --sem-cache para desligar)",
    )
    parser.add_argument(
        "--sem-cache",
        dest="sem_cache",
        action="store_true",
        help="não usa cache em disco",
    )
    parser.add_argument(
        "--recarregar",
        dest="recarregar",
        action="store_true",
        help="ignora o cache e baixa de novo",
    )
    parser.add_argument(
        "--gui",
        "--interface",
        dest="gui",
        action="store_true",
        help="abre a interface gráfica",
    )
    parser.add_argument("-v", "--verboso", action="store_true", help="mostra mais detalhes")
    parser.add_argument("--version", action="version", version=f"cifrana {__version__}")
    return parser


def read_url_list(path: str) -> list[str]:
    entries: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return entries


def collect_urls(args: argparse.Namespace, fetcher: Fetcher) -> list[str]:
    urls: list[str] = list(args.urls)

    if args.lista:
        urls.extend(read_url_list(args.lista))

    for entry in args.artistas:
        slug = artist_slug(entry)
        page = fetcher.get(artist_url(entry))
        found = parse_artist_page(page, slug)
        if not found:
            log.warning("nenhuma música encontrada na página de %s", slug)
        else:
            log.info("%d música(s) encontradas em %s", len(found), slug)
        urls.extend(found)

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in urls:
        try:
            canonical = song_url(entry)
        except InvalidURL as exc:
            log.error("%s", exc)
            continue
        if canonical not in seen:
            seen.add(canonical)
            normalized.append(canonical)
    return normalized


def convert_one(url: str, args: argparse.Namespace, fetcher: Fetcher) -> tuple[str, str]:
    """Baixa e converte uma cifra. Devolve ``(nome_do_arquivo, conteudo)``."""

    page = fetcher.get(print_url(url))
    song = parse_print_page(page, url=url)
    content = song_to_chordpro(
        song,
        transpose=args.transpor,
        chorus_directives=args.refrao,
        keep_tabs=not args.sem_tabs,
        source=not args.sem_fonte,
    )
    if args.transpor:
        # o nome do arquivo deve refletir o tom realmente exportado
        song = replace(song, key=transpose_key(song.key, args.transpor))
    filename = build_filename(song, args.nome, args.ext, args.ascii)
    return filename, content


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)

    if args.gui:
        from .gui import main as gui_main

        return gui_main()

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    fetcher = Fetcher(
        cache_dir=None if args.sem_cache else args.cache,
        delay=args.intervalo,
        refresh=args.recarregar,
    )

    try:
        urls = collect_urls(args, fetcher)
    except (FetchError, InvalidURL) as exc:
        log.error("%s", exc)
        return 2

    if not urls:
        log.error("nenhuma cifra informada. Use --help para ver exemplos.")
        return 2

    out_dir = Path(args.saida).expanduser()
    written: list[Path] = []
    failures = 0

    for index, url in enumerate(urls, start=1):
        log.info("[%d/%d] %s", index, len(urls), url)
        try:
            filename, content = convert_one(url, args, fetcher)
        except (FetchError, ParseError, InvalidURL) as exc:
            log.error("  falhou: %s", exc)
            failures += 1
            continue

        if args.stdout:
            if len(urls) > 1:
                print(f"\n===== {filename} =====")
            print(content, end="")
            continue

        path = write_song(content, out_dir, filename, args.sobrescrever)
        written.append(path)
        log.info("  -> %s", path)

    if args.zip and written:
        zip_path = make_zip(written, Path(args.zip).expanduser())
        log.info("zip gerado: %s", zip_path)

    if not args.stdout:
        log.info("%d cifra(s) exportada(s), %d falha(s)", len(written), failures)

    if failures and not written and not args.stdout:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
