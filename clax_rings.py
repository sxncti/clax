"""Widget flutuante de rings para a area de trabalho (Windows ou Linux sem GNOME)."""

from __future__ import annotations

import math
import threading
import tkinter as tk
from tkinter import font as tkfont

from clax import collect_profiles, find_claude, reset_time


BACKGROUND = "#20252c"
TEXT = "#f5f6f7"
GREEN = "#2ecc71"
YELLOW = "#f2ab22"
RED = "#e84a42"
MUTED = "#a4aab0"
RAY_IDLE = "#865344"
RAY_MUTED = "#505152"
RAY_MUTED_LIT = "#c7c7c7"
RAYS = 12
REFRESH_MS = 300_000


def enable_dpi_awareness() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError, ValueError):
        pass


class RingsWidget:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("CLAX 5h Rings")
        self.root.configure(bg=BACKGROUND)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.geometry("260x112+80+80")
        self.root.bind("<Button-3>", self.show_menu)
        self.root.bind("<ButtonPress-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Double-Button-1>", lambda _event: self.refresh())
        self.drag_origin = (0, 0)
        self.refreshing = False
        self.tooltip: tk.Toplevel | None = None
        self.hovered = -1
        self.title_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.number_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.percent_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.info_font = tkfont.Font(family="Segoe UI", size=8)
        self.menu = tk.Menu(self.root, tearoff=False, bg=BACKGROUND, fg=TEXT,
                            activebackground="#39434d", activeforeground=TEXT)
        self.menu.add_command(label="Atualizar agora", command=self.refresh)
        self.menu.add_command(label="Manter acima das janelas", command=self.toggle_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="Fechar", command=self.root.destroy)
        self.canvas = tk.Canvas(self.root, width=260, height=112, bg=BACKGROUND,
                                highlightthickness=1, highlightbackground="#46505b")
        self.canvas.pack()
        self.canvas.bind("<Button-3>", self.show_menu)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<Double-Button-1>", lambda _event: self.refresh())
        self.canvas.bind("<Motion>", self.show_account_detail)
        self.canvas.bind("<Leave>", lambda _event: self.hide_detail())
        self.rows: list[tuple[int, str, int, str, int | None]] = []
        self.draw_message("Consultando contas...")
        self.refresh()
        self.root.after(REFRESH_MS, self.periodic_refresh)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def start_drag(self, event: tk.Event) -> None:
        self.drag_origin = (event.x_root - self.root.winfo_x(),
                            event.y_root - self.root.winfo_y())

    def drag(self, event: tk.Event) -> None:
        x = event.x_root - self.drag_origin[0]
        y = event.y_root - self.drag_origin[1]
        self.root.geometry(f"+{x}+{y}")

    def show_menu(self, event: tk.Event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)
        self.menu.grab_release()

    def toggle_topmost(self) -> None:
        self.root.attributes("-topmost", not bool(self.root.attributes("-topmost")))

    def draw_message(self, message: str) -> None:
        self.hide_detail()
        self.canvas.delete("all")
        self.canvas.create_text(12, 16, text="CLAX 5h Rings", fill=TEXT,
                                font=self.title_font, anchor="w")
        self.canvas.create_text(12, 60, text=message, fill=MUTED,
                                font=self.info_font, anchor="w")

    def draw_spark(self, cx: int, cy: int, percent: int, blocked: bool, color: str) -> None:
        # Raios no estilo da "faisca" do Claude em vez de um anel continuo.
        outer = 19
        lit = round(RAYS * percent / 100)
        for index in range(RAYS):
            angle = -math.pi / 2 + 2 * math.pi * index / RAYS
            inner = outer - (7 if index % 2 == 0 else 4.5)
            if index < lit:
                fill = RAY_MUTED_LIT if blocked else color
            else:
                fill = RAY_MUTED if blocked else RAY_IDLE
            self.canvas.create_line(cx + inner * math.cos(angle), cy + inner * math.sin(angle),
                                    cx + outer * math.cos(angle), cy + outer * math.sin(angle),
                                    fill=fill, width=3, capstyle="round")

    def draw(self, rows: list[tuple[int, str, int, str, int | None]]) -> None:
        self.hide_detail()
        if not rows:
            self.rows = []
            self.root.geometry(f"260x112+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self.canvas.configure(width=260, height=112)
            self.draw_message("Nenhuma conta com limite disponivel")
            return
        width = max(260, 16 + len(rows) * 58)
        self.rows = rows
        self.root.geometry(f"{width}x112+{self.root.winfo_x()}+{self.root.winfo_y()}")
        self.canvas.configure(width=width, height=112)
        self.canvas.delete("all")
        self.canvas.create_text(12, 13, text="CLAX 5h Rings", fill=TEXT,
                                font=self.title_font, anchor="w")
        for index, (number, _email, percent, _reset, weekly) in enumerate(rows):
            cx = 42 + index * 58
            cy = 54
            blocked = percent > 0 and weekly == 0
            color = MUTED if blocked else GREEN if percent >= 50 else YELLOW if percent >= 20 else RED
            self.draw_spark(cx, cy, percent, blocked, color)
            self.canvas.create_text(cx, cy, text=str(percent), fill=TEXT if blocked else color,
                                    font=self.percent_font)
            self.canvas.create_text(cx, 82, text=str(number), fill=TEXT,
                                    font=self.number_font)

    def show_account_detail(self, event: tk.Event) -> None:
        index = round((event.x - 42) / 58)
        if not (0 <= index < len(self.rows)) or abs(event.x - (42 + index * 58)) > 23:
            self.hide_detail()
            return
        if index == self.hovered:
            return
        self.hide_detail()
        self.hovered = index
        number, email, percent, reset, weekly = self.rows[index]
        status = "bloqueada" if percent > 0 and weekly == 0 else f"semana {weekly}%" if weekly is not None and weekly >= 0 else "semana indisp."
        detail = f"{number} · {email} · 5h {percent}% · {status} · reset {reset}"
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes("-topmost", True)
        tk.Label(self.tooltip, text=detail, bg="#303943", fg=TEXT,
                 font=self.info_font, padx=8, pady=5).pack()
        self.tooltip.update_idletasks()
        x = min(event.x_root + 12, self.root.winfo_screenwidth() - self.tooltip.winfo_reqwidth() - 8)
        y = min(event.y_root + 16, self.root.winfo_screenheight() - self.tooltip.winfo_reqheight() - 8)
        self.tooltip.geometry(f"+{max(0, x)}+{max(0, y)}")

    def hide_detail(self) -> None:
        self.hovered = -1
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True

        def work() -> None:
            try:
                rows = [(number, usage.email, usage.five, reset_time(usage.five_reset), usage.week)
                        for number, connected, usage in collect_profiles(find_claude())
                        if connected and usage and usage.five is not None]
                self.root.after(0, lambda: self.finish_refresh(rows, None))
            except (Exception, SystemExit) as exc:
                self.root.after(0, lambda: self.finish_refresh([], str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def finish_refresh(self, rows: list[tuple[int, str, int, str, int | None]],
                       error: str | None) -> None:
        self.refreshing = False
        if error:
            self.draw_message("Limites indisponiveis")
        else:
            self.draw(rows)

    def periodic_refresh(self) -> None:
        self.refresh()
        self.root.after(REFRESH_MS, self.periodic_refresh)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    enable_dpi_awareness()
    return RingsWidget().run()


if __name__ == "__main__":
    raise SystemExit(main())
