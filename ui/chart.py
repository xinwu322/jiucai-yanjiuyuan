"""行情图表 v2：多副图、缩放平移、复权、指标读数。"""
import tkinter as tk

from . import theme as T

PAD_L, PAD_R, PAD_T, PAD_B = 8, 66, 26, 20
TIMES = ["09:30", "10:30", "11:30", "13:00", "14:00", "15:00"]


def _ma(values, n):
    out, s = [], 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


class ChartPanel(tk.Canvas):
    def __init__(self, master, **kw):
        kw.setdefault("bg", T.PANEL)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.mode = "kline"
        self.bars = []
        self.title = ""
        self.subtitle = ""
        self.overlay = None
        self.subs = []
        self.days, self.day_labels, self.day_pres = [], [], []
        self.multi = False
        self.hover = None
        self.view_count = 240
        self.view_end = 0
        self._drag = None
        self._geom = {}
        self._after = None

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Control-MouseWheel>", self._on_zoom)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self.pan(-3))
        self.bind("<Button-5>", lambda e: self.pan(3))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag_move)
        self.bind("<Double-Button-1>", lambda e: self.reset_view())

    # ------------------------------------------------ 数据
    def set_kline(self, bars, title="", subtitle=""):
        keep = self.mode == "kline" and self.bars and len(self.bars) == len(bars or [])
        self.mode = "kline"
        self.bars = bars or []
        if not keep or self.view_end > len(self.bars):
            self.reset_view()
        self.title, self.subtitle = title, subtitle
        self.hover = None
        self.redraw()

    def set_minute(self, days, labels, pres, title="", subtitle="", multi=False):
        self.mode = "minute"
        self.days, self.day_labels, self.day_pres = days or [], labels or [], pres or []
        self.multi = multi
        self.title, self.subtitle = title, subtitle
        self.hover = None
        self.redraw()
        self.after(60, self.redraw)
        self.after(260, self.redraw)

    def set_indicators(self, overlay=None, subs=None):
        self.overlay = overlay
        self.subs = [s for s in (subs or []) if s]
        self.redraw()

    def reset_view(self):
        self.view_count = min(240, len(self.bars) or 240)
        self.view_end = len(self.bars)
        self.redraw()

    def zoom(self, factor):
        if self.mode != "kline" or not self.bars:
            return
        n = int(self.view_count * factor)
        n = max(30, min(len(self.bars), n))
        self.view_count = n
        self.view_end = min(len(self.bars), max(n, self.view_end))
        self.redraw()

    def pan(self, delta):
        if self.mode != "kline" or not self.bars:
            return
        end = self.view_end + delta
        end = max(self.view_count, min(len(self.bars), end))
        self.view_end = end
        self.redraw()

    # ------------------------------------------------ 事件
    def _on_zoom(self, event):
        self.zoom(0.8 if event.delta > 0 else 1.25)
        return "break"

    def _on_wheel(self, event):
        self.pan(-3 if event.delta > 0 else 3)
        return "break"

    def _press(self, event):
        self._drag = (event.x, self.view_end)

    def _drag_move(self, event):
        if not self._drag or self.mode != "kline":
            return
        x0, end0 = self._drag
        dx = event.x - x0
        step = int(abs(dx) / max(1.0, self._geom.get("bw", 6)))
        self.view_end = (min(len(self.bars), end0 - step) if dx > 0
                         else max(self.view_count, end0 + step))
        self.redraw()

    def _on_motion(self, event):
        self.hover = (event.x, event.y)
        if self._after is None:
            self._after = self.after(24, self._flush)

    def _flush(self):
        self._after = None
        self.redraw()

    def _on_leave(self, _e):
        self.hover = None
        self.redraw()

    # ------------------------------------------------ 绘制
    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 100:
            return
        if self.mode == "minute":
            if self.multi and len(self.days) > 1:
                self._draw_multi(w, h)
            else:
                self._draw_minute(w, h)
        else:
            self._draw_kline(w, h)

    def _draw_kline(self, w, h):
        bars = self.bars
        if not bars:
            self._empty(w, h, "暂无 K 线数据")
            return
        if self.view_end <= 0 or self.view_end > len(bars):
            self.view_end = len(bars)
        n = max(20, min(self.view_count, len(bars)))
        idx0 = max(0, self.view_end - n)
        view = bars[idx0:idx0 + n]

        sub_n = len(self.subs)
        total = h - PAD_T - PAD_B
        vol_h = int(total * 0.15)
        subs_h = int(total * 0.26) if sub_n else 0
        gap = 6 if sub_n else 4
        main_h = total - vol_h - subs_h - gap * (2 if sub_n else 1)
        plot_w = w - PAD_L - PAD_R
        x0 = PAD_L
        bw = plot_w / max(1, n)

        hi = max(b["h"] for b in view)
        lo = min(b["l"] for b in view)
        mas = {}
        for period, color in ((5, "#e8a33d"), (10, "#2f6fd0"), (20, "#c04fd6"), (60, "#12a3b8")):
            series = _ma([b["c"] for b in bars], period)[idx0:idx0 + n]
            mas[period] = (series, color)
            vals = [v for v in series if v]
            if vals:
                hi, lo = max(hi, max(vals)), min(lo, min(vals))
        if self.overlay:
            for out in self.overlay["outputs"][:4]:
                vals = [v for v in out["values"][idx0:idx0 + n] if v is not None]
                if vals:
                    hi, lo = max(hi, max(vals)), min(lo, min(vals))
        pad = (hi - lo) * 0.06 or 0.01
        hi, lo = hi + pad, lo - pad

        def Y(p):
            return PAD_T + (hi - p) / (hi - lo) * main_h

        vol_top = PAD_T + main_h + gap
        self._geom = {"mode": "kline", "x0": x0, "bw": bw, "n": n, "idx0": idx0,
                      "Y": Y, "hi": hi, "lo": lo, "main_h": main_h, "plot_w": plot_w,
                      "vol_top": vol_top, "vol_h": vol_h}

        for i in range(5):
            p = lo + (hi - lo) * i / 4
            y = Y(p)
            self.create_line(x0, y, x0 + plot_w, y, fill=T.GRID)
            self.create_text(w - 6, y, text=self._fmt(p), anchor="e", fill=T.SUB,
                             font=T.F_NUM_SM)

        vmax = max(1, max(b["v"] for b in view))
        body_w = max(1.0, bw * 0.62)
        for i, b in enumerate(view):
            cx = x0 + bw * (i + 0.5)
            up = b["c"] >= b["o"]
            color = T.UP if up else T.DOWN
            self.create_line(cx, Y(b["h"]), cx, Y(b["l"]), fill=color)
            yo, yc = Y(b["o"]), Y(b["c"])
            top, bot = min(yo, yc), max(yo, yc)
            if bot - top < 1:
                bot = top + 1
            if up:
                self.create_rectangle(cx - body_w / 2, top, cx + body_w / 2, bot,
                                      outline=color, fill=T.PANEL)
            else:
                self.create_rectangle(cx - body_w / 2, top, cx + body_w / 2, bot,
                                      outline=color, fill=color)
            vh = b["v"] / vmax * (vol_h - 3)
            self.create_rectangle(cx - body_w / 2, vol_top + vol_h - vh,
                                  cx + body_w / 2, vol_top + vol_h,
                                  outline="", fill=color if up else T.DOWN)

        for period, (series, color) in mas.items():
            pts = []
            for i, v in enumerate(series):
                if v is None:
                    continue
                pts += [x0 + bw * (i + 0.5), Y(v)]
            if len(pts) >= 4:
                self.create_line(*pts, fill=color, width=1.1)

        if self.overlay:
            for out in self.overlay["outputs"][:4]:
                seg = []
                for i, v in enumerate(out["values"][idx0:idx0 + n]):
                    if v is None:
                        if len(seg) >= 4:
                            self.create_line(*seg, fill=out["color"], width=1.0)
                        seg = []
                    else:
                        seg += [x0 + bw * (i + 0.5), Y(v)]
                if len(seg) >= 4:
                    self.create_line(*seg, fill=out["color"], width=1.0)

        top = vol_top + vol_h + gap
        if sub_n:
            each = int(subs_h / sub_n)
            for k, ind in enumerate(self.subs):
                self._draw_sub(ind, x0, plot_w, top + k * each, each - 4, idx0, n, bw)

        step = max(1, n // 7)
        for i in range(0, n, step):
            self.create_text(x0 + bw * (i + 0.5), h - 8, text=view[i]["dt"][2:10],
                             fill=T.HINT, font=T.F_NUM_SM, anchor="n")

        self._legend(w, self.title, self.subtitle)
        self._ma_legend(x0, mas, idx0, n)
        if self.hover:
            self._cross_kline(view, bw, x0, plot_w, vol_top, vol_h, h)

    def _draw_sub(self, ind, x0, plot_w, top, height, idx0, n, bw):
        outs = ind.get("outputs") or []
        if not outs or height < 26:
            return
        vals = []
        for out in outs:
            vals += [v for v in out["values"][idx0:idx0 + n] if v is not None]
        if not vals:
            return
        hi, lo = max(vals), min(vals)
        if hi == lo:
            hi, lo = hi + .01, lo - .01
        pad = (hi - lo) * 0.12
        hi, lo = hi + pad, lo - pad

        def Y(v):
            return top + (hi - v) / (hi - lo) * height

        self.create_text(x0 + plot_w + 6, Y(hi), text=self._fmt(hi, 2), anchor="w",
                         fill=T.HINT, font=T.F_NUM_SM)
        self.create_text(x0 + plot_w + 6, Y(lo), text=self._fmt(lo, 2), anchor="w",
                         fill=T.HINT, font=T.F_NUM_SM)
        if lo < 0 < hi:
            self.create_line(x0, Y(0), x0 + plot_w, Y(0), fill=T.LINE)
        self.create_line(x0, top, x0 + plot_w, top, fill=T.LINE_SOFT)

        for out in outs:
            if out.get("style") == "bar":
                base = Y(0) if lo < 0 < hi else top + height
                for i, v in enumerate(out["values"][idx0:idx0 + n]):
                    if v is None:
                        continue
                    self.create_line(x0 + bw * (i + .5), base, x0 + bw * (i + .5), Y(v),
                                     fill=T.UP if v >= 0 else T.DOWN, width=max(1, bw * .5))
                continue
            seg = []
            for i, v in enumerate(out["values"][idx0:idx0 + n]):
                if v is None:
                    if len(seg) >= 4:
                        self.create_line(*seg, fill=out["color"], width=1.0)
                    seg = []
                else:
                    seg += [x0 + bw * (i + .5), Y(v)]
            if len(seg) >= 4:
                self.create_line(*seg, fill=out["color"], width=1.0)

        hx = self._hover_index(n, bw)
        px = x0 + 2
        for out in outs[:4]:
            v = None
            if hx is not None:
                v = out["values"][idx0 + hx]
            if v is None:
                for vv in reversed(out["values"][idx0:idx0 + n]):
                    if vv is not None:
                        v = vv
                        break
            label = "%s:%s" % (out["name"], self._fmt(v, 2) if v is not None else "--")
            self.create_text(px, top + 8, text=label, anchor="w", fill=out["color"],
                             font=T.F_NUM_SM)
            px += 10 + len(label) * 6.0
        self.create_text(x0 + plot_w + 6, top + 8, text=ind.get("name", ""), anchor="w",
                         fill=T.HINT, font=T.F_UI_SM)

    def _draw_minute(self, w, h):
        if not self.days or not self.days[-1]:
            self._empty(w, h, "暂无分时数据")
            return
        pts = self.days[-1]
        pre = (self.day_pres[-1] if self.day_pres else 0) or pts[0][0]
        prices = [p for p, _v, _a in pts]
        hi, lo = max(max(prices), pre), min(min(prices), pre)
        pad = max((hi - lo) * 0.07, pre * 0.002)
        hi, lo = hi + pad, lo - pad

        total = h - PAD_T - PAD_B
        vol_h = int(total * 0.18)
        plot_h = total - vol_h - 6
        plot_w = w - PAD_L - PAD_R
        x0 = PAD_L
        bw = plot_w / 240.0

        def Y(p):
            return PAD_T + (hi - p) / (hi - lo) * plot_h

        vtop = PAD_T + plot_h + 6
        self._geom = {"mode": "minute", "x0": x0, "bw": bw, "pre": pre, "Y": Y,
                      "vol_top": vtop, "vol_h": vol_h, "plot_w": plot_w}

        for i in range(5):
            p = lo + (hi - lo) * i / 4
            self.create_line(x0, Y(p), x0 + plot_w, Y(p), fill=T.GRID)
            self.create_text(w - 6, Y(p), text=self._fmt(p), anchor="e", fill=T.SUB,
                             font=T.F_NUM_SM)
        self.create_line(x0, Y(pre), x0 + plot_w, Y(pre), fill=T.CROSS, dash=(3, 3))
        self.create_text(x0 + 3, Y(pre) - 7, text=self._fmt(pre), anchor="w", fill=T.SUB,
                         font=T.F_NUM_SM)

        poly = [x0, PAD_T + plot_h]
        line, avg = [], []
        for i, (p, _v, a) in enumerate(pts):
            x = x0 + bw * (i + 0.5)
            poly += [x, Y(p)]
            line += [x, Y(p)]
            avg += [x, Y(a)]
        poly += [x0 + bw * (len(pts) - 0.5), PAD_T + plot_h]
        self.create_polygon(poly, fill="#eef4ff", outline="")
        self.create_line(*line, fill="#2f6fd0", width=1.3)
        self.create_line(*avg, fill="#e8a33d", width=1.0)

        vmax = max(1, max(v for _p, v, _a in pts))
        last = pre
        for i, (p, v, _a) in enumerate(pts):
            color = T.UP if p >= last else T.DOWN
            last = p
            vh = v / vmax * (vol_h - 2)
            if vh > 0.4:
                self.create_line(x0 + bw * (i + .5), vtop + vol_h - vh,
                                 x0 + bw * (i + .5), vtop + vol_h, fill=color)

        for i, label in enumerate(TIMES):
            self.create_text(x0 + plot_w * i / (len(TIMES) - 1), h - 8, text=label,
                             fill=T.HINT, font=T.F_NUM_SM, anchor="n")

        self._legend(w, self.title, self.subtitle)
        self.create_text(x0 + 4, PAD_T + 10,
                         text="昨收 %s  最高 %s  最低 %s" % (
                             self._fmt(pre), self._fmt(max(prices)), self._fmt(min(prices))),
                         anchor="w", fill=T.HINT, font=T.F_NUM_SM)
        if self.hover:
            self._cross_minute(pts, pre, bw, x0, plot_w, vtop, vol_h, h)

    def _draw_multi(self, w, h):
        days = self.days[-10:]
        pres = self.day_pres[-len(days):] if self.day_pres else [0] * len(days)
        labels = self.day_labels[-len(days):]
        total = h - PAD_T - PAD_B
        vol_h = int(total * 0.16)
        plot_h = total - vol_h - 10
        plot_w = w - PAD_L - PAD_R
        cell = plot_w / max(1, len(days))
        pcts = []
        for pts, pre in zip(days, pres):
            if not pre:
                continue
            pcts += [(p / pre - 1) * 100 for p, _v, _a in pts]
        if not pcts:
            self._empty(w, h, "暂无分时数据")
            return
        lim = max(1.0, max(abs(min(pcts)), abs(max(pcts))) * 1.12)
        mid = PAD_T + plot_h / 2

        for i in range(5):
            v = lim - 2 * lim * i / 4
            y = PAD_T + plot_h * i / 4
            self.create_line(PAD_L, y, PAD_L + plot_w, y, fill=T.GRID)
            self.create_text(w - 6, y, text="%+.2f%%" % v, anchor="e", fill=T.SUB,
                             font=T.F_NUM_SM)
        self.create_line(PAD_L, mid, PAD_L + plot_w, mid, fill=T.CROSS, dash=(3, 3))

        vtop = PAD_T + plot_h + 10
        for k, (pts, pre, label) in enumerate(zip(days, pres, labels)):
            if not pts or not pre:
                continue
            cx = PAD_L + cell * k
            if k:
                self.create_line(cx, PAD_T, cx, PAD_T + plot_h, fill=T.LINE)
            bw = cell / 240.0
            line = []
            for i, (p, _v, _a) in enumerate(pts):
                line += [cx + bw * (i + .5), mid - ((p / pre - 1) * 100) / lim * (plot_h / 2)]
            if len(line) >= 4:
                self.create_line(*line, fill="#2f6fd0", width=1.0)
            vmax = max(1, max(v for _p, v, _a in pts))
            last = pre
            for i, (p, v, _a) in enumerate(pts):
                color = T.UP if p >= last else T.DOWN
                last = p
                vh = v / vmax * (vol_h - 3)
                if vh > .4:
                    self.create_line(cx + bw * (i + .5), vtop + vol_h - vh,
                                     cx + bw * (i + .5), vtop + vol_h, fill=color)
            self.create_text(cx + cell / 2, h - 8, text=label, fill=T.HINT,
                             font=T.F_NUM_SM, anchor="n")

        self._legend(w, self.title, "近 %d 日分时（相对昨收）" % len(days))

    def _hover_index(self, n, bw):
        if not self.hover:
            return None
        mx = self.hover[0]
        if not (PAD_L <= mx <= PAD_L + self._geom.get("plot_w", 0)):
            return None
        i = int((mx - PAD_L) / bw)
        return i if 0 <= i < n else None

    def _cross_kline(self, view, bw, x0, plot_w, vol_top, vol_h, h):
        mx, my = self.hover
        if not (x0 <= mx <= x0 + plot_w):
            return
        i = int((mx - x0) / bw)
        if i < 0 or i >= len(view):
            return
        b = view[i]
        cx = x0 + bw * (i + .5)
        self.create_line(cx, PAD_T, cx, h - PAD_B, fill=T.CROSS, dash=(3, 3))
        y = self._geom["Y"](b["c"])
        self.create_line(x0, y, x0 + plot_w, y, fill=T.CROSS, dash=(3, 3))
        self.create_rectangle(x0 + plot_w + 1, y - 8, x0 + plot_w + 62, y + 8,
                              fill="#1b2330", outline="")
        self.create_text(x0 + plot_w + 5, y, text=self._fmt(b["c"]), anchor="w",
                         fill="#fff", font=T.F_NUM_SM)
        prev = view[i - 1]["c"] if i else b["o"]
        chg = (b["c"] / prev - 1) * 100 if prev else 0
        self._tip(cx, mx, my, ["%s" % b["dt"],
                               "开 %s  高 %s" % (self._fmt(b["o"]), self._fmt(b["h"])),
                               "低 %s  收 %s" % (self._fmt(b["l"]), self._fmt(b["c"])),
                               "涨跌 %+.2f%%  量 %.1f万手" % (chg, b["v"] / 1e4)], plot_w)

    def _cross_minute(self, pts, pre, bw, x0, plot_w, vtop, vol_h, h):
        mx, my = self.hover
        if not (x0 <= mx <= x0 + plot_w):
            return
        i = int((mx - x0) / bw)
        if i < 0 or i >= len(pts):
            return
        p, v, a = pts[i]
        cx = x0 + bw * (i + .5)
        self.create_line(cx, PAD_T, cx, h - PAD_B, fill=T.CROSS, dash=(3, 3))
        y = self._geom["Y"](p)
        self.create_line(x0, y, x0 + plot_w, y, fill=T.CROSS, dash=(3, 3))
        mins = 9 * 60 + 30 + i
        if mins > 11 * 60 + 30:
            mins += 90
        self._tip(cx, mx, my, ["%02d:%02d" % (mins // 60, mins % 60),
                               "价 %s  %+.2f%%" % (self._fmt(p),
                                                   (p / pre - 1) * 100 if pre else 0),
                               "均 %s" % self._fmt(a), "量 %.0f手" % v], plot_w)

    def _tip(self, cx, mx, my, lines, plot_w):
        wdt, hgt = 138, 16 * len(lines) + 10
        x = cx + 12 if cx + 12 + wdt < PAD_L + plot_w else cx - 12 - wdt
        y = max(PAD_T, min(my - hgt / 2, self.winfo_height() - hgt - 28))
        self.create_rectangle(x, y, x + wdt, y + hgt, fill="#ffffff", outline=T.LINE)
        for k, line in enumerate(lines):
            self.create_text(x + 8, y + 8 + 16 * k, text=line, anchor="w",
                             fill=T.SUB if k else T.TEXT,
                             font=T.F_NUM_SM if k else T.F_UI_BD)

    def _legend(self, w, title, subtitle):
        if title:
            self.create_text(PAD_L, 12, text=title, anchor="w", fill=T.TEXT, font=T.F_UI_BD)
        if subtitle:
            self.create_text(w - PAD_R + 4, 12, text=subtitle, anchor="e", fill=T.HINT,
                             font=T.F_UI_SM)

    def _ma_legend(self, x0, mas, idx0, n):
        hx = self._hover_index(n, self._geom.get("bw", 6))
        if hx is None:
            hx = n - 1
        px = x0
        for period in (5, 10, 20, 60):
            series, color = mas[period]
            v = series[hx] if 0 <= hx < len(series) else None
            label = "MA%d %s" % (period, self._fmt(v, 2) if v else "--")
            self.create_text(px, PAD_T + 10, text=label, anchor="w", fill=color,
                             font=T.F_NUM_SM)
            px += 10 + len(label) * 6.0

    def _empty(self, w, h, msg):
        self.create_text(w / 2, h / 2, text=msg, fill=T.HINT, font=T.F_UI)

    @staticmethod
    def _fmt(v, digits=2):
        if v is None:
            return "--"
        if abs(v) >= 10000:
            return "%.0f" % v
        return ("%." + str(digits) + "f") % v
