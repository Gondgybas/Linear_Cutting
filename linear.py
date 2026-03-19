"""
Программа линейного раскроя материала с GUI интерфейсом.
Алгоритм: First Fit Decreasing (FFD).
Интерфейс: tkinter + matplotlib.
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
            pieces.append((p["name"], p["length"]))

    oversized = [p for p in pieces if p[1] > stock_length]
    if oversized:
        names = set(f"«{n}» ({l} мм)" for n, l in oversized)
        raise ValueError(
            f"Изделия длиннее заготовки ({stock_length} мм):\n"
            + "\n".join(f"  • {n}" for n in names)
        )

    pieces.sort(key=lambda x: x[1], reverse=True)
    bins = []

    for piece_name, piece_len in pieces:
        placed = False
        for b in bins:
            if b["remaining"] >= piece_len:
                b["pieces"].append((piece_name, piece_len))
                b["remaining"] -= piece_len
                placed = True
                break
        if not placed:
            bins.append({
                "remaining": stock_length - piece_len,
                "pieces": [(piece_name, piece_len)],
            })
    return bins


# ─────────────────────────── GUI ───────────────────────────

class CuttingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Линейный раскрой материала")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg="#f0f0f0")

        self.parts = []

        self._build_ui()

    # ── Построение интерфейса ──

    def _build_ui(self):
        # Главный контейнер
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ──── Левая панель (ввод данных) ────
        left = ttk.Frame(main, width=380)
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

        # --- Добавление изделия ---
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
        ttk.Button(btn_row, text="🗑 Удалить выбранное", command=self._delete_part).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_row, text="🧹 Очистить всё", command=self._clear_parts).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # --- Таблица изделий ---
        table_frame = ttk.LabelFrame(left, text=" 📋 Список изделий ", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 10))

        columns = ("name", "length", "qty")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        self.tree.heading("name", text="Название")
        self.tree.heading("length", text="Длина (мм)")
        self.tree.heading("qty", text="Кол-во")
        self.tree.column("name", width=140)
        self.tree.column("length", width=90, anchor=tk.CENTER)
        self.tree.column("qty", width=60, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Кнопка расчёта ---
        ttk.Button(
            left, text="🔧  РАССЧИТАТЬ РАСКРОЙ", command=self._calculate,
            style="Accent.TButton"
        ).pack(fill=tk.X, padx=5, pady=(0, 5), ipady=8)

        # ──── Правая панель (визуализация + отчёт) ────
        right = ttk.Frame(main)
        main.add(right, weight=1)

        # Визуализация (matplotlib)
        self.fig = Figure(figsize=(7, 4), dpi=100)
        self.fig.patch.set_facecolor("#fafafa")
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Текстовый отчёт
        report_frame = ttk.LabelFrame(right, text=" 📊 Отчёт ", padding=5)
        report_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.report_text = tk.Text(
            report_frame, height=8, font=("Consolas", 10),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="#ffffff",
            relief=tk.FLAT, wrap=tk.WORD
        )
        self.report_text.pack(fill=tk.X)

        self._show_placeholder()

    # ── Заглушка на графике ──

    def _show_placeholder(self):
        self.fig.clear()
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
        self.canvas.draw()

    # ── Добавление изделия ──

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
            messagebox.showwarning("Внимание", "Введите корректную длину (положительное число)!")
            return
        try:
            qty = int(self.part_qty_var.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Внимание", "Введите корректное количество (целое положительное)!")
            return

        self.parts.append({"name": name, "length": length, "qty": qty})
        self.tree.insert("", tk.END, values=(name, length, qty))

        # Сбросить поля ввода
        self.part_name_var.set("")
        self.part_length_var.set("")
        self.part_qty_var.set("1")

    # ── Удаление выбранного ──

    def _delete_part(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Подсказка", "Выберите строку в таблице для удаления.")
            return
        for item in selected:
            idx = self.tree.index(item)
            self.tree.delete(item)
            if idx < len(self.parts):
                self.parts.pop(idx)

    # ── Очистка всего ──

    def _clear_parts(self):
        self.parts.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._show_placeholder()
        self.report_text.delete("1.0", tk.END)

    # ── Расчёт ──

    def _calculate(self):
        # Валидация
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
            messagebox.showerror("��шибка", str(e))
            return

        self._draw_chart(material_name, stock_length, bins)
        self._fill_report(material_name, stock_length, bins)

    # ── Визуализация ──

    def _draw_chart(self, material_name, stock_length, bins):
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        n = len(bins)
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

        for i, b in enumerate(bins):
            y = n - 1 - i

            # Фон заготовки
            ax.add_patch(patches.FancyBboxPatch(
                (0, y - bar_height / 2), stock_length, bar_height,
                boxstyle="round,pad=0",
                linewidth=1.2, edgecolor="#555555", facecolor="#e8e8e8",
            ))

            x_offset = 0.0
            for name, length in b["pieces"]:
                if name not in color_map:
                    color_map[name] = colors[color_idx % len(colors)]
                    color_idx += 1
                color = color_map[name]

                ax.add_patch(patches.FancyBboxPatch(
                    (x_offset, y - bar_height / 2), length, bar_height,
                    boxstyle="round,pad=0",
                    linewidth=0.8, edgecolor="#333333", facecolor=color, alpha=0.88,
                ))

                label = f"{name}\n{length:.0f}"
                fontsize = max(5.5, min(8.5, length / stock_length * 70))
                ax.text(
                    x_offset + length / 2, y, label,
                    ha="center", va="center",
                    fontsize=fontsize, fontweight="bold", color="#ffffff",
                )
                x_offset += length

            # Остаток
            remaining = b["remaining"]
            if remaining > stock_length * 0.03:
                ax.text(
                    x_offset + remaining / 2, y,
                    f"Ост.\n{remaining:.0f}",
                    ha="center", va="center",
                    fontsize=6.5, fontstyle="italic", color="#999999",
                )

            # Номер
            ax.text(
                -stock_length * 0.015, y,
                f"#{i + 1}", ha="right", va="center",
                fontsize=9, fontweight="bold", color="#444444",
            )

        ax.set_xlim(-stock_length * 0.07, stock_length * 1.05)
        ax.set_ylim(-0.8, n - 0.2 + 0.8)
        ax.set_xlabel("Длина (мм)", fontsize=10)
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

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
        self.canvas.draw()

    # ── Текстовый отчёт ──

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
            parts_str = " + ".join(f"{n}({l:.0f})" for n, l in b["pieces"])
            lines.append(f"  #{i}: {parts_str}  →  остаток {b['remaining']:.0f} мм")

        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", "\n".join(lines))


# ─────────────────────────── Запуск ───────────────────────────

def main():
    root = tk.Tk()
    app = CuttingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()