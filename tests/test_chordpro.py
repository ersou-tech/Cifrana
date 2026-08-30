import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from cifrana.chordpro import song_to_chordpro
from cifrana.chords import transpose_chord, transpose_key
from cifrana.model import ChordAt, RawLine, Song
from cifrana.parser import parse_print_page

FIXTURE = Path(__file__).parent / "fixtures" / "exemplo_impressao.html"


def song_with(lines):
    return Song(title="T", artist="A", lines=lines)


class InlineChordTest(unittest.TestCase):
    def test_chord_is_inserted_at_the_right_column(self):
        chord_line = RawLine("G          D", [ChordAt(0, "G"), ChordAt(11, "D")])
        lyric_line = RawLine("Numero um dois tres")
        out = song_to_chordpro(song_with([chord_line, lyric_line]), source=False)
        self.assertIn("[G]Numero um d[D]ois tres", out)

    def test_chord_past_end_of_lyric_is_padded(self):
        chord_line = RawLine("               C", [ChordAt(15, "C")])
        lyric_line = RawLine("curta")
        out = song_to_chordpro(song_with([chord_line, lyric_line]), source=False)
        self.assertIn("curta          [C]", out)

    def test_chord_only_line_keeps_spacing(self):
        chord_line = RawLine("G  D", [ChordAt(0, "G"), ChordAt(3, "D")])
        out = song_to_chordpro(song_with([chord_line, RawLine("")]), source=False)
        self.assertIn("[G]  [D]", out)

    def test_square_brackets_in_lyrics_become_parentheses(self):
        chord_line = RawLine("G", [ChordAt(0, "G")])
        lyric_line = RawLine("uma [nota] qualquer")
        out = song_to_chordpro(song_with([chord_line, lyric_line]), source=False)
        self.assertIn("[G]uma (nota) qualquer", out)
        self.assertNotIn("[nota]", out)

    def test_section_header_becomes_comment(self):
        out = song_to_chordpro(song_with([RawLine("[Primeira Parte]")]), source=False)
        self.assertIn("{comment: Primeira Parte}", out)

    def test_section_header_with_chords_on_same_line(self):
        line = RawLine("[Intro] G  D", [ChordAt(8, "G"), ChordAt(11, "D")])
        out = song_to_chordpro(song_with([line]), source=False)
        self.assertIn("{comment: Intro}", out)
        self.assertIn("[G]", out)
        self.assertNotIn("[Intro]", out)

    def test_chorus_directives_are_optional(self):
        lines = [RawLine("[Refrão]"), RawLine("uma linha")]
        default = song_to_chordpro(song_with(lines), source=False)
        self.assertIn("{comment: Refrão}", default)

        with_chorus = song_to_chordpro(song_with(lines), chorus_directives=True, source=False)
        self.assertIn("{start_of_chorus: Refrão}", with_chorus)
        self.assertIn("{end_of_chorus}", with_chorus)


class TabTest(unittest.TestCase):
    def test_tab_block_is_wrapped_and_literal(self):
        lines = [
            RawLine("   G", [ChordAt(3, "G")]),
            RawLine("E|--3---5--|"),
            RawLine("B|--0---0--|"),
        ]
        out = song_to_chordpro(song_with(lines), source=False)
        self.assertIn("{start_of_tab}", out)
        self.assertIn("{end_of_tab}", out)
        self.assertIn("E|--3---5--|", out)
        # dentro da tablatura o acorde fica literal, para manter o alinhamento
        self.assertIn("\n   G\n", out)

    def test_tabs_can_be_dropped(self):
        lines = [RawLine("E|--3---5--|"), RawLine("B|--0---0--|"), RawLine("depois")]
        out = song_to_chordpro(song_with(lines), keep_tabs=False, source=False)
        self.assertNotIn("start_of_tab", out)
        self.assertNotIn("E|", out)
        self.assertIn("depois", out)


class HeaderTest(unittest.TestCase):
    def test_directives(self):
        song = Song(
            title="Cifra De Teste",
            artist="Banda Ficticia",
            composer="Fulano",
            key="G",
            capo=2,
            tempo=120,
            tuning="D A D G B E",
            url="https://exemplo/",
            lines=[RawLine("abc")],
        )
        out = song_to_chordpro(song)
        for expected in (
            "{title: Cifra De Teste}",
            "{artist: Banda Ficticia}",
            "{composer: Fulano}",
            "{key: G}",
            "{capo: 2}",
            "{tempo: 120}",
            "{comment: Afinação: D A D G B E}",
            "{comment: Fonte: https://exemplo/}",
        ):
            self.assertIn(expected, out)

    def test_standard_tuning_is_not_reported(self):
        song = Song(title="T", tuning="E A D G B E", lines=[RawLine("abc")])
        self.assertNotIn("Afinação", song_to_chordpro(song, source=False))

    def test_source_can_be_omitted(self):
        song = Song(title="T", url="https://exemplo/", lines=[RawLine("abc")])
        self.assertNotIn("Fonte", song_to_chordpro(song, source=False))


class TransposeTest(unittest.TestCase):
    def test_chord_transposition(self):
        self.assertEqual(transpose_chord("C", 2), "D")
        self.assertEqual(transpose_chord("Am7", 3), "Cm7")
        self.assertEqual(transpose_chord("G/B", -2), "F/A")
        self.assertEqual(transpose_chord("C7M", 1), "C#7M")
        self.assertEqual(transpose_chord("Intro", 2), "Intro")

    def test_key_transposition(self):
        self.assertEqual(transpose_key("Em", 2), "F#m")
        self.assertEqual(transpose_key("C", 5), "F")

    def test_song_transposition_updates_key_and_chords(self):
        song = Song(
            title="T",
            key="G",
            lines=[RawLine("G", [ChordAt(0, "G")]), RawLine("letra")],
        )
        out = song_to_chordpro(song, transpose=2, source=False)
        self.assertIn("{key: A}", out)
        self.assertIn("[A]letra", out)
        self.assertIn("Transposto +2", out)


class EndToEndFixtureTest(unittest.TestCase):
    def test_fixture_renders(self):
        song = parse_print_page(FIXTURE.read_text(encoding="utf-8"), url="https://exemplo/")
        out = song_to_chordpro(song, chorus_directives=True)
        self.assertIn("{title: Cifra De Teste}", out)
        self.assertIn("{capo: 2}", out)
        self.assertIn("{start_of_chorus: Refrão}", out)
        self.assertIn("{start_of_tab}", out)
        self.assertIn("[G]Numero um", out)
        self.assertIn("[Am7]", out)
        # nenhum colchete desemparelhado
        self.assertEqual(out.count("["), out.count("]"))
        # nada de rótulo de seção virando acorde
        self.assertNotIn("[Primeira Parte]", out)


if __name__ == "__main__":
    unittest.main()
