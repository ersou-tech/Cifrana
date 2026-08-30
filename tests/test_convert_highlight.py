import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cifrana import highlight
from cifrana.convert import Options, fetch_and_render, render
from cifrana.parser import parse_print_page

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_impressao.html"


class FetcherFalso:
    """Devolve sempre a mesma página e anota o que foi pedido."""

    def __init__(self, corpo):
        self.corpo = corpo
        self.pedidos = []

    def get(self, url):
        self.pedidos.append(url)
        return self.corpo


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.song = parse_print_page(FIXTURE.read_text(encoding="utf-8"), url="https://exemplo/")

    def test_nome_padrao(self):
        convertida = render(self.song, Options())
        self.assertEqual(convertida.filename, "Banda Ficticia - Cifra De Teste.cho")
        self.assertIn("{title: Cifra De Teste}", convertida.content)

    def test_transposicao_afeta_conteudo_e_nome(self):
        convertida = render(self.song, Options(transpose=2, name_template="{title} ({key})"))
        self.assertEqual(convertida.filename, "Cifra De Teste (A).cho")
        self.assertIn("{key: A}", convertida.content)

    def test_opcoes_chegam_ao_chordpro(self):
        sem_tabs = render(self.song, Options(tabs=False, source=False))
        self.assertNotIn("start_of_tab", sem_tabs.content)
        self.assertNotIn("Fonte:", sem_tabs.content)

        com_refrao = render(self.song, Options(chorus=True))
        self.assertIn("{start_of_chorus: Refrão}", com_refrao.content)

    def test_extensao_e_ascii(self):
        convertida = render(self.song, Options(ext=".pro", ascii_only=True))
        self.assertTrue(convertida.filename.endswith(".pro"))
        self.assertEqual(convertida.filename, "Banda Ficticia - Cifra De Teste.pro")


class FetchAndRenderTest(unittest.TestCase):
    def test_busca_a_versao_de_impressao(self):
        fetcher = FetcherFalso(FIXTURE.read_text(encoding="utf-8"))
        convertida = fetch_and_render("banda-ficticia/cifra-de-teste", fetcher, Options())
        self.assertEqual(
            fetcher.pedidos,
            ["https://www.cifraclub.com.br/banda-ficticia/cifra-de-teste/imprimir.html"],
        )
        self.assertEqual(convertida.song.title, "Cifra De Teste")


class HighlightTest(unittest.TestCase):
    def marcadores(self, texto):
        return {(tag, texto[a:b]) for tag, a, b in highlight.spans(texto)}

    def test_diretivas_e_acordes(self):
        texto = "{title: X}\n[C]uma linha [G7]aqui\n"
        encontrados = self.marcadores(texto)
        self.assertIn((highlight.DIRETIVA, "{title: X}"), encontrados)
        self.assertIn((highlight.ACORDE, "[C]"), encontrados)
        self.assertIn((highlight.ACORDE, "[G7]"), encontrados)

    def test_miolo_da_tablatura(self):
        texto = "{start_of_tab}\nE|--3--|\nB|--0--|\n{end_of_tab}\ndepois\n"
        encontrados = self.marcadores(texto)
        self.assertIn((highlight.TABLATURA, "E|--3--|"), encontrados)
        self.assertIn((highlight.TABLATURA, "B|--0--|"), encontrados)
        self.assertNotIn((highlight.TABLATURA, "depois"), encontrados)

    def test_abreviacoes_sot_eot(self):
        texto = "{sot}\nE|--3--|\n{eot}\nfora\n"
        self.assertIn((highlight.TABLATURA, "E|--3--|"), self.marcadores(texto))
        self.assertNotIn((highlight.TABLATURA, "fora"), self.marcadores(texto))

    def test_posicoes_batem_com_o_texto(self):
        texto = FIXTURE.read_text(encoding="utf-8")
        conteudo = render(parse_print_page(texto, url="u"), Options()).content
        for tag, inicio, fim in highlight.spans(conteudo):
            trecho = conteudo[inicio:fim]
            self.assertTrue(trecho.strip(), f"{tag} apontou para trecho vazio")
            if tag == highlight.ACORDE:
                self.assertTrue(trecho.startswith("[") and trecho.endswith("]"))
            elif tag == highlight.DIRETIVA:
                self.assertTrue(trecho.startswith("{") and trecho.endswith("}"))

    def test_texto_vazio(self):
        self.assertEqual(highlight.spans(""), [])


if __name__ == "__main__":
    unittest.main()
