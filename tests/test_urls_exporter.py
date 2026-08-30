import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest
import zipfile

from cifrana.exporter import build_filename, make_zip, safe_filename, unique_path, write_song
from cifrana.model import Song
from cifrana.urls import InvalidURL, artist_slug, print_url, song_url, split_song


class UrlTest(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(
            split_song("https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/"),
            ("legiao-urbana", "tempo-perdido"),
        )

    def test_slug_pair(self):
        self.assertEqual(split_song("legiao-urbana/tempo-perdido"), ("legiao-urbana", "tempo-perdido"))

    def test_extra_segments_are_ignored(self):
        for url in (
            "https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/imprimir.html",
            "https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/simplificada.html",
            "https://m.cifraclub.com.br/legiao-urbana/tempo-perdido/#tab",
            "https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/?instrument=guitar",
        ):
            self.assertEqual(split_song(url), ("legiao-urbana", "tempo-perdido"), url)

    def test_print_and_song_url(self):
        self.assertEqual(
            print_url("legiao-urbana/tempo-perdido"),
            "https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/imprimir.html",
        )
        self.assertEqual(
            song_url("legiao-urbana/tempo-perdido"),
            "https://www.cifraclub.com.br/legiao-urbana/tempo-perdido/",
        )

    def test_rejects_other_sites(self):
        with self.assertRaises(InvalidURL):
            split_song("https://exemplo.com/algum/caminho/")

    def test_rejects_incomplete_path(self):
        with self.assertRaises(InvalidURL):
            split_song("legiao-urbana")

    def test_artist_slug(self):
        self.assertEqual(artist_slug("https://www.cifraclub.com.br/legiao-urbana/"), "legiao-urbana")


class FilenameTest(unittest.TestCase):
    def test_invalid_characters_are_replaced(self):
        self.assertEqual(safe_filename('a/b:c*d?"e|f'), "a-b-c-d--e-f")

    def test_ascii_mode(self):
        self.assertEqual(safe_filename("Legião Urbana", ascii_only=True), "Legiao Urbana")

    def test_windows_reserved_names(self):
        self.assertTrue(safe_filename("CON").startswith("_"))

    def test_build_filename_template(self):
        song = Song(title="Tempo Perdido", artist="Legião Urbana", key="Em")
        self.assertEqual(build_filename(song), "Legião Urbana - Tempo Perdido.cho")
        self.assertEqual(
            build_filename(song, "{title} ({key})", ".pro"),
            "Tempo Perdido (Em).pro",
        )

    def test_build_filename_with_bad_template_falls_back(self):
        song = Song(title="T", artist="A")
        self.assertEqual(build_filename(song, "{nao_existe}"), "A - T.cho")


class WriteTest(unittest.TestCase):
    def test_write_and_avoid_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = write_song("{title: A}\n", out, "a.cho")
            second = write_song("{title: B}\n", out, "a.cho")
            self.assertEqual(first.name, "a.cho")
            self.assertEqual(second.name, "a (2).cho")
            self.assertEqual(first.read_text(encoding="utf-8"), "{title: A}\n")

    def test_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_song("um\n", out, "a.cho")
            write_song("dois\n", out, "a.cho", overwrite=True)
            self.assertEqual((out / "a.cho").read_text(encoding="utf-8"), "dois\n")
            self.assertFalse((out / "a (2).cho").exists())

    def test_unique_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.cho"
            self.assertEqual(unique_path(path), path)

    def test_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            files = [write_song("a\n", out, "a.cho"), write_song("b\n", out, "b.cho")]
            archive = make_zip(files, out / "pacote.zip")
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(sorted(zf.namelist()), ["a.cho", "b.cho"])


if __name__ == "__main__":
    unittest.main()
