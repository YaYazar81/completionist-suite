"""Diagramme mit matplotlib, eingebettet in die Tk-Oberfläche.

matplotlib braucht beim ersten Import einen Moment. Die App lädt dieses Modul
deshalb erst, wenn das Fenster schon steht (siehe ``QROnlineApp._build_charts``).
"""
from __future__ import annotations

import customtkinter as ctk
import matplotlib

matplotlib.use("TkAgg")
from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

ACCENT = "#3B82F6"
ACCENT_HOVER = "#1D4ED8"
CARD = ("#FFFFFF", "#333333")  # Kartenfarbe hell/dunkel, auch fuer die Kennzahlen
COLORS = {"Light": {"bg": CARD[0], "text": "#1F2937", "muted": "#6B7280", "grid": "#E5E7EB",
                    "tip": "#FFFFFF"},
          "Dark": {"bg": CARD[1], "text": "#E5E7EB", "muted": "#9CA3AF", "grid": "#3F3F46",
                   "tip": "#1F1F1F"}}


def _font() -> list[str]:
    available = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in ("Segoe UI", "Inter", "Arial") if f in available] + ["DejaVu Sans"]


matplotlib.rcParams.update({"font.family": "sans-serif", "font.sans-serif": _font(),
                            "font.size": 9})


def palette() -> dict:
    return COLORS["Dark" if ctk.get_appearance_mode() == "Dark" else "Light"]


class Chart(ctk.CTkFrame):
    """Balkendiagramm: senkrecht (Verlauf) oder waagerecht (Anteile in %), mit Tooltip."""

    def __init__(self, master, title: str, horizontal: bool = False, height: int = 190):
        super().__init__(master, fg_color=CARD, corner_radius=12, height=height)
        self.heading = ctk.CTkLabel(self, text=title, anchor="w",
                                    font=ctk.CTkFont(size=13, weight="bold"))
        self.heading.pack(fill="x", padx=14, pady=(10, 0))
        self.horizontal = horizontal
        self.items: list[tuple[str, int]] = []
        self.label_every = 1
        self.fig = Figure(dpi=self.winfo_fpixels("1i"), layout="constrained")
        self.ax = self.fig.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        widget = self.canvas.get_tk_widget()
        widget.configure(height=height, highlightthickness=0, bd=0)
        widget.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.bars = None
        self.tip = None
        self.canvas.mpl_connect("motion_notify_event", self._hover)
        self.canvas.mpl_connect("figure_leave_event", lambda _e: self._highlight(None))
        self._mode = ctk.get_appearance_mode()
        self.after(1000, self._watch_mode)
        self.redraw()

    @property
    def title(self) -> str:
        return self.heading.cget("text")

    @title.setter
    def title(self, text: str) -> None:
        self.heading.configure(text=text)

    def set_data(self, items: list[tuple[str, int]], label_every: int = 1) -> None:
        self.items = items
        self.label_every = max(1, label_every)
        self.redraw()

    def _watch_mode(self) -> None:
        # Hell/Dunkel nach Windows-Einstellung: bei Wechsel neu zeichnen
        mode = ctk.get_appearance_mode()
        if mode != self._mode:
            self._mode = mode
            self.redraw()
        self.after(1000, self._watch_mode)

    def redraw(self) -> None:
        c = palette()
        ax = self.ax
        ax.clear()
        self.fig.set_facecolor(c["bg"])
        ax.set_facecolor(c["bg"])
        self.canvas.get_tk_widget().configure(bg=c["bg"])
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(c["grid"])
        ax.tick_params(colors=c["muted"], length=0)
        self.bars, self.tip = None, None
        values = [n for _, n in self.items]
        if not any(values):
            ax.set_xticks([])
            ax.set_yticks([])
            ax.spines["bottom"].set_visible(False)
            ax.text(0.5, 0.45, "Noch keine Scans", transform=ax.transAxes, ha="center",
                    va="center", color=c["muted"], fontsize=10)
            self.canvas.draw_idle()
            return
        labels = [label for label, _ in self.items]
        if self.horizontal:
            self._draw_horizontal(labels, values, c)
        else:
            self._draw_vertical(labels, values, c)
        self.tip = ax.annotate("", xy=(0, 0), xytext=(0, 10), textcoords="offset points",
                               ha="center", va="bottom", color=c["text"], fontsize=9,
                               bbox={"boxstyle": "round,pad=0.4", "fc": c["tip"], "ec": c["grid"]},
                               annotation_clip=False, zorder=10)
        self.tip.set_visible(False)
        self.canvas.draw_idle()

    def _draw_vertical(self, labels, values, c) -> None:
        ax = self.ax
        x = range(len(values))
        self.bars = ax.bar(x, values, width=0.72, color=ACCENT, zorder=3)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        ax.grid(axis="y", color=c["grid"], linewidth=0.8, zorder=0)
        ax.set_xticks([i for i in x if i % self.label_every == 0],
                      [labels[i] for i in x if i % self.label_every == 0])
        ax.set_xlim(-0.6, len(values) - 0.4)
        ax.set_ylim(0, max(values) * 1.12)

    def _draw_horizontal(self, labels, values, c) -> None:
        ax = self.ax
        total = sum(values)
        y = range(len(values))
        self.bars = ax.barh(y, values, height=0.62, color=ACCENT, zorder=3)
        ax.set_yticks(list(y), labels, color=c["text"])
        # Immer Platz fuer mindestens 5 Zeilen: gleich dicke Balken, groesster Wert oben
        ax.set_ylim(max(len(values), 5) - 0.5, -0.5)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_xlim(0, max(values) * 1.9)  # rechts Platz fuer „84 %  (302)“
        for i, n in enumerate(values):
            ax.text(n, i, f"  {100 * n / total:.0f} %  ({n})", va="center", color=c["muted"])

    def _hover(self, event) -> None:
        if self.bars is None or event.inaxes is not self.ax:
            self._highlight(None)
            return
        for i, bar in enumerate(self.bars):
            if bar.contains(event)[0]:
                self._highlight(i)
                return
        self._highlight(None)

    def _highlight(self, index: int | None) -> None:
        if self.bars is None or self.tip is None:
            return
        for i, bar in enumerate(self.bars):
            bar.set_color(ACCENT_HOVER if i == index else ACCENT)
        if index is None or self.horizontal:  # waagerecht steht die Zahl schon am Balken
            self.tip.set_visible(False)
        else:
            label, n = self.items[index]
            bar = self.bars[index]
            self.tip.xy = (bar.get_x() + bar.get_width() / 2, bar.get_height())
            self.tip.set_text(f"{label} · {n} {'Scan' if n == 1 else 'Scans'}")
            self.tip.set_visible(True)
        self.canvas.draw_idle()
