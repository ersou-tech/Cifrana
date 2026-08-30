"""Interface gráfica do Cifrana (Tkinter/ttk).

Fluxo pensado para quem não quer saber de terminal: busca a música pelo nome,
monta uma fila, escolhe a pasta e exporta. Todo trabalho de rede acontece em
uma thread separada; a interface é atualizada por uma fila de mensagens.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:  # pragma: no cover - depende do ambiente
    raise SystemExit(
        "A interface gráfica precisa do Tkinter.\n"
        "No Linux Mint/Ubuntu instale com:\n\n"
        "    sudo apt install python3-tk\n"
    ) from exc

from . import __version__
from .chordpro import song_to_chordpro
from .exporter import build_filename, make_zip, write_song
from .fetcher import Fetcher, FetchError
from .parser import ParseError, parse_artist_page, parse_print_page
from .search import SearchError, SearchResult, search
from .urls import InvalidURL, artist_slug, artist_url, print_url, song_url

APP_NAME = "Cifrana"
SUBTITLE = "Cifras do CifraClub prontas para o SongbookPro"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cifrana"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "cifrana"

DEFAULT_OUT = str(Path.home() / "Cifras")

TRANSPOSE_VALUES = [f"{n:+d}" if n else "0" for n in range(-11, 12)]


@dataclass
class QueueItem:
    """Uma música esperando para ser exportada."""

    label: str
    artist: str
    url: str


class CifranaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.messages: queue.Queue = queue.Queue()
        self.results: list[SearchResult] = []
        self.items: list[QueueItem] = []
        self.busy = False
        self.last_out_dir = Path(DEFAULT_OUT)

        root.title(f"{APP_NAME} — {SUBTITLE}")
        root.geometry("1020x760")
        root.minsize(940, 660)
        self._apply_theme()
        self._build_widgets()
        self._load_config()
        self._refresh_buttons()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(80, self._pump)

    # ------------------------------------------------------------------
    # aparência
    # ------------------------------------------------------------------
    def _apply_theme(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Titulo.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("Sub.TLabel", foreground="#5a5a5a")
        style.configure("Acao.TButton", font=("TkDefaultFont", 10, "bold"), padding=8)
        style.configure("Treeview", rowheight=24)

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        # -- cabeçalho ---------------------------------------------------
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text=APP_NAME, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(header, text=SUBTITLE, style="Sub.TLabel").pack(anchor="w")

        # -- busca -------------------------------------------------------
        search_box = ttk.LabelFrame(outer, text=" 1. Procure a música ", padding=10)
        search_box.grid(row=1, column=0, sticky="ew")
        search_box.columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        entry = ttk.Entry(search_box, textvariable=self.search_var, font=("TkDefaultFont", 11))
        entry.grid(row=0, column=0, sticky="ew", ipady=4)
        entry.bind("<Return>", lambda _e: self.do_search())
        entry.focus_set()
        self.search_entry = entry

        self.search_button = ttk.Button(search_box, text="Buscar", command=self.do_search)
        self.search_button.grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            search_box,
            text="Digite o nome da música ou do artista — ou cole um link do CifraClub.",
            style="Sub.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # -- listas ------------------------------------------------------
        lists = ttk.Frame(outer)
        lists.grid(row=2, column=0, sticky="nsew", pady=10)
        lists.columnconfigure(0, weight=3, minsize=340)
        lists.columnconfigure(2, weight=2, minsize=280)
        lists.rowconfigure(0, weight=1)

        self._build_results(lists)
        self._build_middle_buttons(lists)
        self._build_queue(lists)

        # -- opções ------------------------------------------------------
        self._build_options(outer)

        # -- ação e progresso -------------------------------------------
        self._build_actions(outer)

    def _build_results(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" 2. Resultados da busca ", padding=8)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        columns = ("musica", "artista")
        tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="extended", height=11)
        tree.heading("musica", text="Música")
        tree.heading("artista", text="Artista")
        tree.column("musica", width=200, anchor="w")
        tree.column("artista", width=210, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        tree.bind("<Double-1>", self._on_result_activate)
        tree.tag_configure("artista", foreground="#1a5fb4")

        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        self.results_tree = tree

        ttk.Label(
            box,
            text="Dois cliques adicionam a música.",
            style="Sub.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_middle_buttons(self, parent: ttk.Frame) -> None:
        middle = ttk.Frame(parent)
        middle.grid(row=0, column=1, padx=10)  # sem sticky: fica centralizado
        self.add_button = ttk.Button(middle, text="Adicionar  ▶", command=self.add_selected)
        self.add_button.pack(fill="x", pady=4)
        self.add_all_button = ttk.Button(middle, text="Adicionar todas", command=self.add_all)
        self.add_all_button.pack(fill="x", pady=4)

    def _build_queue(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" 3. Fila de exportação ", padding=8)
        box.grid(row=0, column=2, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        tree = ttk.Treeview(box, columns=("item",), show="headings", selectmode="extended", height=11)
        tree.heading("item", text="Música")
        tree.column("item", width=240, anchor="w")
        tree.grid(row=0, column=0, sticky="nsew")
        tree.bind("<Delete>", lambda _e: self.remove_selected())

        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        self.queue_tree = tree

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.remove_button = ttk.Button(buttons, text="Remover", command=self.remove_selected)
        self.remove_button.pack(side="left")
        self.clear_button = ttk.Button(buttons, text="Limpar fila", command=self.clear_queue)
        self.clear_button.pack(side="left", padx=6)
        self.queue_label = ttk.Label(buttons, text="vazia", style="Sub.TLabel")
        self.queue_label.pack(side="right", padx=(6, 0))

    def _build_options(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" 4. Onde salvar e como ", padding=10)
        box.grid(row=3, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Pasta:").grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        ttk.Entry(box, textvariable=self.out_var).grid(row=0, column=1, sticky="ew", padx=8)
        self.choose_button = ttk.Button(box, text="Escolher…", command=self.choose_folder)
        self.choose_button.grid(row=0, column=2)

        options = ttk.Frame(box)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.tabs_var = tk.BooleanVar(value=True)
        self.chorus_var = tk.BooleanVar(value=True)
        self.source_var = tk.BooleanVar(value=True)
        self.zip_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(options, text="Incluir tablaturas", variable=self.tabs_var).pack(side="left")
        ttk.Checkbutton(options, text="Marcar refrões", variable=self.chorus_var).pack(
            side="left", padx=12
        )
        ttk.Checkbutton(options, text="Anotar a fonte", variable=self.source_var).pack(side="left")
        ttk.Checkbutton(options, text="Gerar .zip", variable=self.zip_var).pack(side="left", padx=12)

        ttk.Label(options, text="Transpor:").pack(side="left", padx=(12, 4))
        self.transpose_var = tk.StringVar(value="0")
        ttk.Combobox(
            options,
            textvariable=self.transpose_var,
            values=TRANSPOSE_VALUES,
            width=4,
            state="readonly",
        ).pack(side="left")
        ttk.Label(options, text="semitons", style="Sub.TLabel").pack(side="left", padx=(4, 0))

    def _build_actions(self, parent: ttk.Frame) -> None:
        box = ttk.Frame(parent)
        box.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        box.columnconfigure(0, weight=1)

        buttons = ttk.Frame(box)
        buttons.grid(row=0, column=0, sticky="ew")
        self.export_button = ttk.Button(
            buttons, text="Baixar e exportar", style="Acao.TButton", command=self.do_export
        )
        self.export_button.pack(side="left")
        self.open_button = ttk.Button(buttons, text="Abrir pasta", command=self.open_folder)
        self.open_button.pack(side="left", padx=8)
        ttk.Label(buttons, text=f"v{__version__}", style="Sub.TLabel").pack(side="right")

        self.progress = ttk.Progressbar(box, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 4))

        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(box, textvariable=self.status_var).grid(row=2, column=0, sticky="w")

        log_frame = ttk.Frame(box)
        log_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=5, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="ew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

    # ------------------------------------------------------------------
    # comunicação thread -> interface
    # ------------------------------------------------------------------
    def _post(self, kind: str, payload=None) -> None:
        self.messages.put((kind, payload))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                handler = getattr(self, f"_on_{kind}", None)
                if handler:
                    handler(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _on_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_status(self, text: str) -> None:
        self.status_var.set(text)

    def _on_progress(self, payload) -> None:
        done, total = payload
        self.progress.configure(maximum=max(total, 1), value=done)

    def _on_results(self, results: list[SearchResult]) -> None:
        self.results = results
        self.results_tree.delete(*self.results_tree.get_children())
        for index, result in enumerate(results):
            if result.is_song:
                values = (result.title, result.artist)
                tags = ()
            else:
                values = (f"▸ {result.title}", "todas as músicas")
                tags = ("artista",)
            self.results_tree.insert("", "end", iid=str(index), values=values, tags=tags)
        if not results:
            self._on_status("Nada encontrado. Tente outro termo.")

    def _on_busy(self, busy: bool) -> None:
        self.busy = busy
        self._refresh_buttons()
        if busy:
            self.root.configure(cursor="watch")
        else:
            self.root.configure(cursor="")

    def _on_error(self, text: str) -> None:
        self._on_log(f"  ✗ {text}")
        messagebox.showerror(APP_NAME, text, parent=self.root)

    def _on_queue_add(self, items: list[QueueItem]) -> None:
        self.add_items(items)

    # ------------------------------------------------------------------
    # ações
    # ------------------------------------------------------------------
    def _run(self, target, *args) -> None:
        def wrapper():
            try:
                target(*args)
            except Exception:  # pragma: no cover - salvaguarda
                self._post("error", traceback.format_exc(limit=2))
            finally:
                self._post("busy", False)

        self._post("busy", True)
        threading.Thread(target=wrapper, daemon=True).start()

    def _refresh_buttons(self) -> None:
        state = "disabled" if self.busy else "normal"
        for widget in (
            self.search_button,
            self.add_button,
            self.add_all_button,
            self.remove_button,
            self.clear_button,
            self.choose_button,
            self.export_button,
        ):
            widget.configure(state=state)
        if not self.busy and not self.items:
            self.export_button.configure(state="disabled")
        total = len(self.items)
        self.queue_label.configure(text="vazia" if not total else f"{total} na fila")

    def _fetcher(self, delay: float = 1.0) -> Fetcher:
        return Fetcher(cache_dir=CACHE_DIR, delay=delay)

    # -- busca ---------------------------------------------------------
    def do_search(self) -> None:
        term = self.search_var.get().strip()
        if not term or self.busy:
            return

        if "cifraclub.com.br" in term:
            self._add_pasted_url(term)
            return

        self._on_status(f"Buscando “{term}”…")
        self._run(self._search_worker, term)

    def _add_pasted_url(self, raw: str) -> None:
        try:
            url = song_url(raw)
        except InvalidURL:
            try:
                slug = artist_slug(raw)
            except InvalidURL as exc:
                self._on_error(str(exc))
                return
            self._on_status(f"Buscando músicas de {slug}…")
            self._run(self._artist_worker, slug)
            return

        artist, title = url.rstrip("/").split("/")[-2:]
        self.add_items([QueueItem(f"{title} — {artist}", artist, url)])
        self.search_var.set("")
        self._on_status("Link adicionado à fila.")

    def _search_worker(self, term: str) -> None:
        try:
            results = search(term, self._fetcher(delay=0.0))
        except (SearchError, FetchError) as exc:
            self._post("error", f"Busca falhou: {exc}")
            return
        self._post("results", results)
        songs = sum(1 for r in results if r.is_song)
        self._post("status", f"{songs} música(s) e {len(results) - songs} artista(s) encontrados.")

    def _artist_worker(self, slug: str) -> None:
        fetcher = self._fetcher(delay=0.5)
        try:
            page = fetcher.get(artist_url(slug))
        except FetchError as exc:
            self._post("error", f"Não consegui abrir a página do artista: {exc}")
            return
        urls = parse_artist_page(page, slug)
        if not urls:
            self._post("status", f"Nenhuma música listada na página de {slug}.")
            return
        results = [
            SearchResult("musica", url.rstrip("/").split("/")[-1].replace("-", " ").title(),
                         slug.replace("-", " ").title(), slug, url.rstrip("/").split("/")[-1])
            for url in urls
        ]
        self._post("results", results)
        self._post("status", f"{len(results)} música(s) de {slug}. Selecione e adicione.")

    def _on_result_activate(self, _event) -> None:
        selection = self.results_tree.selection()
        if not selection:
            return
        result = self.results[int(selection[0])]
        if result.is_song:
            self.add_selected()
        else:
            self._on_status(f"Buscando músicas de {result.title}…")
            self._run(self._artist_worker, result.artist_slug)

    # -- fila ----------------------------------------------------------
    def _selected_results(self) -> list[SearchResult]:
        return [self.results[int(iid)] for iid in self.results_tree.selection()]

    def add_selected(self) -> None:
        chosen = self._selected_results()
        if not chosen:
            self._on_status("Selecione uma música na lista de resultados.")
            return
        songs = [r for r in chosen if r.is_song]
        for artist in (r for r in chosen if not r.is_song):
            self._on_status(f"Buscando músicas de {artist.title}…")
            self._run(self._artist_worker, artist.artist_slug)
        self.add_items([QueueItem(r.label, r.artist, r.url) for r in songs])

    def add_all(self) -> None:
        songs = [r for r in self.results if r.is_song]
        if not songs:
            self._on_status("Não há músicas nos resultados para adicionar.")
            return
        self.add_items([QueueItem(r.label, r.artist, r.url) for r in songs])

    def add_items(self, items: list[QueueItem]) -> None:
        known = {item.url for item in self.items}
        added = 0
        for item in items:
            if item.url in known:
                continue
            known.add(item.url)
            self.items.append(item)
            self.queue_tree.insert("", "end", iid=item.url, values=(item.label,))
            added += 1
        if added:
            self._on_status(f"{added} música(s) adicionada(s) à fila.")
        elif items:
            self._on_status("Essas músicas já estavam na fila.")
        self._refresh_buttons()

    def remove_selected(self) -> None:
        for iid in self.queue_tree.selection():
            self.queue_tree.delete(iid)
            self.items = [item for item in self.items if item.url != iid]
        self._refresh_buttons()

    def clear_queue(self) -> None:
        self.queue_tree.delete(*self.queue_tree.get_children())
        self.items.clear()
        self._refresh_buttons()

    # -- pasta ---------------------------------------------------------
    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Onde salvar as cifras", initialdir=self.out_var.get() or DEFAULT_OUT
        )
        if chosen:
            self.out_var.set(chosen)

    def open_folder(self) -> None:
        path = Path(self.out_var.get() or DEFAULT_OUT).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self._on_error(f"Não consegui abrir a pasta: {exc}")

    # -- exportação ----------------------------------------------------
    def do_export(self) -> None:
        if self.busy or not self.items:
            return
        out_dir = Path(self.out_var.get() or DEFAULT_OUT).expanduser()
        settings = {
            "transpose": int(self.transpose_var.get() or 0),
            "chorus": self.chorus_var.get(),
            "tabs": self.tabs_var.get(),
            "source": self.source_var.get(),
            "zip": self.zip_var.get(),
        }
        self._save_config()
        self.progress.configure(value=0, maximum=len(self.items))
        self._on_log(f"— exportando {len(self.items)} música(s) para {out_dir}")
        self._run(self._export_worker, list(self.items), out_dir, settings)

    def _export_worker(self, items: list[QueueItem], out_dir: Path, settings: dict) -> None:
        fetcher = self._fetcher(delay=1.0)
        written: list[Path] = []
        failures = 0

        for index, item in enumerate(items, start=1):
            self._post("status", f"[{index}/{len(items)}] {item.label}")
            try:
                page = fetcher.get(print_url(item.url))
                song = parse_print_page(page, url=item.url)
                content = song_to_chordpro(
                    song,
                    transpose=settings["transpose"],
                    chorus_directives=settings["chorus"],
                    keep_tabs=settings["tabs"],
                    source=settings["source"],
                )
                filename = build_filename(song)
                path = write_song(content, out_dir, filename)
                written.append(path)
                self._post("log", f"  ✓ {path.name}")
            except (FetchError, ParseError, InvalidURL) as exc:
                failures += 1
                self._post("log", f"  ✗ {item.label}: {exc}")
            self._post("progress", (index, len(items)))

        if settings["zip"] and written:
            zip_path = make_zip(written, out_dir / "cifras.zip")
            self._post("log", f"  ✓ {zip_path.name} ({len(written)} arquivos)")

        self.last_out_dir = out_dir
        summary = f"Concluído: {len(written)} exportada(s), {failures} falha(s)."
        self._post("log", f"— {summary}")
        self._post("status", summary)

    # ------------------------------------------------------------------
    # preferências
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.out_var.set(data.get("out_dir", DEFAULT_OUT))
        self.tabs_var.set(bool(data.get("tabs", True)))
        self.chorus_var.set(bool(data.get("chorus", True)))
        self.source_var.set(bool(data.get("source", True)))
        self.zip_var.set(bool(data.get("zip", False)))
        transpose = str(data.get("transpose", "0"))
        if transpose in TRANSPOSE_VALUES:
            self.transpose_var.set(transpose)

    def _save_config(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "out_dir": self.out_var.get(),
            "tabs": self.tabs_var.get(),
            "chorus": self.chorus_var.get(),
            "source": self.source_var.get(),
            "zip": self.zip_var.get(),
            "transpose": self.transpose_var.get(),
        }
        try:
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _on_close(self) -> None:
        self._save_config()
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    CifranaApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
