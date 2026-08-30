"""Testes do editor de cifras. Pulam onde não há Tkinter ou display."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cifrana.convert import Options, render
from cifrana.parser import parse_print_page

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_impressao.html"


def _tk_ou_pula(caso):
    try:
        import tkinter as tk
    except ImportError:
        caso.skipTest("Tkinter não disponível neste Python")
    try:
        raiz = tk.Tk()
    except tk.TclError as exc:
        caso.skipTest(f"sem display para abrir janela ({exc})")
    raiz.withdraw()
    return raiz


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.root = _tk_ou_pula(self)
        from cifrana.gui import CifranaApp, QueueItem

        self.app = CifranaApp(self.root)
        self.convertida = render(
            parse_print_page(FIXTURE.read_text(encoding="utf-8"), url="https://exemplo/"),
            Options(),
        )
        self.item = QueueItem("Cifra De Teste — Banda Ficticia", "Banda Ficticia", "https://exemplo/")
        self.app.add_items([self.item])
        self.item.content = self.convertida.content
        self.item.filename = self.convertida.filename
        self.app.refresh_item(self.item)
        self.app.queue_tree.selection_set(self.item.url)

    def tearDown(self):
        self.root.destroy()

    def abrir(self):
        self.app.open_editor()
        return next(iter(self.app.editors.values()))

    def trocar_aba(self, editor, indice):
        """Troca de aba e deixa o Tk despachar o evento.

        Sem mainloop, o <<NotebookTabChanged>> fica na fila até um update().
        """

        editor.caderno.select(indice)
        self.root.update()

    def test_abre_com_o_texto_convertido(self):
        editor = self.abrir()
        self.assertEqual(editor.texto_atual(), self.convertida.content)
        self.assertEqual(editor.file_var.get(), self.convertida.filename)
        self.assertFalse(editor.alterado)

    def test_destaque_marca_acordes_diretivas_e_tablatura(self):
        editor = self.abrir()
        for marcador in ("acorde", "diretiva", "tablatura"):
            self.assertTrue(
                editor.text.tag_ranges(marcador), f"nada destacado como {marcador}"
            )

    def test_editar_e_salvar_marca_a_musica(self):
        editor = self.abrir()
        editor.text.insert("1.0", "{comment: Meu arranjo}\n")
        self.assertTrue(editor.alterado)

        editor.salvar()
        self.assertFalse(editor.alterado)
        self.assertTrue(self.item.edited)
        self.assertIn("{comment: Meu arranjo}", self.item.content)
        self.assertEqual(self.item.state_label, "editada")

    def test_salvar_sem_mudar_nada_nao_marca_como_editada(self):
        editor = self.abrir()
        editor.salvar()
        self.assertFalse(self.item.edited)
        self.assertEqual(self.item.state_label, "revisada")

    def test_nome_do_arquivo_ganha_extensao_e_e_saneado(self):
        editor = self.abrir()
        editor.file_var.set("minha/cifra")
        editor.salvar()
        self.assertEqual(self.item.filename, "minha-cifra.cho")

    def test_reabrir_devolve_a_mesma_janela(self):
        primeira = self.abrir()
        self.app.open_editor()
        self.assertIs(next(iter(self.app.editors.values())), primeira)

    def test_exportacao_usa_o_texto_editado_sem_baixar_de_novo(self):
        editor = self.abrir()
        editor.text.insert("1.0", "{comment: Meu arranjo}\n")
        editor.salvar()

        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp)
            # sem rede: o item já tem conteúdo, então nada deve ser baixado
            self.app._export_worker([self.item], destino, Options(), False)
            gravado = destino / self.item.filename
            self.assertTrue(gravado.is_file(), f"não gravou {self.item.filename}")
            self.assertIn("{comment: Meu arranjo}", gravado.read_text(encoding="utf-8"))

    def test_recarregar_limpa_a_marca_de_edicao(self):
        editor = self.abrir()
        editor.text.insert("1.0", "{comment: Meu arranjo}\n")
        editor.salvar()
        self.assertTrue(self.item.edited)

        # só a parte que não toca a rede: descarta o texto e marca para rebaixar
        self.item.content = None
        self.item.edited = False
        self.app.refresh_item(self.item)
        self.assertEqual(self.item.state_label, "")


class EdicaoNaPreviaTest(EditorTest):
    """Editar na aba Prévia precisa chegar ao arquivo exportado."""

    def test_a_previa_abre_com_o_corpo_da_cifra(self):
        editor = self.abrir()
        corpo = editor.previa.get("1.0", "end-1c")
        self.assertIn("[Primeira Parte]", corpo)
        self.assertNotIn("{title:", corpo)   # o cabeçalho fica fora
        self.assertNotIn("[C]", corpo)       # e os acordes não vêm entre colchetes

    def test_trocar_acorde_na_previa_chega_ao_chordpro(self):
        editor = self.abrir()
        corpo = editor.previa.get("1.0", "end-1c")
        numero = next(
            n for n, linha in enumerate(corpo.splitlines(), start=1)
            if linha == "G          D"
        )
        editor.previa.delete(f"{numero}.0", f"{numero}.end")
        editor.previa.insert(f"{numero}.0", "Gm         D")
        editor._fonte = "previa"

        chordpro = editor.texto_atual()
        self.assertIn("[Gm]", chordpro)
        self.assertIn("[D]", chordpro)

    def test_edicao_na_previa_marca_e_salva(self):
        editor = self.abrir()
        editor.previa.insert("1.0", "[Meu trecho]\n")
        editor._fonte = "previa"
        editor.salvar()

        self.assertTrue(self.item.edited)
        self.assertIn("{comment: Meu trecho}", self.item.content)

    def test_as_abas_se_mantem_em_dia(self):
        editor = self.abrir()
        editor.previa.insert("1.0", "[Coda]\nC  G\numa letra\n")
        editor._fonte = "previa"
        self.trocar_aba(editor, 1)           # vai para a aba Texto
        self.assertIn("{comment: Coda}", editor.text.get("1.0", "end-1c"))

        self.trocar_aba(editor, 0)           # e volta para a Prévia
        self.assertIn("[Coda]", editor.previa.get("1.0", "end-1c"))

    def test_ida_e_volta_pelas_abas_nao_altera_a_cifra(self):
        editor = self.abrir()
        antes = editor.texto_atual()
        for _ in range(3):
            self.trocar_aba(editor, 0)
            self.trocar_aba(editor, 1)
        self.assertEqual(editor.texto_atual(), antes)


if __name__ == "__main__":
    unittest.main()
