"""行情列表 v2：板块/行业列、右键菜单。"""
import tkinter as tk

from . import theme as T

ROW_H = 26
HEAD_H = 28
COLS = [
    ("name", "名称/代码", 148, "w"),
    ("price", "现价", 66, "e"),
    ("pct", "涨跌幅", 72, "e"),
    ("vr", "量比", 56, "e"),
    ("vol", "成交量", 66, "e"),
    ("spark", "缩略分时", 78, "e"),
    ("board", "板块", 76, "w"),
    ("industry", "细分行业", 84, "w"),
]
TOTAL_W = sum(c[2] for c in COLS)


class MarketTable(tk.Frame):
    def __init__(self, master, on_select=None, on_sort=None, on_menu=None):
        super().__init__(master, bg=T.PANEL, highlightthickness=0)
        self.on_select = on_select
        self.on_sort = on_sort
        self.on_menu = on_menu
        self.rows = []
        self.spark = {}
        self.selected = None
        self.sort_key = "pct"
        self.sort_desc = True
        self.hover = None

        self.canvas = tk.Canvas(self, bg=T.PANEL, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                width=10, troughcolor=T.PANEL_ALT, bg=T.LINE,
                                activebackground=T.HINT, relief="flat", bd=0)
        self.bar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Button-3>", self._on_right)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(None))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-3))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(3))

    def set_rows(self, rows):
        self.rows = rows
        total = HEAD_H + len(rows) * ROW_H
        self.canvas.configure(scrollregion=(0, 0, TOTAL_W, max(total, 10)))
        self.redraw()

    def set_spark(self, code, points):
        self.spark[code] = points

    def select(self, code):
        self.selected = code
        self.redraw()

    def jump_to(self, code):
        for i, r in enumerate(self.rows):
            if r["code"] == code:
                total = max(1, HEAD_H + len(self.rows) * ROW_H)
                h = max(1, self.canvas.winfo_height())
                self.canvas.yview_moveto(max(0.0, (HEAD_H + i * ROW_H - h * 0.4) / total))
                self.redraw()
                return

    def _on_scroll(self, first, last):
        self.bar.set(first, last)
        self.redraw()

    def _scroll(self, units):
        self.canvas.yview_scroll(units, "units")
        self.redraw()

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 * int(event.delta / 120) * 3, "units")
        self.redraw()

    def _on_motion(self, event):
        self._set_hover(self._row_at(event.y))

    def _set_hover(self, idx):
        if idx != self.hover:
            self.hover = idx
            self.canvas.configure(cursor="hand2" if idx is not None else "")
            self.redraw()

    def _row_at(self, y):
        cy = self.canvas.canvasy(y)
        if cy < HEAD_H:
            return None
        idx = int((cy - HEAD_H) // ROW_H)
        return idx if 0 <= idx < len(self.rows) else None

    def _on_click(self, event):
        cy = self.canvas.canvasy(event.y)
        if cy < HEAD_H:
            x = self.canvas.canvasx(event.x)
            acc = 0
            for key, _t, width, _a in COLS:
                if acc <= x < acc + width:
                    if key in ("name", "price", "pct", "vr", "vol") and self.on_sort:
                        self.on_sort(key)
                    break
                acc += width
            return
        idx = self._row_at(event.y)
        if idx is not None and self.on_select:
            self.on_select(self.rows[idx]["code"])

    def _on_right(self, event):
        idx = self._row_at(event.y)
        if idx is None:
            return
        row = self.rows[idx]
        self.selected = row["code"]
        self.redraw()
        if self.on_menu:
            self.on_menu(row, event.x_root, event.y_root)

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20:
            return
        c.create_rectangle(0, 0, w, HEAD_H, fill="#fafbfd", outline="")
        x = 0
        for key, title, width, align in COLS:
            label = title + (" ▾" if self.sort_desc else " ▴") if key == self.sort_key else title
            color = T.ACCENT if key == self.sort_key else T.SUB
            tx = x + (8 if align == "w" else width - 8)
            c.create_text(tx, HEAD_H / 2, text=label, anchor="w" if align == "w" else "e",
                          fill=color, font=T.F_UI_SM)
            x += width
        c.create_line(0, HEAD_H, w, HEAD_H, fill=T.LINE)

        first = max(0, int((c.canvasy(0) - HEAD_H) // ROW_H))
        visible = int(h // ROW_H) + 2
        for i in range(first, min(len(self.rows), first + visible)):
            self._draw_row(i, w)

    def _draw_row(self, idx, w):
        c = self.canvas
        row = self.rows[idx]
        y = HEAD_H + idx * ROW_H
        if row["code"] == self.selected:
            c.create_rectangle(0, y, w, y + ROW_H, fill=T.SEL, outline="")
        elif idx == self.hover:
            c.create_rectangle(0, y, w, y + ROW_H, fill=T.HOVER, outline="")
        c.create_line(0, y + ROW_H, w, y + ROW_H, fill=T.LINE_SOFT)

        cy = y + ROW_H / 2
        x = 0
        for key, _t, width, _a in COLS:
            if key == "name":
                c.create_text(x + 8, cy, text=row["name"], anchor="w", fill=T.TEXT, font=T.F_UI)
                c.create_text(x + width - 5, cy, text=row["code"], anchor="e", fill=T.HINT,
                              font=T.F_NUM_SM)
            elif key == "price":
                c.create_text(x + width - 8, cy,
                              text=("%.2f" % row["price"]) if row["price"] else "--",
                              anchor="e", fill=T.color_of(row["pct"]), font=T.F_NUM)
            elif key == "pct":
                c.create_text(x + width - 8, cy, text="%+.2f%%" % row["pct"], anchor="e",
                              fill=T.color_of(row["pct"]), font=T.F_NUM)
            elif key == "vr":
                vr = row.get("vr")
                c.create_text(x + width - 8, cy, text=("%.2f" % vr) if vr else "--",
                              anchor="e", fill=T.SUB if (vr or 0) < 1.5 else T.TEXT,
                              font=T.F_NUM)
            elif key == "vol":
                vol = row.get("vol") or 0
                c.create_text(x + width - 8, cy, text=("%.1f" % (vol / 1e4)) if vol else "--",
                              anchor="e", fill=T.SUB, font=T.F_NUM)
            elif key == "spark":
                self._draw_spark(x + 3, y + 4, width - 10, ROW_H - 8, row)
            elif key == "board":
                c.create_text(x + 6, cy, text=row.get("board", ""), anchor="w", fill="#5b6779",
                              font=T.F_UI_SM)
            elif key == "industry":
                c.create_text(x + 6, cy, text=row.get("industry") or "—", anchor="w",
                              fill=T.SUB, font=T.F_UI_SM)
            x += width

    def _draw_spark(self, x, y, w, h, row):
        pts = self.spark.get(row["code"])
        c = self.canvas
        if not pts or len(pts) < 2:
            c.create_line(x + w * 0.2, y + h / 2, x + w * 0.8, y + h / 2, fill=T.LINE,
                          dash=(2, 3))
            return
        step = max(1, len(pts) // 48)
        prices = [p for p, _v, _a in pts[::step]]
        if len(prices) < 2:
            return
        hi, lo = max(prices), min(prices)
        span = (hi - lo) or (hi * 0.001 or 1)
        pre = row.get("pre_close") or prices[0]
        color = T.UP if prices[-1] >= pre else T.DOWN
        n = len(prices)
        line = []
        for i, p in enumerate(prices):
            line += [x + w * i / (n - 1), y + h - (p - lo) / span * h]
        c.create_line(*line, fill=color, width=1)
        c.create_line(x, y + h - (pre - lo) / span * h, x + w, y + h - (pre - lo) / span * h,
                      fill=T.LINE, dash=(1, 3))
