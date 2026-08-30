import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cifrana import preview
from cifrana.convert import Options, render as converter
from cifrana.parser import parse_print_page

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_impressao.html"


class SepararLinhaTest(unittest.TestCase):
    def test_acorde_fica_na_coluna_em_que_estava(self):
        # o acorde estava embutido entre o "d" e o "ois": é ali que ele volta,
        # e não no começo da palavra — a coluna original é que manda
        acordes, letra = preview.separar_linha("[C]Numero um d[D]ois tres")
        self.assertEqual(letra, "Numero um dois tres")
        self.assertEqual(acordes.index("C"), 0)
        self.assertEqual(acordes.index("D"), len("Numero um d"))

    def test_acorde_no_meio_da_palavra(self):
        acordes, letra = preview.separar_linha("Conta[Em]ndo")
        self.assertEqual(letra, "Contando")
        self.assertEqual(acordes.index("Em"), len("Conta"))

    def test_linha_sem_acordes(self):
        acordes, letra = preview.separar_linha("so a letra aqui")
        self.assertEqual(acordes, "")
        self.assertEqual(letra, "so a letra aqui")

    def test_acordes_colados_ganham_espaco(self):
        acordes, letra = preview.separar_linha("[Am7][Bm7]depois")
        self.assertEqual(acordes, "Am7 Bm7")
        # a letra é empurrada para não ficar sob o primeiro acorde
        self.assertTrue(letra.endswith("depois"))
        self.assertEqual(acordes.index("Bm7"), letra.index("depois"))

    def test_colchete_vazio_e_ignorado(self):
        acordes, letra = preview.separar_linha("nada[]aqui")
        self.assertEqual(acordes, "")
        self.assertEqual(letra, "nadaaqui")

    def test_linha_so_de_acordes(self):
        acordes, letra = preview.separar_linha("    [G]  [D]")
        self.assertEqual(letra, "")
        # as colunas contam a letra por baixo, não os colchetes: quatro
        # espaços antes do G e mais dois antes do D
        self.assertEqual(acordes.index("G"), 4)
        self.assertEqual(acordes.index("D"), 6)


class RenderTest(unittest.TestCase):
    def blocos(self, texto):
        return preview.render(texto)

    def tipos(self, texto):
        return [b.tipo for b in self.blocos(texto)]

    def test_titulo_e_artista(self):
        blocos = self.blocos("{title: Musica}\n{artist: Banda}\n")
        self.assertEqual(blocos[0].tipo, preview.TITULO)
        self.assertEqual(blocos[0].texto, "Musica")
        self.assertEqual(blocos[1].tipo, preview.SUBTITULO)

    def test_capo_vira_texto_legivel(self):
        blocos = self.blocos("{title: X}\n{capo: 2}\n")
        info = [b.texto for b in blocos if b.tipo == preview.INFO]
        self.assertTrue(any("2ª casa" in t for t in info), info)

    def test_comentario_no_cabecalho_e_informacao(self):
        blocos = self.blocos("{title: X}\n{comment: Afinação: D A D G B E}\n")
        self.assertIn(preview.INFO, [b.tipo for b in blocos])
        self.assertNotIn(preview.SECAO, [b.tipo for b in blocos])

    def test_comentario_depois_da_musica_e_secao(self):
        blocos = self.blocos("{title: X}\n[C]letra\n{comment: Solo}\n")
        secoes = [b.texto for b in blocos if b.tipo == preview.SECAO]
        self.assertEqual(secoes, ["Solo"])

    def test_acordes_vem_antes_da_letra(self):
        tipos = self.tipos("[C]uma linha\n")
        self.assertEqual(tipos, [preview.ACORDES, preview.LETRA])

    def test_linha_sem_acorde_nao_gera_linha_de_acordes(self):
        self.assertEqual(self.tipos("so letra\n"), [preview.LETRA])

    def test_tablatura_sai_literal_e_sem_as_diretivas(self):
        blocos = self.blocos("{start_of_tab}\nE|--3--|\n{end_of_tab}\n")
        self.assertEqual([b.tipo for b in blocos], [preview.TAB])
        self.assertEqual(blocos[0].texto, "E|--3--|")

    def test_refrao_e_marcado(self):
        blocos = self.blocos("{title: X}\n[C]antes\n{start_of_chorus: Refrão}\n[G]dentro\n{end_of_chorus}\n[D]depois\n")
        dentro = [b for b in blocos if b.texto == "dentro"]
        fora = [b for b in blocos if b.texto in ("antes", "depois")]
        self.assertTrue(all(b.refrao for b in dentro))
        self.assertTrue(all(not b.refrao for b in fora))

    def test_abreviacoes_do_chordpro(self):
        blocos = self.blocos("{t: Musica}\n{c: Nota}\n{soc}\n[C]x\n{eoc}\n")
        self.assertEqual(blocos[0].tipo, preview.TITULO)
        self.assertIn(preview.SECAO, [b.tipo for b in blocos])

    def test_texto_vazio(self):
        self.assertEqual(preview.render(""), [])

    def test_nao_sobra_linha_em_branco_no_fim(self):
        blocos = self.blocos("[C]linha\n\n\n\n")
        self.assertNotEqual(blocos[-1].tipo, preview.VAZIO)


