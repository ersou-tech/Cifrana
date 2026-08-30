import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from cifrana.chordpro import classify, residual_text, CHORDS, LYRICS, SECTION, TAB, BLANK
from cifrana.model import ChordAt, RawLine
from cifrana.parser import parse_artist_page, parse_print_page, ParseError

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_impressao.html"


class ParsePrintPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = parse_print_page(
            FIXTURE.read_text(encoding="utf-8"),
            url="https://www.cifraclub.com.br/banda-ficticia/cifra-de-teste/",
        )

    def test_metadata(self):
        self.assertEqual(self.song.title, "Cifra De Teste")
        self.assertEqual(self.song.artist, "Banda Ficticia")
        self.assertEqual(self.song.composer, "Fulano de Tal")
        self.assertEqual(self.song.key, "G")
        self.assertEqual(self.song.tuning, "D A D G B E")
        self.assertEqual(self.song.capo, 2)
        self.assertEqual(self.song.tempo, 120)
        self.assertEqual(self.song.rhythm, "Ritmo Padrão")

    def test_pages_are_concatenated(self):
        text = "\n".join(line.text for line in self.song.lines)
        self.assertIn("[Primeira Parte]", text)
        self.assertIn("[Refrão]", text)
        self.assertIn("[Final]", text)

    def test_chord_columns_match_text(self):
        for line in self.song.lines:
            for chord in line.chords:
                self.assertEqual(
                    line.text[chord.col : chord.end],
                    chord.text,
                    f"coluna errada para {chord.name!r} em {line.text!r}",
                )

    def test_page_break_does_not_duplicate_lines(self):
        texts = [line.text for line in self.song.lines if line.text.strip()]
        for header in ("[Primeira Parte]", "[Refrão]", "[Intro] G  D  Em"):
            self.assertEqual(texts.count(header), 1, f"{header!r} duplicado na junção das páginas")

    def test_missing_sheet_raises(self):
        with self.assertRaises(ParseError):
            parse_print_page("<html><body><p>sem cifra</p></body></html>")


class ClassifyTest(unittest.TestCase):
    def test_blank(self):
        self.assertEqual(classify(RawLine("   ")), BLANK)

    def test_section(self):
        self.assertEqual(classify(RawLine("[Primeira Parte]")), SECTION)

    def test_chord_only_line(self):
        line = RawLine("G   D", [ChordAt(0, "G"), ChordAt(4, "D")])
        self.assertEqual(classify(line), CHORDS)

    def test_chord_line_with_repeat_marker(self):
        line = RawLine("G   D  ( 2x )", [ChordAt(0, "G"), ChordAt(4, "D")])
        self.assertEqual(classify(line), CHORDS)

    def test_tab_line(self):
        self.assertEqual(classify(RawLine("E|-----3---5---|")), TAB)

    def test_lyrics(self):
        self.assertEqual(classify(RawLine("contando ate seis")), LYRICS)

    def test_residual_blanks_out_chords(self):
        line = RawLine("Gm   D", [ChordAt(0, "Gm"), ChordAt(5, "D")])
        self.assertEqual(residual_text(line).strip(), "")


class ArtistPageTest(unittest.TestCase):
    def test_extracts_song_links(self):
        html = (
            '<a href="/banda-ficticia/uma-musica/">x</a>'
            '<a href="/banda-ficticia/outra-musica/">y</a>'
            '<a href="/banda-ficticia/discografia/">z</a>'
            '<a href="/outra-banda/musica/">w</a>'
            '<a href="/banda-ficticia/uma-musica/">repetida</a>'
        )
        found = parse_artist_page(html, "banda-ficticia")
        self.assertEqual(
            found,
            [
                "https://www.cifraclub.com.br/banda-ficticia/uma-musica/",
                "https://www.cifraclub.com.br/banda-ficticia/outra-musica/",
            ],
        )


if __name__ == "__main__":
    unittest.main()
