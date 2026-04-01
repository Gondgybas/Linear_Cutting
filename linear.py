"""
Программа линейного раскроя материала с GUI интерфейсом.
Алгоритм: First Fit Decreasing (FFD).
Интерфейс: tkinter + matplotlib.
Возможность редактирования изделий двойным кликом.
Прокрутка визуализации колёсиком мыши.
Умные подписи: если название не помещается — показывается #номер.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
from tkinter import filedialog
import matplotlib.pyplot as plt


# ─────────────────────────── Алгоритм ───────────────────────────

def ffd_cutting(usable_length, parts, kerf=0):
    """First Fit Decreasing для линейного раскроя с учётом ширины пропила."""
    pieces = []
    for p in parts:
        for _ in range(p["qty"]):
            pieces.append((p["name"], p["length"], p["id"]))

    oversized = [p for p in pieces if p[1] > usable_length]
    fitting = [p for p in pieces if p[1] <= usable_length]

    fitting.sort(key=lambda x: x[1], reverse=True)
    bins = []

    for piece_name, piece_len, piece_id in fitting:
        placed = False
        for b in bins:
            # Если уже есть изделия — нужен пропил перед новым
            needed = piece_len + (kerf if b["pieces"] else 0)
            if b["remaining"] >= needed:
                b["pieces"].append((piece_name, piece_len, piece_id))
                b["remaining"] -= needed
                placed = True
                break
        if not placed:
            bins.append({
                "remaining": usable_length - piece_len,
                "pieces": [(piece_name, piece_len, piece_id)],
            })

    return bins, oversized

def group_bins(bins):
    """
    Группирует одинаковые заготовки (с идентичным набором изделий).
    Возвращает список: [{"bin": bin_data, "count": N, "indices": [1,2,3...]}, ...]
    """
    groups = []
    for i, b in enumerate(bins):
        # Ключ — кортеж из (piece_id, length) каждого изделия + остаток
        key = tuple((pid, l) for _, l, pid in b["pieces"]) + (("rem", b["remaining"]),)
        found = False
        for g in groups:
            if g["key"] == key:
                g["count"] += 1
                g["indices"].append(i + 1)
                found = True
                break
        if not found:
            groups.append({
                "key": key,
                "bin": b,
                "count": 1,
                "indices": [i + 1],
            })
    return groups

# ─────────────────────── Окно редактирования ─────────────────────

class EditPartDialog(tk.Toplevel):
    """Модальное окно для редактирования изделия."""

    def __init__(self, parent, name, length, qty):
        super().__init__(parent)
        self.title("Редактирование изделия")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()

        self.result = None

        w, h = 340, 200
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Название:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar(value=name)
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=25)
        self.name_entry.grid(row=0, column=1, padx=(10, 0), pady=5)
        self.name_entry.focus_set()
        self.name_entry.select_range(0, tk.END)

        ttk.Label(frame, text="Длина (мм):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.length_var = tk.StringVar(value=str(length))
        ttk.Entry(frame, textvariable=self.length_var, width=25).grid(
            row=1, column=1, padx=(10, 0), pady=5
        )

        ttk.Label(frame, text="Количество:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.qty_var = tk.StringVar(value=str(qty))
        ttk.Entry(frame, textvariable=self.qty_var, width=25).grid(
            row=2, column=1, padx=(10, 0), pady=5
        )

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(15, 0))

        ttk.Button(btn_row, text="✅ Сохранить", command=self._save).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(btn_row, text="❌ Отмена", command=self.destroy).pack(side=tk.LEFT)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())

    def _save(self):
        name = self.name_var.get().strip()
        # Название может быть пустым — это допустимо
        try:
            length = float(self.length_var.get())
            if length <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Введите корректную длину!", parent=self)
            return
        try:
            qty = int(self.qty_var.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Введите корректное количество!", parent=self)
            return

        self.result = (name, length, qty)
        self.destroy()

class ImportDialog(tk.Toplevel):
    """Модальное окно для импорта изделий из текста."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Импорт изделий")
        self.resizable(True, True)
        self.grab_set()
        self.focus_set()

        self.result = None

        w, h = 520, 480
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(400, 350)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Используем grid для точного контроля размеров
        frame.rowconfigure(1, weight=1)  # текстовое поле растягивается
        frame.columnconfigure(0, weight=1)

        # Инструкция (row 0) — фиксированная высота
        hint = ttk.Label(frame, text=(
            "Формат: [Название] <длина> <количество>\n"
            "Каждая строка — одно изделие. Разделитель — пробел.\n"
            "Два последних числа — длина и количество, всё остальное — название.\n\n"
            "Примеры:\n"
            "  Стойка каркасная 1500 4\n"
            "  Перекладина 800 6\n"
            "  1200 3"
        ), justify=tk.LEFT, foreground="#555555")
        hint.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Текстовое поле (row 1) — растягивается
        text_frame = ttk.Frame(frame)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame, font=("Consolas", 11),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#ffffff",
            relief=tk.FLAT, wrap=tk.NONE, undo=True,
        )
        scroll_y = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        scroll_x = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        self.text.focus_set()

        # Статус-строка (row 2) — фиксированная
        self.status_var = tk.StringVar(value="")
        status_label = ttk.Label(frame, textvariable=self.status_var, foreground="#cc0000")
        status_label.grid(row=2, column=0, sticky="ew", pady=(5, 0))

        # Кнопки (row 3) — фиксированная
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        ttk.Button(btn_row, text="➕ Добавить", command=self._import).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(btn_row, text="❌ Отмена", command=self.destroy).pack(side=tk.LEFT)

        self.bind("<Escape>", lambda e: self.destroy())

    def _parse_line(self, line):
        """
        Парсит строку: два последних токена-числа = длина и количество,
        всё что перед ними = название (может быть пустым).
        Поддерживает запятую как десятичный разделитель (10,5 = 10.5).
        """
        line = line.strip()
        if not line:
            return None

        tokens = line.split()

        def to_float(s):
            return float(s.replace(",", "."))

        def to_int(s):
            return int(to_float(s))

        if len(tokens) < 2:
            try:
                length = to_float(tokens[0])
                return {"name": "", "length": length, "qty": 1}
            except ValueError:
                raise ValueError(f"Не удалось распознать: «{line}»")

        # Пытаемся взять два последних как числа
        try:
            qty = to_int(tokens[-1])
            length = to_float(tokens[-2])
            name = " ".join(tokens[:-2]).strip()
            if length <= 0 or qty <= 0:
                raise ValueError
            return {"name": name, "length": length, "qty": qty}
        except (ValueError, IndexError):
            pass

        # Может последний токен — только длина
        try:
            length = to_float(tokens[-1])
            if length <= 0:
                raise ValueError
            name = " ".join(tokens[:-1]).strip()
            return {"name": name, "length": length, "qty": 1}
        except ValueError:
            raise ValueError(f"Не удалось распознать: «{line}»")

    def _import(self):
        raw = self.text.get("1.0", tk.END)
        lines = raw.strip().splitlines()

        if not lines or all(not l.strip() for l in lines):
            self.status_var.set("⚠ Введите хотя бы одну строку!")
            return

        results = []
        errors = []

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                parsed = self._parse_line(line)
                if parsed:
                    results.append(parsed)
            except ValueError as e:
                errors.append(f"Строка {i}: {e}")

        if errors:
            self.status_var.set("\n".join(errors))
            return

        if not results:
            self.status_var.set("⚠ Не найдено ни одного изделия!")
            return

        self.result = results
        self.destroy()


