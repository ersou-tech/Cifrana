"""Interface gráfica do Cifrana (Tkinter/ttk).

Fluxo pensado para quem não quer saber de terminal: busca a música pelo nome,
monta uma fila, escolhe a pasta e exporta. Todo trabalho de rede acontece em
uma thread separada; a interface é atualizada por uma fila de mensagens.
"""

from __future__ import annotations

import bisect
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
    from tkinter import filedialog, font as tkfont, messagebox, ttk
except ImportError as exc:  # pragma: no cover - depende do ambiente
    raise SystemExit(
        "A interface gráfica precisa do Tkinter.\n"
        "No Linux Mint/Ubuntu instale com:\n\n"
        "    sudo apt install python3-tk\n"
    ) from exc

from . import __version__, highlight
from .convert import Options, fetch_and_render
from .exporter import make_zip, safe_filename, write_song
from .fetcher import Fetcher, FetchError
from .parser import ParseError, parse_artist_page
from .search import SearchError, SearchResult, search
from .urls import InvalidURL, artist_slug, artist_url, song_url

APP_NAME = "Cifrana"
SUBTITLE = "Cifras do CifraClub prontas para o SongbookPro"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cifrana"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "cifrana"

DEFAULT_OUT = str(Path.home() / "Cifras")

TRANSPOSE_VALUES = [f"{n:+d}" if n else "0" for n in range(-11, 12)]


@dataclass
class QueueItem:
    """Uma música esperando para ser exportada.

    Enquanto ``content`` for ``None``, a cifra ainda será baixada e convertida
    na hora de exportar. Depois de aberta no editor, ``content`` guarda o texto
    ChordPro — editado ou não — e é ele que vai para o arquivo.
    """

    label: str
    artist: str
    url: str
    content: str | None = None
    filename: str | None = None
    edited: bool = False

    @property
    def state_label(self) -> str:
        if self.edited:
            return "editada"
        return "revisada" if self.content else ""


class CifranaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.messages: queue.Queue = queue.Queue()
        self.results: list[SearchResult] = []
        self.items: list[QueueItem] = []
        self.editors: dict[str, "EditorCifra"] = {}
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
        self.queue_box = box
        box.grid(row=0, column=2, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            box, columns=("item", "estado"), show="headings", selectmode="extended", height=11
        )
        tree.heading("item", text="Música")
        tree.heading("estado", text="")
        tree.column("item", width=190, anchor="w")
        tree.column("estado", width=70, anchor="e", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        tree.bind("<Delete>", lambda _e: self.remove_selected())
        tree.bind("<Double-1>", lambda _e: self.open_editor())
        tree.tag_configure("editada", foreground="#1a5fb4")

        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        self.queue_tree = tree

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.edit_button = ttk.Button(buttons, text="Ver / editar", command=self.open_editor)
        self.edit_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text="Remover", command=self.remove_selected)
        self.remove_button.pack(side="left", padx=6)
        self.clear_button = ttk.Button(buttons, text="Limpar", command=self.clear_queue)
        self.clear_button.pack(side="left")


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
            self.edit_button,
            self.remove_button,
            self.clear_button,
            self.choose_button,
            self.export_button,
        ):
            widget.configure(state=state)
        if not self.busy and not self.items:
            self.export_button.configure(state="disabled")
        total = len(self.items)
        quantidade = "vazia" if not total else f"{total} música{'s' if total > 1 else ''}"
        self.queue_box.configure(text=f" 3. Fila de exportação — {quantidade} ")

    def _fetcher(self, delay: float = 1.0) -> Fetcher:
        return Fetcher(cache_dir=CACHE_DIR, delay=delay)

    def _options(self) -> Options:
        """As escolhas atuais da janela, do jeito que a conversão espera."""

        return Options(
            transpose=int(self.transpose_var.get() or 0),
            chorus=self.chorus_var.get(),
            tabs=self.tabs_var.get(),
            source=self.source_var.get(),
        )

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
            self.queue_tree.insert("", "end", iid=item.url, values=(item.label, ""))
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

    # -- editor --------------------------------------------------------
    def open_editor(self) -> None:
        if self.busy:
            return
        selecionadas = self.queue_tree.selection()
        if not selecionadas:
            self._on_status("Selecione uma música da fila para ver ou editar.")
            return

        item = next((i for i in self.items if i.url == selecionadas[0]), None)
        if item is None:
            return
        if item.content is not None:
            self._mostrar_editor(item)
            return

        self._on_status(f"Baixando {item.label} para edição…")
        self._run(self._preview_worker, item)

    def _preview_worker(self, item: QueueItem) -> None:
        try:
            convertida = fetch_and_render(item.url, self._fetcher(delay=0.5), self._options())
        except (FetchError, ParseError, InvalidURL) as exc:
            self._post("error", f"Não consegui abrir {item.label}: {exc}")
            return
        self._post("editor", (item, convertida))

    def _on_editor(self, payload) -> None:
        item, convertida = payload
        item.content = convertida.content
        item.filename = convertida.filename
        self.refresh_item(item)
        self._on_status(f"{item.label} pronta para revisão.")
        self._mostrar_editor(item)

    def _mostrar_editor(self, item: QueueItem) -> None:
        janela = self.editors.get(item.url)
        if janela is not None and janela.winfo_exists():
            janela.lift()
            janela.focus_set()
            return
        self.editors[item.url] = EditorCifra(self, item)

    def refresh_item(self, item: QueueItem) -> None:
        """Reflete na fila o estado atual de uma música."""

        if self.queue_tree.exists(item.url):
            self.queue_tree.item(
                item.url,
                values=(item.label, item.state_label),
                tags=("editada",) if item.edited else (),
            )

    def recarregar_item(self, item: QueueItem) -> None:
        """Joga fora o texto atual e baixa a cifra de novo."""

        item.content = None
        item.filename = None
        item.edited = False
        self.refresh_item(item)
        self._on_status(f"Recarregando {item.label}…")
        self._run(self._reload_worker, item)

    def _reload_worker(self, item: QueueItem) -> None:
        try:
            convertida = fetch_and_render(
                item.url, self._fetcher(delay=0.5), self._options()
            )
        except (FetchError, ParseError, InvalidURL) as exc:
            self._post("error", f"Não consegui recarregar {item.label}: {exc}")
            return
        self._post("reloaded", (item, convertida))

    def _on_reloaded(self, payload) -> None:
        item, convertida = payload
        item.content = convertida.content
        item.filename = convertida.filename
        item.edited = False
        self.refresh_item(item)
        janela = self.editors.get(item.url)
        if janela is not None and janela.winfo_exists():
            janela.substituir_texto(convertida.content, convertida.filename)
        self._on_status(f"{item.label} recarregada do site.")

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
        self._save_config()
        self.progress.configure(value=0, maximum=len(self.items))
        self._on_log(f"— exportando {len(self.items)} música(s) para {out_dir}")
        self._run(
            self._export_worker, list(self.items), out_dir, self._options(), self.zip_var.get()
        )

    def _export_worker(
        self, items: list[QueueItem], out_dir: Path, options: Options, fazer_zip: bool
    ) -> None:
        fetcher = self._fetcher(delay=1.0)
        written: list[Path] = []
        failures = 0

        for index, item in enumerate(items, start=1):
            self._post("status", f"[{index}/{len(items)}] {item.label}")
            try:
                if item.content is not None:
                    # já revisada no editor: vai exatamente como está na tela
                    content = item.content
                    filename = item.filename or safe_filename(item.label) + options.ext
                else:
                    convertida = fetch_and_render(item.url, fetcher, options)
                    content, filename = convertida.content, convertida.filename

                path = write_song(content, out_dir, filename)
                written.append(path)
                marca = " (editada)" if item.edited else ""
                self._post("log", f"  ✓ {path.name}{marca}")
            except (FetchError, ParseError, InvalidURL) as exc:
                failures += 1
                self._post("log", f"  ✗ {item.label}: {exc}")
            self._post("progress", (index, len(items)))

        if fazer_zip and written:
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


