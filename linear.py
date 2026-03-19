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


# ─────────────────────────── Алгоритм ───────────────────────────

def ffd_cutting(stock_length, parts):
    """First Fit Decreasing для линейного раскроя."""
    pieces = []
    for p in parts:
        for _ in range(p["qty"]):
            pieces.append((p["name"], p["length"], p["id"]))

    oversized = [p for p in pieces if p[1] > stock_length]
    if oversized:
        names = set(f"«{n}» ({l} мм)" for n, l, _ in oversized)
        raise ValueError(
            f"Изделия длиннее заготовки ({stock_length} мм):\n"
            + "\n".join(f"  • {n}" for n in names)
        )

    pieces.sort(key=lambda x: x[1], reverse=True)
    bins = []

    for piece_name, piece_len, piece_id in pieces:
        placed = False
        for b in bins:
            if b["remaining"] >= piece_len:
                b["pieces"].append((piece_name, piece_len, piece_id))
                b["remaining"] -= piece_len
                placed = True
                break
        if not placed:
            bins.append({
                "remaining": stock_length - piece_len,
                "pieces": [(piece_name, piece_len, piece_id)],
            })
    return bins


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
        if not name:
            messagebox.showwarning("Внимание", "Введите название!", parent=self)
            return
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

    def draw(self, material_name, stock_length, bins):
        """Отрисовать карту раскроя с фиксированной высотой строк."""
        self.clear()

        n = len(bins)
        canvas_width = max(self.tk_canvas.winfo_width(), 600)
        fig_w = canvas_width / self.DPI
        fig_h_px = self.PADDING_TOP_PX + n * self.ROW_HEIGHT_PX + self.PADDING_BOTTOM_PX
        fig_h = fig_h_px / self.DPI

        self.fig = Figure(figsize=(fig_w, fig_h), dpi=self.DPI)
        self.fig.patch.set_facecolor("#fafafa")
        ax = self.fig.add_subplot(111)

        bar_height = 0.6

        color_map = {}
        colors = [
            "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
            "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
            "#9c755f", "#bab0ac", "#6baed6", "#fd8d3c",
            "#74c476", "#9e9ac8", "#e377c2", "#17becf",
            "#bcbd22", "#7f7f7f", "#d62728", "#1f77b4",
        ]
        color_idx = 0

        # Настраиваем оси ДО отрисовки текста (нужно для расчёта ширины)
        ax.set_xlim(-stock_length * 0.07, stock_length * 1.05)
        ax.set_ylim(-0.8, n - 0.2 + 0.8)
        ax.set_xlabel("Длина (мм)", fontsize=10)
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

        self.fig.tight_layout()

        # Нужен предварительный рендер, чтобы renderer существовал
        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=self.inner_frame)
        self.mpl_canvas.draw()

        # Собираем все тексты для отложенной отрисовки
        text_items = []

        for i, b in enumerate(bins):
            y = n - 1 - i

            ax.add_patch(patches.FancyBboxPatch(
                (0, y - bar_height / 2), stock_length, bar_height,
                boxstyle="round,pad=0",
                linewidth=1.2, edgecolor="#555555", facecolor="#e8e8e8",
            ))

            x_offset = 0.0
            for name, length, piece_id in b["pieces"]:
                if name not in color_map:
                    color_map[name] = colors[color_idx % len(colors)]
                    color_idx += 1
                color = color_map[name]

                ax.add_patch(patches.FancyBboxPatch(
                    (x_offset, y - bar_height / 2), length, bar_height,
                    boxstyle="round,pad=0",
                    linewidth=0.8, edgecolor="#333333", facecolor=color, alpha=0.88,
                ))

                fontsize = max(5.5, min(8.5, length / stock_length * 70))

                # Полная подпись и короткая (#id)
                full_label = f"{name}\n{length:.0f}"
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

            ax.text(
                -stock_length * 0.015, y,
                f"#{i + 1}", ha="right", va="center",
                fontsize=9, fontweight="bold", color="#444444",
            )

        # Умные подписи: проверяем помещается ли название
        PADDING_FACTOR = 1.3  # запас, чтобы текст не впритык к краям

        for item in text_items:
            full_w = self._get_text_width(ax, item["full"].split("\n")[0], item["fontsize"])
            full_w *= PADDING_FACTOR

            if full_w <= item["width"]:
                label = item["full"]
            else:
                label = item["short"]

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
            f"Штук: {len(bins)}  •  Эффективность: {eff:.1f}%",
            fontsize=11, fontweight="bold", pad=12,
        )

        # Легенда
        legend_handles = [
            patches.Patch(facecolor=c, edgecolor="#333", label=f"#{pid} {nm}")
            for nm, (c, pid) in {
                n: (color_map[n], next(
                    p["id"] for p in _parts_ref if p["name"] == n
                )) for n in color_map
            }.items()
        ] if False else [
            patches.Patch(facecolor=c, edgecolor="#333", label=nm)
            for nm, c in color_map.items()
        ]
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

        # Материал
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
        if not name:
            messagebox.showwarning("Внимание", "Введите название изделия!")
            return
        try:
            length = float(self.part_length_var.get())
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

        self.parts.append({"id": part_id, "name": name, "length": length, "qty": qty})
        self.tree.insert("", tk.END, values=(f"#{part_id}", name, length, qty))

        self.part_name_var.set("")
        self.part_length_var.set("")
        self.part_qty_var.set("1")

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
            stock_length = float(self.stock_length_var.get())
            if stock_length <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректную длину заготовки!")
            return

        if not self.parts:
            messagebox.showwarning("Внимание", "Добавьте хотя бы одно изделие!")
            return

        material_name = self.material_name_var.get().strip() or "Материал"

        try:
            bins = ffd_cutting(stock_length, self.parts)
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
            return

        self.chart.draw(material_name, stock_length, bins)
        self._fill_report(material_name, stock_length, bins)

    # ── Отчёт ──

    def _fill_report(self, material_name, stock_length, bins):
        total_pieces = sum(p["qty"] for p in self.parts)
        total_needed = sum(p["length"] * p["qty"] for p in self.parts)
        total_stock = len(bins) * stock_length
        total_waste = sum(b["remaining"] for b in bins)
        eff = (total_needed / total_stock) * 100 if total_stock else 0

        lines = [
            f"  Материал:         {material_name}",
            f"  Длина заготовки:  {stock_length:.0f} мм",
            f"  Всего изделий:    {total_pieces} шт.",
            f"  Заготовок нужно:  {len(bins)} шт.",
            f"  Общий расход:     {total_stock:.0f} мм",
            f"  Полезная длина:   {total_needed:.0f} мм",
            f"  Общий отход:      {total_waste:.0f} мм",
            f"  Эффективность:    {eff:.1f}%",
            "",
        ]
        for i, b in enumerate(bins, 1):
            parts_str = " + ".join(f"#{pid} {n}({l:.0f})" for n, l, pid in b["pieces"])
            lines.append(f"  Заготовка #{i}: {parts_str}  →  остаток {b['remaining']:.0f} мм")

        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", "\n".join(lines))


# ─────────────────────────── Запуск ───────────────────────────

def main():
    root = tk.Tk()
    app = CuttingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()