# ──────────────── Прокручиваемый Canvas с matplotlib ────────────────

class ScrollableChart(ttk.Frame):
    """
    Фрейм с matplotlib-графиком внутри прокручиваемой области.
    Каждая заготовка имеет фиксированную высоту.
    """

    ROW_HEIGHT_PX = 60
    PADDING_TOP_PX = 80
    PADDING_BOTTOM_PX = 40
    DPI = 100

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.tk_canvas = tk.Canvas(self, bg="#fafafa", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tk_canvas.yview)
        self.tk_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tk_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner_frame = ttk.Frame(self.tk_canvas)
        self.window_id = self.tk_canvas.create_window(
            (0, 0), window=self.inner_frame, anchor=tk.NW
        )

        self.fig = None
        self.mpl_canvas = None

        self.tk_canvas.bind("<Enter>", self._bind_mousewheel)
        self.tk_canvas.bind("<Leave>", self._unbind_mousewheel)
        self.tk_canvas.bind("<Configure>", self._on_canvas_configure)
        self.inner_frame.bind("<Configure>", self._on_frame_configure)

    def _on_frame_configure(self, event=None):
        self.tk_canvas.configure(scrollregion=self.tk_canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        width = self.tk_canvas.winfo_width()
        self.tk_canvas.itemconfig(self.window_id, width=width)
        if self.fig and self.mpl_canvas:
            fig_w = width / self.DPI
            fig_h = self.fig.get_figheight()
            self.fig.set_size_inches(fig_w, fig_h)
            self.mpl_canvas.draw()
            self.mpl_canvas.get_tk_widget().configure(
                width=width, height=int(fig_h * self.DPI)
            )
            self._on_frame_configure()

    def _bind_mousewheel(self, event=None):
        self.tk_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.tk_canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.tk_canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _unbind_mousewheel(self, event=None):
        self.tk_canvas.unbind_all("<MouseWheel>")
        self.tk_canvas.unbind_all("<Button-4>")
        self.tk_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if abs(event.delta) >= 120:
            self.tk_canvas.yview_scroll(-event.delta // 120, "units")
        else:
            self.tk_canvas.yview_scroll(-event.delta, "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.tk_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.tk_canvas.yview_scroll(3, "units")

    def clear(self):
        if self.mpl_canvas:
            self.mpl_canvas.get_tk_widget().destroy()
            self.mpl_canvas = None
        if self.fig:
            import matplotlib.pyplot as plt
            plt.close(self.fig)
            self.fig = None

    def _get_text_width(self, ax, text, fontsize):
        """Вычисляет ширину текста в единицах данных оси X."""
        from matplotlib.text import Text
        renderer = self.fig.canvas.get_renderer()
        t = Text(0, 0, text, fontsize=fontsize, fontweight="bold", figure=self.fig)
        bb = t.get_window_extent(renderer=renderer)
        # Переводим пиксели в единицы данных
        inv = ax.transData.inverted()
        p0 = inv.transform((0, 0))
        p1 = inv.transform((bb.width, 0))
        return p1[0] - p0[0]

    def draw(self, material_name, stock_length, bins, margin_left=0, margin_right=0, kerf=0):
        """Отрисовать карту раскроя с группировкой одинаковых заготовок."""
        self.clear()

        groups = group_bins(bins)
        n = len(groups)

        canvas_width = max(self.tk_canvas.winfo_width(), 600)
        fig_w = canvas_width / self.DPI
        fig_h_px = self.PADDING_TOP_PX + n * self.ROW_HEIGHT_PX + self.PADDING_BOTTOM_PX
        fig_h = fig_h_px / self.DPI

        self.fig = Figure(figsize=(fig_w, fig_h), dpi=self.DPI)
        self.fig.patch.set_facecolor("#fafafa")
        ax = self.fig.add_subplot(111)

        bar_height = 0.6

        color_map = {}
        label_map = {}
        colors = [
            "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
            "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
            "#9c755f", "#bab0ac", "#6baed6", "#fd8d3c",
            "#74c476", "#9e9ac8", "#e377c2", "#17becf",
            "#bcbd22", "#7f7f7f", "#d62728", "#1f77b4",
        ]
        color_idx = 0

        ax.set_xlim(-stock_length * 0.12, stock_length * 1.05)
        ax.set_ylim(-0.8, n - 0.2 + 0.8)
        ax.set_xlabel("Длина (мм)", fontsize=10)
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        self.fig.tight_layout()

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=self.inner_frame)
        self.mpl_canvas.draw()

        text_items = []

        for i, g in enumerate(groups):
            b = g["bin"]
            count = g["count"]
            indices = g["indices"]
            y = n - 1 - i

            # Фон заготовки
            ax.add_patch(patches.FancyBboxPatch(
                (0, y - bar_height / 2), stock_length, bar_height,
                boxstyle="round,pad=0",
                linewidth=1.2, edgecolor="#555555", facecolor="#e8e8e8",
            ))

            # Припуски
            if margin_left > 0:
                ax.add_patch(patches.Rectangle(
                    (0, y - bar_height / 2), margin_left, bar_height,
                    linewidth=0.5, edgecolor="#999", facecolor="#cccccc",
                    hatch="///", alpha=0.7,
                ))
            if margin_right > 0:
                ax.add_patch(patches.Rectangle(
                    (stock_length - margin_right, y - bar_height / 2),
                    margin_right, bar_height,
                    linewidth=0.5, edgecolor="#999", facecolor="#cccccc",
                    hatch="///", alpha=0.7,
                ))

            x_offset = margin_left
            for j, (name, length, piece_id) in enumerate(b["pieces"]):
                if j > 0 and kerf > 0:
                    ax.add_patch(patches.Rectangle(
                        (x_offset, y - bar_height / 2), kerf, bar_height,
                        linewidth=0, facecolor="#ff4444", alpha=0.6,
                    ))
                    x_offset += kerf

                if piece_id not in color_map:
                    color_map[piece_id] = colors[color_idx % len(colors)]
                    color_idx += 1
                    legend_label = f"#{piece_id} {name}" if name else f"#{piece_id}"
                    label_map[piece_id] = (legend_label, color_map[piece_id])
                color = color_map[piece_id]

                ax.add_patch(patches.FancyBboxPatch(
                    (x_offset, y - bar_height / 2), length, bar_height,
                    boxstyle="round,pad=0",
                    linewidth=0.8, edgecolor="#333333", facecolor=color, alpha=0.88,
                ))

                fontsize = max(5.5, min(8.5, length / stock_length * 70))

                full_label = f"{name}\n{length:.0f}" if name else f"#{piece_id}\n{length:.0f}"
                short_label = f"#{piece_id}\n{length:.0f}"

                text_items.append({
                    "x": x_offset + length / 2,
                    "y": y,
                    "full": full_label,
                    "short": short_label,
                    "fontsize": fontsize,
                    "width": length,
                })

                x_offset += length

            remaining = b["remaining"]
            if remaining > stock_length * 0.03:
                ax.text(
                    x_offset + remaining / 2, y,
                    f"Ост.\n{remaining:.0f}",
                    ha="center", va="center",
                    fontsize=6.5, fontstyle="italic", color="#999999",
                )

            # Левая подпись: номера + количество
            if count > 1:
                # Сокращаем список номеров если слишком длинный
                if len(indices) <= 3:
                    idx_str = ",".join(str(x) for x in indices)
                else:
                    idx_str = f"{indices[0]}–{indices[-1]}"
                left_label = f"×{count}\n(#{idx_str})"
            else:
                left_label = f"#{indices[0]}"

            ax.text(
                -stock_length * 0.015, y,
                left_label, ha="right", va="center",
                fontsize=8 if count > 1 else 9,
                fontweight="bold",
                color="#cc6600" if count > 1 else "#444444",
            )

        # Умные подписи
        PADDING_FACTOR = 1.3
        for item in text_items:
            full_w = self._get_text_width(ax, item["full"].split("\n")[0], item["fontsize"])
            full_w *= PADDING_FACTOR
            label = item["full"] if full_w <= item["width"] else item["short"]
            ax.text(
                item["x"], item["y"], label,
                ha="center", va="center",
                fontsize=item["fontsize"], fontweight="bold", color="#ffffff",
            )

        # Заголовок
        total_stock = len(bins) * stock_length
        total_waste = sum(b_["remaining"] for b_ in bins)
        eff = ((total_stock - total_waste) / total_stock) * 100 if total_stock else 0

        ax.set_title(
            f"«{material_name}»  •  Заготовка: {stock_length:.0f} мм  •  "
            f"Штук: {len(bins)}  •  Уник. схем: {n}  •  Эффективность: {eff:.1f}%",
            fontsize=11, fontweight="bold", pad=12,
        )

        # Легенда
        legend_handles = [
            patches.Patch(facecolor=c, edgecolor="#333", label=lbl)
            for lbl, c in label_map.values()
        ]
        if margin_left > 0 or margin_right > 0:
            legend_handles.append(
                patches.Patch(facecolor="#cccccc", edgecolor="#999", hatch="///", label="Припуск")
            )
        if kerf > 0:
            legend_handles.append(
                patches.Patch(facecolor="#ff4444", alpha=0.6, edgecolor="none", label=f"Пропил ({kerf})")
            )
        legend_handles.append(
            patches.Patch(facecolor="#e8e8e8", edgecolor="#555", label="Остаток")
        )
        ax.legend(
            handles=legend_handles, loc="upper right",
            fontsize=8, framealpha=0.9, title="Изделия",
        )

        self.fig.tight_layout()

        widget = self.mpl_canvas.get_tk_widget()
        widget.configure(width=canvas_width, height=fig_h_px)
        widget.pack(fill=tk.X, expand=False)
        self.mpl_canvas.draw()

        self.inner_frame.update_idletasks()
        self._on_frame_configure()
        self.tk_canvas.yview_moveto(0)

    def show_placeholder(self):
        self.clear()
        canvas_width = max(self.tk_canvas.winfo_width(), 600)
        fig_w = canvas_width / self.DPI

        self.fig = Figure(figsize=(fig_w, 3), dpi=self.DPI)
        self.fig.patch.set_facecolor("#fafafa")
        ax = self.fig.add_subplot(111)
        ax.text(
            0.5, 0.5, "Добавьте изделия и нажмите\n«РАССЧИТАТЬ РАСКРОЙ»",
            ha="center", va="center", fontsize=14, color="#999999",
            transform=ax.transAxes
        )
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=self.inner_frame)
        widget = self.mpl_canvas.get_tk_widget()
        widget.configure(width=canvas_width, height=300)
        widget.pack(fill=tk.X, expand=False)
        self.mpl_canvas.draw()
        self.inner_frame.update_idletasks()
        self._on_frame_configure()


# ─────────────────────────── GUI ───────────────────────────

class CuttingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Линейный раскрой материала")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg="#f0f0f0")

        self.parts = []
        self.next_id = 1  # счётчик номеров изделий

        self._build_ui()

    def _build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ──── Левая панель ────
        left = ttk.Frame(main, width=400)
        main.add(left, weight=0)

        # --- Материал ---
        mat_frame = ttk.LabelFrame(left, text=" 📦 Материал ", padding=10)
        mat_frame.pack(fill=tk.X, padx=5, pady=(5, 10))

        ttk.Label(mat_frame, text="Название:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.material_name_var = tk.StringVar(value="Труба профильная")
        ttk.Entry(mat_frame, textvariable=self.material_name_var, width=28).grid(
            row=0, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(mat_frame, text="Длина заготовки (мм):").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.stock_length_var = tk.StringVar(value="6000")
        ttk.Entry(mat_frame, textvariable=self.stock_length_var, width=28).grid(
            row=1, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(mat_frame, text="Припуск слева (мм):").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.margin_left_var = tk.StringVar(value="0")
        ttk.Entry(mat_frame, textvariable=self.margin_left_var, width=28).grid(
            row=2, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(mat_frame, text="Припуск справа (мм):").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.margin_right_var = tk.StringVar(value="0")
        ttk.Entry(mat_frame, textvariable=self.margin_right_var, width=28).grid(
            row=3, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(mat_frame, text="Ширина пропила (мм):").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.kerf_var = tk.StringVar(value="0")
        ttk.Entry(mat_frame, textvariable=self.kerf_var, width=28).grid(
            row=4, column=1, padx=(5, 0), pady=3
        )

        # Добавление изделия
        add_frame = ttk.LabelFrame(left, text=" ✏️ Добавить изделие ", padding=10)
        add_frame.pack(fill=tk.X, padx=5, pady=(0, 10))

        ttk.Label(add_frame, text="Название:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.part_name_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.part_name_var, width=28).grid(
            row=0, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(add_frame, text="Длина (мм):").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.part_length_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.part_length_var, width=28).grid(
            row=1, column=1, padx=(5, 0), pady=3
        )

        ttk.Label(add_frame, text="Количество:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.part_qty_var = tk.StringVar(value="1")
        ttk.Entry(add_frame, textvariable=self.part_qty_var, width=28).grid(
            row=2, column=1, padx=(5, 0), pady=3
        )

        btn_row = ttk.Frame(add_frame)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(10, 0))

        ttk.Button(btn_row, text="➕ Добавить", command=self._add_part).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_row, text="🗑 Удалить", command=self._delete_part).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_row, text="🧹 Очистить", command=self._clear_parts).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        ttk.Button(btn_row, text="📥 Импорт", command=self._import_parts).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Таблица с колонкой №
        table_frame = ttk.LabelFrame(left, text=" 📋 Список изделий (2×клик — редактировать) ", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 10))

        columns = ("id", "name", "length", "qty")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        self.tree.heading("id", text="№")
        self.tree.heading("name", text="Название")
        self.tree.heading("length", text="Длина (мм)")
        self.tree.heading("qty", text="Кол-во")
        self.tree.column("id", width=35, anchor=tk.CENTER)
        self.tree.column("name", width=140)
        self.tree.column("length", width=85, anchor=tk.CENTER)
        self.tree.column("qty", width=55, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_double_click)

        # Кнопка расчёта
        ttk.Button(
            left, text="🔧  РАССЧИТАТЬ РАСКРОЙ", command=self._calculate,
        ).pack(fill=tk.X, padx=5, pady=(0, 5), ipady=8)

        # Кнопка экспорта PDF
        ttk.Button(
            left, text="📄  ЭКСПОРТ В PDF", command=self._export_pdf,
        ).pack(fill=tk.X, padx=5, pady=(0, 5), ipady=4)

        # ──── Правая панель ────
        right = ttk.Frame(main)
        main.add(right, weight=1)

        self.chart = ScrollableChart(right)
        self.chart.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        report_frame = ttk.LabelFrame(right, text=" 📊 Отчёт ", padding=5)
        report_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.report_text = tk.Text(
            report_frame, height=8, font=("Consolas", 10),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#ffffff",
            relief=tk.FLAT, wrap=tk.WORD
        )
        self.report_text.pack(fill=tk.X)

        self.root.after(100, self.chart.show_placeholder)

    # ── Добавление ──

    def _add_part(self):
        name = self.part_name_var.get().strip()
        try:
            length = float(self.part_length_var.get().replace(",", "."))
            if length <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Введите корректную длину!")
            return
        try:
            qty = int(self.part_qty_var.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Введите корректное количество!")
            return

        part_id = self.next_id
        self.next_id += 1

        display_name = name if name else ""

        self.parts.append({"id": part_id, "name": display_name, "length": length, "qty": qty})
        self.tree.insert("", tk.END, values=(f"#{part_id}", display_name, length, qty))

        self.part_name_var.set("")
        self.part_length_var.set("")
        self.part_qty_var.set("1")

    def _import_parts(self):
        """Открыть окно импорта изделий."""
        dialog = ImportDialog(self.root)
        self.root.wait_window(dialog)

        if dialog.result is not None:
            count = 0
            for item in dialog.result:
                part_id = self.next_id
                self.next_id += 1
                self.parts.append({
                    "id": part_id,
                    "name": item["name"],
                    "length": item["length"],
                    "qty": item["qty"],
                })
                self.tree.insert("", tk.END, values=(
                    f"#{part_id}", item["name"], item["length"], item["qty"]
                ))
                count += 1
            messagebox.showinfo("Импорт", f"Добавлено изделий: {count}")

    # ── Редактирование ──

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return

        idx = self.tree.index(item)
        part = self.parts[idx]

        dialog = EditPartDialog(
            self.root,
            name=part["name"],
            length=part["length"],
            qty=part["qty"],
        )
        self.root.wait_window(dialog)

        if dialog.result is not None:
            new_name, new_length, new_qty = dialog.result
            self.parts[idx]["name"] = new_name
            self.parts[idx]["length"] = new_length
            self.parts[idx]["qty"] = new_qty
            self.tree.item(item, values=(f"#{part['id']}", new_name, new_length, new_qty))

    # ── Удаление ──

    def _delete_part(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Подсказка", "Выберите строку для удаления.")
            return
        indices = sorted([self.tree.index(item) for item in selected], reverse=True)
        for idx in indices:
            self.parts.pop(idx)
        for item in selected:
            self.tree.delete(item)

    # ── Очистка ──

    def _clear_parts(self):
        self.parts.clear()
        self.next_id = 1
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.chart.show_placeholder()
        self.report_text.delete("1.0", tk.END)

    # ── Расчёт ──

    def _calculate(self):
        try:
            stock_length = float(self.stock_length_var.get().replace(",", "."))
            if stock_length <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректную длину заготовки!")
            return

        try:
            margin_left = float(self.margin_left_var.get().replace(",", "."))
            if margin_left < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректный припуск слева!")
            return

        try:
            margin_right = float(self.margin_right_var.get().replace(",", "."))
            if margin_right < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректный припуск справа!")
            return

        try:
            kerf = float(self.kerf_var.get().replace(",", "."))
            if kerf < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректную ширину пропила!")
            return

        usable_length = stock_length - margin_left - margin_right
        if usable_length <= 0:
            messagebox.showerror("Ошибка", "Припуски больше длины заготовки!")
            return

        if not self.parts:
            messagebox.showwarning("Внимание", "Добавьте хотя бы одно изделие!")
            return

        material_name = self.material_name_var.get().strip() or "Материал"

        bins, oversized = ffd_cutting(usable_length, self.parts, kerf)

        if not bins and oversized:
            messagebox.showerror(
                "Ошибка",
                "Ни одно изделие не помещается в заготовку!"
            )
            return

        self.chart.draw(material_name, stock_length, bins, margin_left, margin_right, kerf)
        self._fill_report(material_name, stock_length, bins, oversized, margin_left, margin_right, kerf)

        if oversized:
            lines = []
            for name, length, pid in oversized:
                label = f"#{pid} {name}" if name else f"#{pid}"
                lines.append(f"  • {label} — {length:.0f} мм")
            messagebox.showwarning(
                "Внимание: не все изделия разложены",
                f"Следующие изделия длиннее рабочей зоны ({usable_length:.0f} мм) "
                f"и не были включены в раскрой:\n\n" + "\n".join(lines)
            )

    # ── Отчёт ──

    def _fill_report(self, material_name, stock_length, bins, oversized=None,
                     margin_left=0, margin_right=0, kerf=0):
        usable_length = stock_length - margin_left - margin_right
        total_pieces = sum(p["qty"] for p in self.parts)
        placed_count = sum(len(b["pieces"]) for b in bins)
        total_needed = sum(p["length"] * p["qty"] for p in self.parts)
        total_stock = len(bins) * stock_length
        total_waste = sum(b["remaining"] for b in bins)
        total_kerfs_count = sum(max(0, len(b["pieces"]) - 1) for b in bins)
        total_kerfs_mm = total_kerfs_count * kerf
        total_margins = len(bins) * (margin_left + margin_right)
        eff = (total_needed / total_stock) * 100 if total_stock else 0

        groups = group_bins(bins)

        lines = [
            f"  Материал:         {material_name}",
            f"  Дл��на заготовки:  {stock_length:.0f} мм",
            f"  Рабочая зона:     {usable_length:.0f} мм  (припуск Л={margin_left:.0f} П={margin_right:.0f})",
            f"  Ширина пропила:   {kerf:.1f} мм",
            f"  Всего изделий:    {total_pieces} шт.",
            f"  Разложено:        {placed_count} шт.",
            f"  Заготовок нужно:  {len(bins)} шт.  (уник. схем: {len(groups)})",
            f"  Общий расход:     {total_stock:.0f} мм",
            f"  Полезная длина:   {total_needed:.0f} мм",
            f"  Пропилов:         {total_kerfs_count} шт. ({total_kerfs_mm:.0f} мм)",
            f"  На припуски:      {total_margins:.0f} мм",
            f"  Общий отход:      {total_waste:.0f} мм",
            f"  Эффективность:    {eff:.1f}%",
        ]

        if oversized:
            lines.append("")
            lines.append(f"  ⚠ НЕ РАЗЛОЖЕНО ({len(oversized)} шт.):")
            for name, length, pid in oversized:
                label = f"#{pid} {name}" if name else f"#{pid}"
                lines.append(f"    • {label} — {length:.0f} мм (длиннее рабочей зоны)")

        lines.append("")
        for g in groups:
            b = g["bin"]
            count = g["count"]
            indices = g["indices"]

            # Группируем одинаковые изделия внутри заготовки
            piece_groups = []
            for name, length, pid in b["pieces"]:
                label = f"#{pid} {name}({length:.0f})" if name else f"#{pid}({length:.0f})"
                if piece_groups and piece_groups[-1]["label"] == label:
                    piece_groups[-1]["qty"] += 1
                else:
                    piece_groups.append({"label": label, "qty": 1})

            parts_parts = []
            for pg in piece_groups:
                if pg["qty"] > 1:
                    parts_parts.append(f"{pg['label']} ×{pg['qty']}шт")
                else:
                    parts_parts.append(pg["label"])
            parts_str = " + ".join(parts_parts)

            num_kerfs = max(0, len(b["pieces"]) - 1)

            if count > 1:
                if indices[-1] - indices[0] + 1 == count:
                    idx_str = f"#{indices[0]}-{indices[-1]}"
                else:
                    idx_str = ", ".join(f"#{x}" for x in indices)
                header = f"  Заготовка {idx_str} ({count} шт.):"
            else:
                header = f"  Заготовка #{indices[0]}:"

            detail = f"    {parts_str}"
            footer = f"    → остаток {b['remaining']:.0f} мм, пропилов: {num_kerfs}"

            lines.append(header)
            lines.append(detail)
            lines.append(footer)
            lines.append("")

        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", "\n".join(lines))

    def _export_pdf(self):
        """Экспорт отчёта и визуализации в PDF."""
        if not self.chart.fig or not self.chart.mpl_canvas:
            messagebox.showwarning("Внимание", "Сначала выполните расчёт раскроя!")
            return

        material_name = self.material_name_var.get().strip() or "Материал"

        filepath = filedialog.asksaveasfilename(
            title="Сохранить отчёт в PDF",
            defaultextension=".pdf",
            filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")],
            initialfile=f"{material_name}.pdf",
        )
        if not filepath:
            return

        try:
            stock_length = float(self.stock_length_var.get().replace(",", "."))
            margin_left = float(self.margin_left_var.get().replace(",", "."))
            margin_right = float(self.margin_right_var.get().replace(",", "."))
            kerf = float(self.kerf_var.get().replace(",", "."))
            report_text = self.report_text.get("1.0", tk.END).strip()

            with PdfPages(filepath) as pdf:
                # ── Страницы отчёта (может быть несколько) ──
                page_h = 11.69  # A4 высота в дюймах
                page_w = 8.27   # A4 ширина
                margin_top = 0.95
                margin_bottom = 0.05
                line_h = 0.015  # высота одной строки отчёта (в долях страницы)

                # === Страница 1: заголовок + параметры + таблица ===
                fig_p1 = Figure(figsize=(page_w, page_h), dpi=100)
                fig_p1.patch.set_facecolor("#ffffff")

                # Заголовок
                fig_p1.text(
                    0.5, margin_top, f"Отчёт линейного раскроя\n«{material_name}»",
                    ha="center", va="top",
                    fontsize=16, fontweight="bold",
                )

                # Параметры
                params_y = margin_top - 0.07
                params_lines = (
                    f"Длина заготовки: {stock_length:.0f} мм   |   "
                    f"Припуск Л: {margin_left:.0f} мм   П: {margin_right:.0f} мм   |   "
                    f"Пропил: {kerf:.1f} мм"
                )
                fig_p1.text(
                    0.5, params_y, params_lines,
                    ha="center", va="top",
                    fontsize=10, color="#555555",
                )

                # Таблица изделий
                table_data = []
                for p in self.parts:
                    pid = f"#{p['id']}"
                    pname = p["name"] if p["name"] else "—"
                    plength = f"{p['length']:.0f}"
                    pqty = f"{p['qty']}"
                    table_data.append([pid, pname, plength, pqty])

                col_labels = ["№", "Название", "Длина (мм)", "Кол-во (шт)"]
                num_rows = len(table_data)
                row_height_frac = 0.025  # высота строки таблицы в долях
                table_height = (num_rows + 1) * row_height_frac  # +1 для заголовка
                table_top = params_y - 0.04
                table_bottom = table_top - table_height

                # Проверяем, влезает ли таблица
                if table_bottom < margin_bottom:
                    table_bottom = margin_bottom
                    table_height = table_top - table_bottom

                table_ax = fig_p1.add_axes([0.06, table_bottom, 0.88, table_height])
                table_ax.axis("off")

                table_ax.text(
                    0.0, 1.05, "Список изделий:",
                    fontsize=12, fontweight="bold",
                    transform=table_ax.transAxes,
                )

                table = table_ax.table(
                    cellText=table_data,
                    colLabels=col_labels,
                    loc="upper center",
                    cellLoc="center",
                    colWidths=[0.08, 0.52, 0.20, 0.20],
                )
                table.auto_set_font_size(False)
                table.set_fontsize(9)
                table.scale(1, 1.4)

                for j in range(len(col_labels)):
                    cell = table[0, j]
                    cell.set_facecolor("#4e79a7")
                    cell.set_text_props(color="#ffffff", fontweight="bold")
                    cell.set_edgecolor("#333333")

                for i in range(1, len(table_data) + 1):
                    for j in range(len(col_labels)):
                        cell = table[i, j]
                        cell.set_edgecolor("#cccccc")
                        if i % 2 == 0:
                            cell.set_facecolor("#f2f2f2")
                        else:
                            cell.set_facecolor("#ffffff")
                    table[i, 1].set_text_props(ha="left")

                pdf.savefig(fig_p1)
                plt.close(fig_p1)

                # === Страницы текстового отчёта (с разбивкой) ===
                report_lines = report_text.split("\n")
                max_lines_per_page = 55
                line_idx = 0

                while line_idx < len(report_lines):
                    chunk = report_lines[line_idx:line_idx + max_lines_per_page]
                    line_idx += max_lines_per_page

                    fig_rpt = Figure(figsize=(page_w, page_h), dpi=100)
                    fig_rpt.patch.set_facecolor("#ffffff")

                    # Заголовок на каждой странице отчёта
                    if line_idx <= max_lines_per_page:
                        fig_rpt.text(
                            0.06, margin_top, "Результаты раскроя:",
                            ha="left", va="top",
                            fontsize=14, fontweight="bold",
                        )
                        text_start_y = margin_top - 0.04
                    else:
                        fig_rpt.text(
                            0.06, margin_top, "Результаты раскроя (продолжение):",
                            ha="left", va="top",
                            fontsize=14, fontweight="bold",
                        )
                        text_start_y = margin_top - 0.04

                    fig_rpt.text(
                        0.06, text_start_y,
                        "\n".join(chunk),
                        ha="left", va="top",
                        fontsize=8.5, fontfamily="monospace",
                        linespacing=1.4,
                    )

                    pdf.savefig(fig_rpt)
                    plt.close(fig_rpt)

                # ── Страницы визуализации ──
                bins, oversized = ffd_cutting(
                    stock_length - margin_left - margin_right,
                    self.parts, kerf
                )

                max_rows_per_page = 20
                total_bins = len(bins)
                page_num = 0

                while page_num * max_rows_per_page < total_bins:
                    start = page_num * max_rows_per_page
                    end = min(start + max_rows_per_page, total_bins)
                    page_bins = bins[start:end]
                    n = len(page_bins)

                    fig_vis = Figure(figsize=(11.69, 8.27), dpi=100)  # A4 landscape
                    fig_vis.patch.set_facecolor("#ffffff")
                    ax = fig_vis.add_subplot(111)

                    bar_height = 0.6
                    color_map = {}
                    label_map = {}
                    colors_list = [
                        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                        "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
                        "#9c755f", "#bab0ac", "#6baed6", "#fd8d3c",
                        "#74c476", "#9e9ac8", "#e377c2", "#17becf",
                        "#bcbd22", "#7f7f7f", "#d62728", "#1f77b4",
                    ]
                    c_idx = 0

                    ax.set_xlim(-stock_length * 0.07, stock_length * 1.05)
                    ax.set_ylim(-0.8, n - 0.2 + 0.8)
                    ax.set_xlabel("Длина (мм)", fontsize=10)
                    ax.set_yticks([])
                    ax.spines["top"].set_visible(False)
                    ax.spines["right"].set_visible(False)
                    ax.spines["left"].set_visible(False)

                    for i, b in enumerate(page_bins):
                        y = n - 1 - i
                        global_idx = start + i + 1

                        # Фон заготовки
                        ax.add_patch(patches.FancyBboxPatch(
                            (0, y - bar_height / 2), stock_length, bar_height,
                            boxstyle="round,pad=0",
                            linewidth=1.2, edgecolor="#555555", facecolor="#e8e8e8",
                        ))

                        # Припуски
                        if margin_left > 0:
                            ax.add_patch(patches.Rectangle(
                                (0, y - bar_height / 2), margin_left, bar_height,
                                linewidth=0.5, edgecolor="#999", facecolor="#cccccc",
                                hatch="///", alpha=0.7,
                            ))
                        if margin_right > 0:
                            ax.add_patch(patches.Rectangle(
                                (stock_length - margin_right, y - bar_height / 2),
                                margin_right, bar_height,
                                linewidth=0.5, edgecolor="#999", facecolor="#cccccc",
                                hatch="///", alpha=0.7,
                            ))

                        x_offset = margin_left
                        for j, (name, length, piece_id) in enumerate(b["pieces"]):
                            if j > 0 and kerf > 0:
                                ax.add_patch(patches.Rectangle(
                                    (x_offset, y - bar_height / 2), kerf, bar_height,
                                    linewidth=0, facecolor="#ff4444", alpha=0.6,
                                ))
                                x_offset += kerf

                            if piece_id not in color_map:
                                color_map[piece_id] = colors_list[c_idx % len(colors_list)]
                                c_idx += 1
                                lbl = f"#{piece_id} {name}" if name else f"#{piece_id}"
                                label_map[piece_id] = (lbl, color_map[piece_id])
                            color = color_map[piece_id]

                            ax.add_patch(patches.FancyBboxPatch(
                                (x_offset, y - bar_height / 2), length, bar_height,
                                boxstyle="round,pad=0",
                                linewidth=0.8, edgecolor="#333", facecolor=color, alpha=0.88,
                            ))

                            fontsize = max(5.5, min(8.5, length / stock_length * 70))
                            full_label = f"{name}\n{length:.0f}" if name else f"#{piece_id}\n{length:.0f}"
                            short_label = f"#{piece_id}\n{length:.0f}"

                            approx_char_w = stock_length / 120
                            text_len = len(full_label.split("\n")[0])
                            label = full_label if (text_len * approx_char_w) < length * 0.8 else short_label

                            ax.text(
                                x_offset + length / 2, y, label,
                                ha="center", va="center",
                                fontsize=fontsize, fontweight="bold", color="#ffffff",
                            )
                            x_offset += length

                        remaining = b["remaining"]
                        if remaining > stock_length * 0.03:
                            ax.text(
                                x_offset + remaining / 2, y,
                                f"Ост.\n{remaining:.0f}",
                                ha="center", va="center",
                                fontsize=6.5, fontstyle="italic", color="#999999",
                            )

                        ax.text(
                            -stock_length * 0.015, y,
                            f"#{global_idx}", ha="right", va="center",
                            fontsize=9, fontweight="bold", color="#444444",
                        )

                    # Заголовок страницы
                    page_label = f" (стр. {page_num + 1})" if total_bins > max_rows_per_page else ""
                    total_stock_all = len(bins) * stock_length
                    total_waste_all = sum(bb["remaining"] for bb in bins)
                    eff = ((total_stock_all - total_waste_all) / total_stock_all) * 100 if total_stock_all else 0

                    ax.set_title(
                        f"«{material_name}»  •  Заготовка: {stock_length:.0f} мм  •  "
                        f"Штук: {len(bins)}  •  Эффективность: {eff:.1f}%{page_label}",
                        fontsize=11, fontweight="bold", pad=12,
                    )

                    # Легенда
                    legend_handles = [
                        patches.Patch(facecolor=c, edgecolor="#333", label=lbl)
                        for lbl, c in label_map.values()
                    ]
                    if margin_left > 0 or margin_right > 0:
                        legend_handles.append(
                            patches.Patch(facecolor="#cccccc", edgecolor="#999",
                                          hatch="///", label="Припуск")
                        )
                    if kerf > 0:
                        legend_handles.append(
                            patches.Patch(facecolor="#ff4444", alpha=0.6,
                                          edgecolor="none", label=f"Пропил ({kerf})")
                        )
                    legend_handles.append(
                        patches.Patch(facecolor="#e8e8e8", edgecolor="#555", label="Остаток")
                    )
                    ax.legend(
                        handles=legend_handles, loc="upper right",
                        fontsize=7, framealpha=0.9, title="Изделия",
                    )

                    fig_vis.tight_layout()
                    pdf.savefig(fig_vis)
                    plt.close(fig_vis)
                    page_num += 1

            messagebox.showinfo("Готово", f"PDF сохранён:\n{filepath}")

        except Exception as e:
            messagebox.showerror("Ошибка экспорта", f"Не удалось сохранить PDF:\n{e}")


# ─────────────────────────── Запуск ───────────────────────────

def main():
    root = tk.Tk()
    app = CuttingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()