class ColunasTest(unittest.TestCase):
    """A prévia tem de reconstituir a cifra como o CifraClub a mostrava."""

    def test_ida_e_volta_devolve_as_mesmas_colunas(self):
        from cifrana.chordpro import song_to_chordpro
        from cifrana.model import ChordAt, RawLine, Song

        original_acordes = "G          D"
        original_letra = "Numero um dois tres"
        musica = Song(
            title="T",
            lines=[
                RawLine(original_acordes, [ChordAt(0, "G"), ChordAt(11, "D")]),
                RawLine(original_letra),
            ],
        )
        chordpro = song_to_chordpro(musica, source=False)

        linha = next(l for l in chordpro.splitlines() if "[" in l and "{" not in l)
        acordes, letra = preview.separar_linha(linha)
        self.assertEqual(letra, original_letra)
        self.assertEqual(acordes, original_acordes)


class IdaEVoltaTest(unittest.TestCase):
    """A prévia precisa reconstituir o que o CifraClub mostrava."""

    def setUp(self):
        song = parse_print_page(FIXTURE.read_text(encoding="utf-8"), url="https://exemplo/")
        self.chordpro = converter(song, Options(chorus=True)).content

    def test_nenhum_colchete_sobra_na_previa(self):
        texto = preview.como_texto(self.chordpro)
        self.assertNotIn("[", texto)
        self.assertNotIn("{", texto)

    def test_a_letra_sobrevive_inteira(self):
        texto = preview.como_texto(self.chordpro)
        for trecho in ("Numero um dois tres", "Contando ate seis", "Ate o fim do teste"):
            self.assertIn(trecho, texto)

    def test_os_acordes_aparecem_todos(self):
        texto = preview.como_texto(self.chordpro)
        for acorde in ("G", "D", "Em", "C", "Am7", "D7", "G/B", "F7M".replace("F7M", "Am7")):
            self.assertIn(acorde, texto)

    def test_a_tablatura_continua_desenhada(self):
        texto = preview.como_texto(self.chordpro)
        self.assertIn("E|-----------------------------------------|", texto)


if __name__ == "__main__":
    unittest.main()


