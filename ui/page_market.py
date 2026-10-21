"""行情工作区：筛选、列表、详情、多股同列、右键操作。"""
import tkinter as tk
from tkinter import messagebox, ttk

from core import catalog, formula, store
from core.tdx import CAT_30MIN, CAT_DAY, CAT_QUARTER, CAT_YEAR
from . import theme as T
from .chart import ChartPanel
from .table import MarketTable

MARKS = ["全部", "自选股", "沪市", "深市", "北交所"]
BOARDS = ["全部板块", "沪市主板", "深市主板", "创业板", "科创板", "北交所"]
PERIODS = ["分时", "30分钟", "日线", "季线", "年线"]
CATS = {"30分钟": CAT_30MIN, "日线": CAT_DAY, "季线": CAT_QUARTER, "年线": CAT_YEAR}
ADJUSTS = ["不复权", "前复权", "后复权"]
ADJ_KEY = {"不复权": "none", "前复权": "qfq", "后复权": "hfq"}


class MarketPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.mark = "全部"
        self.board = "全部板块"
        self.industry = "全部行业"
        self.group = None
        self.selected = None
        self.period = "分时"
        self.adjust = "不复权"
        self.minute_days = 1
        self.sub_count = 1
        self.main_ind = "无"

        self._bars_raw = {}
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        bar = tk.Frame(self, bg=T.PANEL, height=70)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        row1 = tk.Frame(bar, bg=T.PANEL)
        row1.pack(fill="x", padx=10, pady=(8, 0))
        self.mark_btns = {}
        for name in MARKS:
            b = tk.Label(row1, text=name, bg=T.PANEL_ALT, fg=T.SUB, font=T.F_UI, padx=10,
                         pady=3, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, n=name: self._set_mark(n))
            self.mark_btns[name] = b
        self.lbl_count = tk.Label(row1, text="", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM)
        self.lbl_count.pack(side="right")

        row2 = tk.Frame(bar, bg=T.PANEL)
        row2.pack(fill="x", padx=10, pady=(6, 8))
        tk.Label(row2, text="板块", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_board = tk.StringVar(value=self.board)
        cb = ttk.Combobox(row2, textvariable=self.var_board, values=BOARDS, width=10,
                          state="readonly", font=T.F_UI_SM)
        cb.pack(side="left", padx=(4, 14))
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_board())
        tk.Label(row2, text="行业", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_industry = tk.StringVar(value=self.industry)
        inds = ["全部行业"] + catalog.industry_list()
        self.cb_industry = ttk.Combobox(row2, textvariable=self.var_industry, values=inds,
                                        width=14, state="readonly", font=T.F_UI_SM)
        self.cb_industry.pack(side="left", padx=(4, 0))
        self.cb_industry.bind("<<ComboboxSelected>>", lambda e: self._set_industry())

        self.group_bar = tk.Frame(row2, bg=T.PANEL)
        self.group_bar.pack(side="left", padx=(16, 0))

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=8, pady=(6, 6))

        left = tk.Frame(body, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        left.pack(side="left", fill="y")
        left.configure(width=700)
        left.pack_propagate(False)
        self.table = MarketTable(left, on_select=self._select, on_sort=self._sort,
                                 on_menu=self._menu)
        self.table.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self._build_detail(right)
        self._paint_marks()

    def _build_detail(self, parent):
        head = tk.Frame(parent, bg=T.PANEL)
        head.pack(fill="x", padx=12, pady=(8, 0))
        head.columnconfigure(0, weight=1)

        left = tk.Frame(head, bg=T.PANEL)
        left.grid(row=0, column=0, sticky="w")
        self.lbl_name = tk.Label(left, text="—", bg=T.PANEL, fg=T.TEXT,
                                 font=(T.UI_FAMILY, 14, "bold"))
        self.lbl_name.pack(side="left")
        self.lbl_code = tk.Label(left, text="", bg=T.PANEL, fg=T.HINT, font=T.F_NUM)
        self.lbl_code.pack(side="left", padx=(8, 0))
        self.btn_star = tk.Label(left, text="☆ 加自选", bg=T.PANEL_ALT, fg=T.SUB,
                                 font=T.F_UI_SM, padx=8, pady=2, cursor="hand2")
        self.btn_star.pack(side="left", padx=10)
        self.btn_star.bind("<Button-1>", lambda e: self._toggle_watch())

        rbox = tk.Frame(head, bg=T.PANEL)
        rbox.grid(row=0, column=1, sticky="e")
        self.lbl_price = tk.Label(rbox, text="--", bg=T.PANEL, fg=T.FLAT,
                                  font=(T.NUM_FAMILY, 21, "bold"))
        self.lbl_price.pack(anchor="e")
        self.lbl_change = tk.Label(rbox, text="", bg=T.PANEL, fg=T.SUB, font=T.F_NUM)
        self.lbl_change.pack(anchor="e")

        self.lbl_stats = tk.Label(head, text="", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM, anchor="w")
        self.lbl_stats.grid(row=1, column=0, columnspan=2, sticky="we", pady=(3, 4))

        tabs = tk.Frame(head, bg=T.PANEL)
        tabs.grid(row=2, column=0, columnspan=2, sticky="w")
        self.tab_btns = {}
        for name in PERIODS:
            b = tk.Label(tabs, text=name, bg=T.PANEL, fg=T.SUB, font=T.F_UI, padx=9, pady=4,
                         cursor="hand2")
            b.pack(side="left", padx=(0, 2))
            b.bind("<Button-1>", lambda e, n=name: self._set_period(n))
            self.tab_btns[name] = b

        opt = tk.Frame(head, bg=T.PANEL)
        opt.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 2))

        tk.Label(opt, text="日数", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_days = tk.StringVar(value="1")
        self.cb_days = ttk.Combobox(opt, textvariable=self.var_days, width=3, state="readonly",
                                    values=[str(i) for i in range(1, 11)], font=T.F_UI_SM)
        self.cb_days.pack(side="left", padx=(3, 10))
        self.cb_days.bind("<<ComboboxSelected>>", lambda e: self._set_days())

        tk.Label(opt, text="复权", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_adjust = tk.StringVar(value=self.adjust)
        self.cb_adjust = ttk.Combobox(opt, textvariable=self.var_adjust, width=6,
                                      state="readonly", values=ADJUSTS, font=T.F_UI_SM)
        self.cb_adjust.pack(side="left", padx=(3, 10))
        self.cb_adjust.bind("<<ComboboxSelected>>", lambda e: self._reload_kline())

        tk.Label(opt, text="主图", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_main = tk.StringVar(value="无")
        self.cb_main = ttk.Combobox(opt, textvariable=self.var_main, width=8, state="readonly",
                                    values=["无", "BOLL", "均线系统"], font=T.F_UI_SM)
        self.cb_main.pack(side="left", padx=(3, 10))
        self.cb_main.bind("<<ComboboxSelected>>", lambda e: self._apply_indicators())

        tk.Label(opt, text="副图", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left")
        self.var_subs = tk.StringVar(value="1")
        self.cb_subs = ttk.Combobox(opt, textvariable=self.var_subs, width=3, state="readonly",
                                    values=["0", "1", "2", "3"], font=T.F_UI_SM)
        self.cb_subs.pack(side="left", padx=(3, 10))
        self.cb_subs.bind("<<ComboboxSelected>>", lambda e: self._apply_indicators())

        subrow = tk.Frame(head, bg=T.PANEL)
        subrow.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.sub_vars = []
        self.sub_boxes = []
        subs = ["无"] + [k for k in ("MACD", "KDJ", "RSI", "量能异动", "趋势强度")
                         if k in self.app.formulas]
        for i in range(3):
            tk.Label(subrow, text="副图%d" % (i + 1), bg=T.PANEL, fg=T.HINT,
                     font=T.F_UI_SM).pack(side="left")
            var = tk.StringVar(value=("MACD" if i == 0 else "无"))
            cb = ttk.Combobox(subrow, textvariable=var, width=9, state="readonly",
                              values=subs, font=T.F_UI_SM)
            cb.pack(side="left", padx=(3, 8))
            cb.bind("<<ComboboxSelected>>", lambda e: self._apply_indicators())
            self.sub_vars.append(var)
            self.sub_boxes.append(cb)

        mgr = tk.Label(subrow, text="公式管理器", bg=T.PANEL_ALT, fg=T.ACCENT, font=T.F_UI_SM,
                       padx=8, pady=2, cursor="hand2")
        mgr.pack(side="left", padx=(4, 8))
        mgr.bind("<Button-1>", lambda e: FormulaManager(self, self.app))
        tk.Label(subrow, text="Ctrl+滚轮缩放 · 拖动平移 · 双击复位", bg=T.PANEL, fg=T.HINT,
                 font=T.F_UI_SM).pack(side="left")

        self.chart = ChartPanel(parent)
        self.chart.pack(fill="both", expand=True, padx=8, pady=(2, 6))
        self._paint_period()

    # ------------------------------------------------------------ 筛选
    def _paint_marks(self):
        for name, b in self.mark_btns.items():
            if name == self.mark:
                b.configure(bg=T.ACCENT_SOFT, fg=T.ACCENT, font=T.F_UI_BD)
            else:
                b.configure(bg=T.PANEL_ALT, fg=T.SUB, font=T.F_UI)
        self._paint_groups()

    def _paint_groups(self):
        for w in self.group_bar.winfo_children():
            w.destroy()
        if self.mark != "自选股":
            return
        tk.Label(self.group_bar, text="分组", bg=T.PANEL, fg=T.HINT,
                 font=T.F_UI_SM).pack(side="left", padx=(0, 4))
        for name in list(self.app.watch_groups.keys()):
            on = (name == self.group)
            b = tk.Label(self.group_bar, text="%s(%d)" % (name, len(self.app.watch_groups[name])),
                         bg=T.ACCENT_SOFT if on else T.PANEL_ALT,
                         fg=T.ACCENT if on else T.SUB, font=T.F_UI_SM, padx=7, pady=2,
                         cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, n=name: self._set_group(n))
        add = tk.Label(self.group_bar, text="+ 新建分组", bg=T.PANEL_ALT, fg=T.SUB,
                       font=T.F_UI_SM, padx=7, pady=2, cursor="hand2")
        add.pack(side="left")
        add.bind("<Button-1>", lambda e: self._new_group())

    def _set_mark(self, name):
        self.mark = name
        self.group = None
        self._paint_marks()
        self.refresh()

    def _set_board(self):
        self.board = self.var_board.get()
        self.refresh()

    def _set_industry(self):
        self.industry = self.var_industry.get()
        self.refresh()

    def _set_group(self, name):
        self.group = name
        self._paint_groups()
        self.refresh()

    def _new_group(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("新建分组", "分组名称（例如：半导体、电力）", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        self.app.watch_groups.setdefault(name, [])
        store.save_watch_groups(self.app.watch_groups)
        self.group = name
        self._paint_groups()
        self.refresh()

    # ------------------------------------------------------------ 列表
    def universe(self):
        q = self.app.quotes
        out = []
        for market, code, _name, board in self.app.stocks:
            if self.mark == "自选股":
                if not self._in_group(code):
                    continue
            elif self.mark == "沪市" and market != 1:
                continue
            elif self.mark == "深市" and market != 0:
                continue
            elif self.mark == "北交所" and market != 2:
                continue
            label = catalog.market_label(market, code, board)
            if self.board != "全部板块" and label != self.board:
                continue
            ind = catalog.industry_of(code)
            if self.industry != "全部行业" and ind != self.industry:
                continue
            item = q.get(code)
            if item:
                out.append(item)
        kw = (self.app.keyword or "").strip().upper()
        if kw:
            out = [q for q in out if kw in q.code or kw in q.name.upper()
                   or kw in catalog.initials(q.name)]
        return out

    def _in_group(self, code):
        if self.group:
            return code in self.app.watch_groups.get(self.group, [])
        return any(code in v for v in self.app.watch_groups.values())

    def refresh(self):
        rows = self.universe()
        key, desc = self.table.sort_key, self.table.sort_desc
        if key == "name":
            rows.sort(key=lambda r: r.name, reverse=desc)
        else:
            rows.sort(key=lambda r: (r.vr if key == "vr" else getattr(r, key, 0)) or 0,
                      reverse=desc)
        data = []
        for r in rows:
            st = self.app.by_code.get(r.code)
            data.append({
                "code": r.code, "name": r.name, "price": r.price, "pct": r.pct,
                "vr": r.vr, "vol": r.vol, "pre_close": r.pre_close,
                "board": catalog.market_label(st[0], r.code, st[3]) if st else "",
                "industry": catalog.industry_of(r.code),
            })
        self.table.set_rows(data)
        self.lbl_count.configure(text="%d 只" % len(data))
        if self.selected:
            self.table.select(self.selected)

    def _sort(self, key):
        if self.table.sort_key == key:
            self.table.sort_desc = not self.table.sort_desc
        else:
            self.table.sort_key, self.table.sort_desc = key, True
        self.refresh()

    def _select(self, code):
        self.selected = code
        self.table.select(code)
        self._update_header()
        self._update_star()
        self._reload()

    def _menu(self, row, x, y):
        code = row["code"]
        m = tk.Menu(self, tearoff=0, font=T.F_UI)
        groups = list(self.app.watch_groups.keys()) or ["默认分组"]
        add = tk.Menu(m, tearoff=0, font=T.F_UI)
        for g in groups:
            add.add_command(label=g, command=lambda g=g: self._add_to_group(code, g))
        add.add_separator()
        add.add_command(label="新建分组…", command=lambda: self._add_to_new_group(code))
        m.add_cascade(label="添加至自选股", menu=add)
        m.add_command(label="展示该板块内股票（%s）" % (row.get("board") or "板块"),
                      command=lambda: self._show_board(row.get("board")))
        m.add_command(label="展示该行业内股票（%s）" % (row.get("industry") or "行业"),
                      command=lambda: self._show_industry(row.get("industry")))
        m.add_separator()
        m.add_command(label="多股同列（自选前 4 只）", command=self._multi_view)
        m.add_command(label="复制代码", command=lambda: self._copy(code))
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _add_to_group(self, code, group):
        self.app.watch_groups.setdefault(group, [])
        if code not in self.app.watch_groups[group]:
            self.app.watch_groups[group].append(code)
            store.save_watch_groups(self.app.watch_groups)
        self._update_star()
        self.app.toast("已加入自选", "%s → %s" % (code, group))

    def _add_to_new_group(self, code):
        from tkinter import simpledialog
        name = simpledialog.askstring("新建分组", "分组名称", parent=self)
        if name and name.strip():
            self._add_to_group(code, name.strip())
            self._paint_groups()

    def _show_board(self, label):
        if not label:
            return
        self.mark = "全部"
        self.board = label
        self.var_board.set(label)
        self._paint_marks()
        self.refresh()

    def _show_industry(self, industry):
        if not industry:
            return
        self.industry = industry
        self.var_industry.set(industry)
        self.refresh()

    def _copy(self, code):
        self.clipboard_clear()
        self.clipboard_append(code)

    def _multi_view(self):
        codes = list(dict.fromkeys([c for v in self.app.watch_groups.values() for c in v]))[:4]
        if self.selected and self.selected not in codes:
            codes = ([self.selected] + codes)[:4]
        if not codes:
            self.app.toast("多股同列", "请先添加自选股")
            return
        MultiView(self, self.app, codes)

    def _toggle_watch(self):
        if not self.selected:
            return
        group = self.group or (list(self.app.watch_groups.keys())[0]
                               if self.app.watch_groups else "默认分组")
        lst = self.app.watch_groups.setdefault(group, [])
        if self.selected in lst:
            lst.remove(self.selected)
        else:
            lst.append(self.selected)
        store.save_watch_groups(self.app.watch_groups)
        self._update_star()
        if self.mark == "自选股":
            self.refresh()

    def _update_star(self):
        on = any(self.selected in v for v in self.app.watch_groups.values()) if self.selected else False
        self.btn_star.configure(text="★ 已自选" if on else "☆ 加自选",
                                fg=T.WARN if on else T.SUB)

    # ------------------------------------------------------------ 详情
    def _paint_period(self):
        for name, b in self.tab_btns.items():
            b.configure(fg=T.ACCENT if name == self.period else T.SUB,
                        font=T.F_UI_BD if name == self.period else T.F_UI)
        is_minute = self.period == "分时"
        self.cb_days.configure(state="readonly" if is_minute else "disabled")
        self.cb_adjust.configure(state="disabled" if is_minute else "readonly")

    def _set_period(self, name):
        self.period = name
        self._paint_period()
        self._reload()

    def _set_days(self):
        self.minute_days = int(self.var_days.get())
        self._reload()

    def _reload(self):
        if not self.selected:
            return
        st = self.app.by_code.get(self.selected)
        if not st:
            return
        if self.period == "分时":
            self.app.submit("mk:minute", (st[0], self.selected, self.minute_days))
        else:
            self._reload_kline()

    def _reload_kline(self):
        if not self.selected or self.period == "分时":
            return
        st = self.app.by_code.get(self.selected)
        if not st:
            return
        self.adjust = self.var_adjust.get()
        self.app.submit("mk:kline", (st[0], self.selected, self.period, ADJ_KEY[self.adjust]))

    def update_quotes(self):
        q = self.app.quotes.get(self.selected) if self.selected else None
        if q:
            self._update_header()

    def _update_header(self):
        q = self.app.quotes.get(self.selected) if self.selected else None
        if not q:
            return
        st = self.app.by_code.get(self.selected)
        color = T.color_of(q.pct)
        self.lbl_name.configure(text=q.name)
        label = catalog.market_label(st[0], q.code, st[3]) if st else ""
        ind = catalog.industry_of(q.code)
        self.lbl_code.configure(text="%s · %s%s" % (q.code, label, (" · " + ind) if ind else ""))
        self.lbl_price.configure(text=("%.2f" % q.price) if q.price else "--", fg=color)
        self.lbl_change.configure(
            text="%+.2f   %+.2f%%" % (q.price - q.pre_close, q.pct) if q.pre_close else "--",
            fg=color)
        amp = ((q.high - q.low) / q.pre_close * 100) if q.pre_close else 0
        self.lbl_stats.configure(
            text="今开 %.2f   最高 %.2f   最低 %.2f   昨收 %.2f   振幅 %.2f%%   量比 %s   "
                 "成交额 %.2f亿" % (q.open, q.high, q.low, q.pre_close, amp,
                                    ("%.2f" % q.vr) if q.vr else "--", (q.amount or 0) / 1e8))

    def _apply_indicators(self):
        bars = self.chart.bars if self.chart.mode == "kline" else []
        if not bars:
            self.chart.set_indicators(None, [])
            return
        ctx = self._ctx(bars)
        n = len(bars)
        overlay = None
        name = self.var_main.get()
        if name != "无" and name in self.app.formulas:
            try:
                outs = formula.evaluate(self.app.formulas[name], ctx, n)
                overlay = {"name": name, "outputs": outs}
            except formula.FormulaError:
                overlay = None
        subs = []
        for i in range(int(self.var_subs.get())):
            nm = self.sub_vars[i].get()
            if nm == "无" or nm not in self.app.formulas:
                continue
            try:
                outs = formula.evaluate(self.app.formulas[nm], ctx, n)
                subs.append({"name": nm, "outputs": outs})
            except formula.FormulaError as exc:
                self.app.toast("指标错误", "%s: %s" % (nm, exc))
        self.chart.set_indicators(overlay, subs)

    @staticmethod
    def _ctx(bars):
        return {
            "O": [b["o"] for b in bars], "H": [b["h"] for b in bars],
            "L": [b["l"] for b in bars], "C": [b["c"] for b in bars],
            "V": [b["v"] for b in bars], "A": [b["a"] for b in bars],
            "OPEN": [b["o"] for b in bars], "HIGH": [b["h"] for b in bars],
            "LOW": [b["l"] for b in bars], "CLOSE": [b["c"] for b in bars],
            "VOL": [b["v"] for b in bars], "AMOUNT": [b["a"] for b in bars],
        }

    def on_data(self, kind, payload):
        if kind == "mk:kline":
            code, period, bars, adjust = payload
            if code != self.selected or period != self.period:
                return
            st = self.app.by_code.get(code)
            title = "%s %s · %s%s" % (st[2] if st else code, code, period,
                                      "" if adjust == "none" else " · " + self.var_adjust.get())
            sub = "共 %d 根 · %s ~ %s" % (len(bars), bars[0]["dt"][:10],
                                         bars[-1]["dt"][:10]) if bars else "无数据"
            self.chart.set_kline(bars, title, sub)
            self._apply_indicators()
        elif kind == "mk:minute":
            code, data = payload
            if code != self.selected or self.period != "分时" or not data:
                return
            st = self.app.by_code.get(code)
            title = "%s %s · 分时" % (st[2] if st else code, code)
            self.chart.set_indicators(None, [])
            self.chart.set_minute(data["days"], data["labels"], data["pres"], title,
                                  "%d 日" % len(data["days"]), multi=len(data["days"]) > 1)


class MultiView(tk.Toplevel):
    """多股同列：2×2 迷你走势。"""

    def __init__(self, master, app, codes):
        super().__init__(master)
        self.title("多股同列 · " + " ".join(codes))
        self.geometry("1000x680")
        self.configure(bg=T.BG)
        self.app = app
        for i, code in enumerate(codes[:4]):
            st = app.by_code.get(code)
            f = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
            f.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            tk.Label(f, text="%s %s" % (st[2] if st else "", code), bg=T.PANEL, fg=T.TEXT,
                     font=T.F_UI_BD, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
            ch = ChartPanel(f, height=240)
            ch.pack(fill="both", expand=True, padx=6, pady=6)
            app.submit("mk:mini", (st[0], code, ch))
        for r in range(2):
            self.rowconfigure(r, weight=1)
        for c in range(2):
            self.columnconfigure(c, weight=1)


class FormulaManager(tk.Toplevel):
    """公式管理器：查看、导入、删除自定义指标公式。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("公式管理器")
        self.geometry("720x480")
        self.configure(bg=T.BG)

        left = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.configure(width=210)
        left.pack_propagate(False)
        tk.Label(left, text="指标列表", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM).pack(
            anchor="w", padx=10, pady=(8, 2))
        self.listbox = tk.Listbox(left, bd=0, highlightthickness=0, font=T.F_UI,
                                  selectbackground=T.SEL, selectforeground=T.TEXT)
        self.listbox.pack(fill="both", expand=True, padx=6, pady=4)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._preview())

        right = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        self.text = tk.Text(right, bd=0, highlightthickness=0, font=(T.NUM_FAMILY, 9),
                            wrap="none", bg="#fbfcfe", fg=T.TEXT)
        self.text.pack(fill="both", expand=True, padx=8, pady=8)

        btns = tk.Frame(self, bg=T.BG)
        btns.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
        tk.Button(btns, text="导入公式…", command=self._import, relief="flat",
                  bg=T.ACCENT, fg="#fff", padx=12, pady=4).pack(side="left")
        tk.Button(btns, text="删除自定义", command=self._delete, relief="flat",
                  bg=T.PANEL_ALT, fg=T.TEXT, padx=12, pady=4).pack(side="left", padx=8)
        tk.Button(btns, text="校验语法", command=self._check, relief="flat",
                  bg=T.PANEL_ALT, fg=T.TEXT, padx=12, pady=4).pack(side="left")
        tk.Button(btns, text="关闭", command=self.destroy, relief="flat",
                  bg=T.PANEL_ALT, fg=T.TEXT, padx=12, pady=4).pack(side="right")
        self._fill()

    def _fill(self):
        self.listbox.delete(0, "end")
        for name in sorted(self.app.formulas):
            tag = "内置" if name in self.app.builtin else "自定义"
            self.listbox.insert("end", "%s  [%s]" % (name, tag))

    def _current(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0]).split("  [")[0]

    def _preview(self):
        name = self._current()
        if not name:
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.app.formulas.get(name, ""))

    def _import(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self, filetypes=[
            ("指标公式", "*.txt *.tdx *.form"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            src = open(path, "r", encoding="utf-8", errors="replace").read()
            formula.parse(src)
        except formula.FormulaError as exc:
            messagebox.showerror("语法错误", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc), parent=self)
            return
        name = store.save_user_formula(path.split("/")[-1].split("\\")[-1].rsplit(".", 1)[0], src)
        self.app.formulas[name] = src
        self.app.refresh_formula_boxes()
        self._fill()
        self.app.toast("公式已导入", name)

    def _delete(self):
        name = self._current()
        if not name:
            return
        if name in self.app.builtin:
            messagebox.showinfo("提示", "内置公式不可删除。", parent=self)
            return
        import os
        path = os.path.join(store.user_formula_dir(), name + ".txt")
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        self.app.formulas.pop(name, None)
        self.app.refresh_formula_boxes()
        self._fill()
        self.text.delete("1.0", "end")

    def _check(self):
        src = self.text.get("1.0", "end")
        try:
            stmts = formula.parse(src)
            messagebox.showinfo("校验通过", "解析到 %d 条语句。" % len(stmts), parent=self)
        except formula.FormulaError as exc:
            messagebox.showerror("语法错误", str(exc), parent=self)
