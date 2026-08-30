import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cifrana.search import (
    SearchError,
    parse_search_payload,
    only_artists,
    only_songs,
)

# resposta no mesmo formato do endpoint, com dados inventados
PAYLOAD = """cb({
  "response":{"numFound":3,"start":0,"docs":[
      {"t":"1","m":"Banda Ficticia","a":"Banda Ficticia","d":"banda-ficticia","u":null},
      {"t":"2","m":"Cifra De Teste","a":"Banda Ficticia","d":"banda-ficticia","u":"cifra-de-teste"},
      {"t":"2","m":"Outra Musica","a":"Banda Ficticia","d":"banda-ficticia","u":"outra-musica"}
  ]}})"""


class SearchPayloadTest(unittest.TestCase):
    def setUp(self):
        self.results = parse_search_payload(PAYLOAD)

    def test_parses_songs_and_artists(self):
        self.assertEqual(len(self.results), 3)
        self.assertEqual(len(only_songs(self.results)), 2)
        self.assertEqual(len(only_artists(self.results)), 1)

    def test_song_url_and_label(self):
        song = only_songs(self.results)[0]
        self.assertEqual(
            song.url, "https://www.cifraclub.com.br/banda-ficticia/cifra-de-teste/"
        )
        self.assertEqual(song.label, "Cifra De Teste — Banda Ficticia")

    def test_artist_url_has_no_song_slug(self):
        artist = only_artists(self.results)[0]
        self.assertEqual(artist.url, "https://www.cifraclub.com.br/banda-ficticia/")
        self.assertFalse(artist.is_song)

    def test_payload_without_jsonp_wrapper(self):
        results = parse_search_payload(
            '{"response":{"docs":[{"t":"2","m":"X","a":"Y","d":"y","u":"x"}]}}'
        )
        self.assertEqual(len(results), 1)

    def test_song_without_slug_is_skipped(self):
        results = parse_search_payload(
            '({"response":{"docs":[{"t":"2","m":"X","a":"Y","d":"y","u":null}]}})'
        )
        self.assertEqual(results, [])

    def test_empty_docs(self):
        self.assertEqual(parse_search_payload('({"response":{"docs":[]}})'), [])

    def test_garbage_raises(self):
        with self.assertRaises(SearchError):
            parse_search_payload("<html>erro</html>")


class GuiImportTest(unittest.TestCase):
    """A GUI só é testável onde o Tkinter existe; fora disso o teste é pulado."""

    def test_gui_module_imports(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("Tkinter não disponível neste Python")
        import cifrana.gui as gui

        self.assertTrue(hasattr(gui, "CifranaApp"))
        self.assertTrue(callable(gui.main))
        # a lista de transposição precisa cobrir -11..+11 com o zero no meio
        self.assertEqual(len(gui.TRANSPOSE_VALUES), 23)
        self.assertIn("0", gui.TRANSPOSE_VALUES)
        self.assertIn("+2", gui.TRANSPOSE_VALUES)
        self.assertIn("-3", gui.TRANSPOSE_VALUES)


if __name__ == "__main__":
    unittest.main()