class EditorCifra(tk.Toplevel):
    """Janela para conferir e ajustar a cifra antes de exportar.

    O texto é o próprio ChordPro que sairá no arquivo: o que estiver aqui na
    hora de salvar é exatamente o que o SongbookPro vai receber.
    """

    def __init__(self, app: "CifranaApp", item: QueueItem) -> None:
        super().__init__(app.root)
        self.app = app
        self.item = item
        self._agendado: str | None = None
        self._original = item.content or ""
        self._salvo = self._original
        self._nome_salvo = item.filename or ""

        self.title(f"Cifra — {item.label}")
        self.geometry("880x760")
        self.minsize(620, 460)

        self._build()
        self.substituir_texto(self._original, self._nome_salvo)

        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Control-s>", lambda _e: (self.salvar(), "break")[1])

    # -- montagem ------------------------------------------------------
    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text=self.item.label, style="Titulo.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        linha = ttk.Frame(outer)
        linha.grid(row=1, column=0, sticky="ew", pady=(8, 10))
        linha.columnconfigure(1, weight=1)
        ttk.Label(linha, text="Arquivo:").grid(row=0, column=0)
        self.file_var = tk.StringVar()
        entrada = ttk.Entry(linha, textvariable=self.file_var)
        entrada.grid(row=0, column=1, sticky="ew", padx=8)
        entrada.bind("<KeyRelease>", lambda _e: self._atualizar_status())

        quadro = ttk.Frame(outer)
        quadro.grid(row=2, column=0, sticky="nsew")
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(0, weight=1)

        base = tkfont.nametofont("TkFixedFont")
        fonte = tkfont.Font(family=base.cget("family"), size=11)
        self.text = tk.Text(
            quadro, wrap="none", undo=True, font=fonte, padx=8, pady=6, spacing1=1
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        vertical = ttk.Scrollbar(quadro, orient="vertical", command=self.text.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(quadro, orient="horizontal", command=self.text.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        negrito = tkfont.Font(family=base.cget("family"), size=11, weight="bold")
        self.text.tag_configure(highlight.DIRETIVA, foreground="#1a5fb4")
        self.text.tag_configure(highlight.ACORDE, foreground="#a51d2d", font=negrito)
        self.text.tag_configure(highlight.TABLATURA, foreground="#5a5a5a")
        self.text.bind("<KeyRelease>", self._ao_digitar)

        ttk.Label(
            outer,
            text=(
                "Acordes entre [colchetes] e diretivas entre {chaves} são o que o "
                "SongbookPro entende. Ctrl+Z desfaz, Ctrl+S salva."
            ),
            style="Sub.TLabel",
            wraplength=820,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        rodape = ttk.Frame(outer)
        rodape.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(rodape, text="Salvar", style="Acao.TButton", command=self.salvar).pack(
            side="left"
        )
        ttk.Button(rodape, text="Recarregar do site", command=self.recarregar).pack(
            side="left", padx=8
        )
        ttk.Button(rodape, text="Fechar", command=self.fechar).pack(side="left")
        self.status = ttk.Label(rodape, text="", style="Sub.TLabel")
        self.status.pack(side="right")

    # -- conteúdo ------------------------------------------------------
    def texto_atual(self) -> str:
        return self.text.get("1.0", "end-1c")

    def substituir_texto(self, conteudo: str, nome: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", conteudo)
        self.text.edit_reset()
        self.text.mark_set("insert", "1.0")
        self.file_var.set(nome)
        self._original = conteudo
        self._salvo = conteudo
        self._nome_salvo = nome
        self._destacar()
        self._atualizar_status()

    @property
    def alterado(self) -> bool:
        """Há mudanças ainda não salvas nesta janela?"""

        return self.texto_atual() != self._salvo or self.file_var.get().strip() != self._nome_salvo

    # -- destaque ------------------------------------------------------
    def _ao_digitar(self, _event=None) -> None:
        if self._agendado is not None:
            self.after_cancel(self._agendado)
        self._agendado = self.after(250, self._redestacar)

    def _redestacar(self) -> None:
        self._agendado = None
        self._destacar()
        self._atualizar_status()

    def _destacar(self) -> None:
        texto = self.texto_atual()
        for marcador in (highlight.DIRETIVA, highlight.ACORDE, highlight.TABLATURA):
            self.text.tag_remove(marcador, "1.0", "end")

        # deslocamento absoluto -> índice "linha.coluna" do Tk
        inicios = [0]
        for linha in texto.splitlines(keepends=True):
            inicios.append(inicios[-1] + len(linha))

        def indice(posicao: int) -> str:
            numero = bisect.bisect_right(inicios, posicao) - 1
            return f"{numero + 1}.{posicao - inicios[numero]}"

        for marcador, inicio, fim in highlight.spans(texto):
            self.text.tag_add(marcador, indice(inicio), indice(fim))

    def _atualizar_status(self) -> None:
        if self.alterado:
            self.status.configure(text="alterações não salvas")
        elif self.item.edited:
            self.status.configure(text="editada — vai assim para o arquivo")
        else:
            self.status.configure(text="igual ao site")

    # -- ações ---------------------------------------------------------
    def salvar(self) -> None:
        nome = safe_filename(self.file_var.get().strip() or self.item.label)
        if not nome.lower().endswith((".cho", ".chopro", ".chordpro", ".pro", ".crd", ".txt")):
            nome += ".cho"
        self.file_var.set(nome)

        texto = self.texto_atual()
        self.item.content = texto
        self.item.filename = nome
        self.item.edited = texto != self._original
        self._salvo = texto
        self._nome_salvo = nome

        self.app.refresh_item(self.item)
        self.app._on_status(f"{self.item.label}: alterações guardadas para a exportação.")
        self._atualizar_status()

    def recarregar(self) -> None:
        if self.alterado and not messagebox.askyesno(
            APP_NAME,
            "Baixar a cifra de novo e descartar o que você mudou aqui?",
            parent=self,
        ):
            return
        self.app.recarregar_item(self.item)

    def fechar(self) -> None:
        if self.alterado:
            resposta = messagebox.askyesnocancel(
                APP_NAME,
                "Salvar as alterações antes de fechar?",
                parent=self,
            )
            if resposta is None:
                return
            if resposta:
                self.salvar()
        self.app.editors.pop(self.item.url, None)
        self.destroy()



def main(argv: list[str] | None = None) -> int:
    root = tk.Tk()
    CifranaApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