class EdicaoNaPreviaTest(unittest.TestCase):
    """A prévia é editável: o que se digita nela vira ChordPro de volta."""

    def setUp(self):
        song = parse_print_page(FIXTURE.read_text(encoding="utf-8"), url="https://exemplo/")
        self.chordpro = converter(song, Options(chorus=True)).content
        self.cabecalho, _ = preview.dividir(self.chordpro)
        self.corpo, self.conhecidas = preview.corpo_editavel(self.chordpro)

    def ciclo(self, corpo=None):
        return preview.para_chordpro(
            self.cabecalho,
            self.corpo if corpo is None else corpo,
            chorus_directives=True,
            conhecidas=self.conhecidas,
        )

    def test_o_cabecalho_volta_intacto(self):
        volta = self.ciclo()
        for linha in self.cabecalho:
            self.assertIn(linha, volta)

    def test_o_corpo_nao_leva_colchetes_de_acorde(self):
        self.assertNotIn("[C]", self.corpo)
        self.assertNotIn("{", self.corpo)

    def test_secoes_aparecem_entre_colchetes(self):
        self.assertIn("[Primeira Parte]", self.corpo)

    def test_ida_e_volta_e_estavel(self):
        uma = self.ciclo()
        cab2, _ = preview.dividir(uma)
        corpo2, conhecidas2 = preview.corpo_editavel(uma)
        duas = preview.para_chordpro(
            cab2, corpo2, chorus_directives=True, conhecidas=conhecidas2
        )
        self.assertEqual(uma, duas, "o texto continua mudando a cada volta")

    def test_a_previa_vista_nao_muda_na_volta(self):
        volta = self.ciclo()
        self.assertEqual(preview.corpo_editavel(volta)[0], self.corpo)

    def test_trocar_um_acorde_na_previa(self):
        corpo = self.corpo.replace("G          D", "Gm         D")
        volta = self.ciclo(corpo)
        self.assertIn("[Gm]", volta)
        self.assertIn("[D]", volta)

    def test_corrigir_a_letra_na_previa(self):
        corpo = self.corpo.replace("Contando ate seis", "Contando ate dez")
        volta = self.ciclo(corpo)
        # o acorde cai no meio da palavra, então a letra volta partida pelo
        # colchete: o que precisa sobreviver é o texto sem os acordes
        sem_acordes = preview.como_texto(volta)
        self.assertIn("Contando ate dez", sem_acordes)

    def test_refrao_sobrevive_a_ida_e_volta(self):
        volta = self.ciclo()
        self.assertIn("{start_of_chorus: Refrão}", volta)
        self.assertIn("{end_of_chorus}", volta)

    def test_tablatura_sobrevive_a_ida_e_volta(self):
        volta = self.ciclo()
        self.assertIn("{start_of_tab}", volta)
        self.assertIn("E|-----------------------------------------|", volta)

    def test_verso_que_parece_acorde_sobrevive(self):
        """Um verso como "Am" é indistinguível de um acorde olhando a linha.

        O que resolve é a origem: se a prévia o mostrou como letra, ele
        continua letra depois da volta.
        """

        original = "{title: X}\n\n{comment: Parte}\n[C]uma linha\nAm\n"
        cabecalho, _ = preview.dividir(original)
        corpo, conhecidas = preview.corpo_editavel(original)
        self.assertIn("Am", corpo)

        volta = preview.para_chordpro(cabecalho, corpo, conhecidas=conhecidas)
        self.assertIn("\nAm\n", volta, "o verso virou acorde na volta")
        self.assertNotIn("[Am]", volta)

    def test_linha_nova_que_so_tem_acordes_e_lida_como_acordes(self):
        """Sem histórico, a linha é classificada pelo que ela parece."""

        corpo = self.corpo + "\n\n[Coda]\nC  Am\n"
        volta = self.ciclo(corpo)
        self.assertIn("[C]", volta)
        self.assertIn("[Am]", volta)

    def test_linha_de_acordes_nova_e_reconhecida(self):
        corpo = self.corpo + "\n\n[Coda]\nC  G  Am\numa letra qualquer\n"
        volta = self.ciclo(corpo)
        self.assertIn("[C]uma letra qualquer", volta.replace("[G]", "").replace("[Am]", ""))
