"""选股 / 提醒 / 交易 / 复盘 四个工作区。"""
import tkinter as tk
from tkinter import ttk

from core import catalog, store
from . import theme as T

ALERT_TYPES = ["价格上穿", "价格下穿", "涨幅突破", "量比突破"]

SCREENER_FIELDS = [
    ("pct", "涨跌幅%"), ("price", "现价"), ("vr", "量比"),
    ("volw", "成交量(万手)"), ("amount", "成交额(亿)"),
]
OPS = [">", ">=", "<", "<=", "between"]

REVIEW_POINTS = [
    ("09:35", "指数定性", "示例观点：指数处于区间震荡，尚未确认趋势", "演示数据。把这里换成你自己的复盘结论即可。"),
    ("10:10", "确认信号", "示例观点：等待放量站上 20 日均线再谈趋势", "把「确认条件」写成可执行的判断，而不是感觉。"),
    ("10:45", "风控", "示例观点：单笔亏损控制在总资产 1% 以内", "先定义最大可承受亏损，再决定仓位。"),
    ("11:20", "节奏", "示例观点：分批建仓，避免一次打满", "震荡市用 3:3:4，趋势确认后再加。"),
    ("13:30", "主线", "示例观点：关注成交量持续放大的板块", "量能是板块能否延续的第一手证据。"),
    ("14:05", "分化", "示例观点：同一板块内龙头与补涨股节奏不同", "先做龙头，补涨只做一次。"),
    ("14:40", "筹码", "示例观点：用「距 60 日高点」衡量上方套牢盘", "作为筹码压力的代理指标。"),
    ("15:00", "情绪", "示例观点：连板高度下降时降低仓位", "退潮期的第一原则是减少出手。"),
]

SYSTEM_DSL = {
    "name": "示例体系 · 趋势跟随",
    "regime": "震荡市 / 右侧确认",
    "entry": "站上 20 日均线 + 量比放大 + 板块共振",
    "position": "3:3:4 分批，首仓 ≤ 计划仓位 40%",
    "stop": "跌破入场 K 线低点 -3%；单笔亏损 ≤ 总资产 1%",
    "filters": [("pct", "between", "-3,6"), ("vr", ">", "1.5")],
}


def _page_title(parent, title, desc):
    head = tk.Frame(parent, bg=T.PANEL)
    head.pack(fill="x", padx=14, pady=(12, 6))
    tk.Label(head, text=title, bg=T.PANEL, fg=T.TEXT,
             font=(T.UI_FAMILY, 13, "bold")).pack(side="left")
    tk.Label(head, text=desc, bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM).pack(side="left", padx=10)
    return head


class ScreenerPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.rules = [{"f": "pct", "op": ">", "v": "3"}]
        self.logic = "AND"
        self._build()

    def _build(self):
        panel = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        panel.pack(side="left", fill="y", padx=(8, 4), pady=8)
        panel.configure(width=330)
        panel.pack_propagate(False)
        _page_title(panel, "条件选股", "全市场实时扫描")
        self.rules_box = tk.Frame(panel, bg=T.PANEL)
        self.rules_box.pack(fill="x", padx=12)
        self._paint_rules()

        row = tk.Frame(panel, bg=T.PANEL)
        row.pack(fill="x", padx=12, pady=8)
        self.var_logic = tk.StringVar(value="AND")
        ttk.Combobox(row, textvariable=self.var_logic, values=["AND", "OR"], width=6,
                     state="readonly").pack(side="left")
        tk.Button(row, text="+ 条件", command=self._add_rule, relief="flat", bg=T.PANEL_ALT,
                  fg=T.TEXT, padx=10, pady=3).pack(side="left", padx=6)
        tk.Button(panel, text="▶ 执行筛选", command=self.run, relief="flat", bg=T.ACCENT,
                  fg="#fff", padx=16, pady=6).pack(fill="x", padx=12, pady=(6, 10))

        self.lbl = tk.Label(panel, text="", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM,
                            justify="left", anchor="w")
        self.lbl.pack(fill="x", padx=12)

        right = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        _page_title(right, "筛选结果", "双击查看行情")
        cols = ("name", "code", "price", "pct", "vr", "volume", "board", "industry")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=24)
        for key, title, width in (("name", "名称", 110), ("code", "代码", 74),
                                  ("price", "现价", 70), ("pct", "涨跌幅", 76),
                                  ("vr", "量比", 56), ("volume", "成交量(万手)", 92),
                                  ("board", "板块", 84), ("industry", "细分行业", 110)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w" if key in ("name", "code", "board", "industry") else "e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.bind("<Double-Button-1>", self._open)

    def _paint_rules(self):
        for w in self.rules_box.winfo_children():
            w.destroy()
        for i, r in enumerate(self.rules):
            row = tk.Frame(self.rules_box, bg=T.PANEL)
            row.pack(fill="x", pady=3)
            vf = tk.StringVar(value=dict(SCREENER_FIELDS).get(r["f"], "涨跌幅%"))
            cb = ttk.Combobox(row, values=[x[1] for x in SCREENER_FIELDS], width=11,
                              state="readonly", textvariable=vf)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e, i=i, v=vf: self._set_field(i, v.get()))
            vo = tk.StringVar(value=r["op"])
            cbo = ttk.Combobox(row, values=OPS, width=4, state="readonly", textvariable=vo)
            cbo.pack(side="left", padx=4)
            cbo.bind("<<ComboboxSelected>>", lambda e, i=i, v=vo: self._set_op(i, v.get()))
            ve = tk.StringVar(value=r["v"])
            ent = tk.Entry(row, width=9, textvariable=ve, relief="flat", bg=T.PANEL_ALT)
            ent.pack(side="left", padx=2, ipady=2)
            ent.bind("<KeyRelease>", lambda e, i=i, v=ve: self._set_val(i, v.get()))
            tk.Label(row, text="✕", bg=T.PANEL, fg=T.HINT, cursor="hand2").pack(side="left", padx=4)
            row.winfo_children()[-1].bind("<Button-1>", lambda e, i=i: self._del_rule(i))

    def _set_field(self, i, label):
        for k, name in SCREENER_FIELDS:
            if name == label:
                self.rules[i]["f"] = k

    def _set_op(self, i, op):
        self.rules[i]["op"] = op

    def _set_val(self, i, v):
        self.rules[i]["v"] = v

    def _add_rule(self):
        self.rules.append({"f": "vr", "op": ">", "v": "1.5"})
        self._paint_rules()

    def _del_rule(self, i):
        if len(self.rules) > 1:
            self.rules.pop(i)
            self._paint_rules()

    def _value(self, q, key):
        if key == "volw":
            return (q.vol or 0) / 1e4
        if key == "amount":
            return (q.amount or 0) / 1e8
        return getattr(q, key, 0) or 0

    def run(self):
        rows = []
        for q in self.app.quotes.values():
            checks = []
            for r in self.rules:
                v = self._value(q, r["f"])
                try:
                    if r["op"] == "between":
                        a, b = [float(x) for x in str(r["v"]).split(",")[:2]]
                        checks.append(a <= v <= b)
                    else:
                        n = float(r["v"])
                        checks.append({">": v > n, ">=": v >= n, "<": v < n,
                                       "<=": v <= n}[r["op"]])
                except Exception:
                    checks.append(False)
            if not checks:
                continue
            if (all(checks) if self.var_logic.get() == "AND" else any(checks)):
                rows.append(q)
        rows.sort(key=lambda q: q.pct, reverse=True)
        self.tree.delete(*self.tree.get_children())
        for q in rows[:500]:
            st = self.app.by_code.get(q.code)
            self.tree.insert("", "end", values=(
                q.name, q.code, "%.2f" % q.price if q.price else "--", "%+.2f%%" % q.pct,
                "%.2f" % q.vr if q.vr else "--", "%.1f" % ((q.vol or 0) / 1e4),
                catalog.market_label(st[0], q.code, st[3]) if st else "",
                catalog.industry_of(q.code)))
        self.lbl.configure(text="命中 %d 只（全市场 %d 只参与扫描）" % (len(rows), len(self.app.quotes)))

    def _open(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        code = self.tree.item(sel[0], "values")[1]
        self.app.open_stock(code)


class AlertsPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self._build()

    def _build(self):
        form = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        form.pack(side="left", fill="y", padx=(8, 4), pady=8)
        form.configure(width=320)
        form.pack_propagate(False)
        _page_title(form, "新建提醒", "触发后即时弹窗")

        body = tk.Frame(form, bg=T.PANEL)
        body.pack(fill="x", padx=12, pady=6)
        tk.Label(body, text="代码", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM).grid(row=0, column=0, sticky="w")
        self.var_code = tk.StringVar(value="600519")
        tk.Entry(body, textvariable=self.var_code, width=14, relief="flat",
                 bg=T.PANEL_ALT).grid(row=0, column=1, pady=4, ipady=3)
        tk.Label(body, text="类型", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM).grid(row=1, column=0, sticky="w")
        self.var_type = tk.StringVar(value=ALERT_TYPES[0])
        ttk.Combobox(body, textvariable=self.var_type, values=ALERT_TYPES, width=12,
                     state="readonly").grid(row=1, column=1, pady=4)
        tk.Label(body, text="阈值", bg=T.PANEL, fg=T.SUB, font=T.F_UI_SM).grid(row=2, column=0, sticky="w")
        self.var_val = tk.StringVar(value="1400")
        tk.Entry(body, textvariable=self.var_val, width=14, relief="flat",
                 bg=T.PANEL_ALT).grid(row=2, column=1, pady=4, ipady=3)

        tk.Button(form, text="创建提醒", command=self._add, relief="flat", bg=T.ACCENT,
                  fg="#fff", padx=16, pady=6).pack(fill="x", padx=12, pady=10)

        right = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        _page_title(right, "提醒列表", "后台每轮行情求值")
        cols = ("time", "code", "name", "type", "target", "status")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=20)
        for key, title, width in (("time", "时间", 90), ("code", "代码", 80),
                                  ("name", "名称", 110), ("type", "类型", 100),
                                  ("target", "阈值", 90), ("status", "状态", 90)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        tk.Button(right, text="删除选中", command=self._del, relief="flat", bg=T.PANEL_ALT,
                  fg=T.TEXT, padx=12, pady=4).pack(anchor="e", padx=10, pady=(0, 10))
        self.refresh()

    def _add(self):
        code = self.var_code.get().strip()
        if code not in self.app.by_code:
            self.app.toast("提醒", "代码不存在：%s" % code)
            return
        try:
            val = float(self.var_val.get())
        except ValueError:
            self.app.toast("提醒", "阈值必须是数字")
            return
        self.app.alerts.append({"code": code, "type": self.var_type.get(), "target": val,
                                "status": "监听中", "time": "", "last": None})
        self.refresh()

    def _del(self):
        sel = self.tree.selection()
        for sid in sel:
            idx = int(self.tree.item(sid, "values")[0])
            if 0 <= idx < len(self.app.alerts):
                self.app.alerts[idx] = None
        self.app.alerts = [a for a in self.app.alerts if a]
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, a in enumerate(self.app.alerts):
            name = self.app.by_code.get(a["code"], (0, "", a["code"], ""))[2]
            self.tree.insert("", "end", values=(
                a.get("time") or "--", a["code"], name, a["type"],
                a["target"], a.get("status", "监听中")))

    def on_tick(self):
        self.refresh()


class TradePage(tk.Frame):
    """模拟盘：验证下单流程与风控，不接真实柜台。"""

    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.cash = 1000000.0
        self.positions = {"600519": [100, 1320.0]}
        self.orders = []
        self._build()

    def _build(self):
        panel = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        panel.pack(side="left", fill="y", padx=(8, 4), pady=8)
        panel.configure(width=330)
        panel.pack_propagate(False)
        _page_title(panel, "模拟下单", "不连接真实柜台")

        body = tk.Frame(panel, bg=T.PANEL)
        body.pack(fill="x", padx=12, pady=6)
        self.var_code = tk.StringVar(value="600519")
        self.var_price = tk.StringVar(value="1330")
        self.var_qty = tk.StringVar(value="100")
        for i, (label, var) in enumerate((("代码", self.var_code), ("价格", self.var_price),
                                          ("数量", self.var_qty))):
            tk.Label(body, text=label, bg=T.PANEL, fg=T.SUB,
                     font=T.F_UI_SM).grid(row=i, column=0, sticky="w")
            tk.Entry(body, textvariable=var, width=14, relief="flat",
                     bg=T.PANEL_ALT).grid(row=i, column=1, pady=4, ipady=3)
        btns = tk.Frame(panel, bg=T.PANEL)
        btns.pack(fill="x", padx=12, pady=8)
        tk.Button(btns, text="买入", command=lambda: self._order("买入"), relief="flat",
                  bg=T.UP, fg="#fff", padx=18, pady=5).pack(side="left")
        tk.Button(btns, text="卖出", command=lambda: self._order("卖出"), relief="flat",
                  bg=T.DOWN, fg="#fff", padx=18, pady=5).pack(side="left", padx=8)
        self.lbl_acc = tk.Label(panel, text="", bg=T.PANEL, fg=T.SUB, font=T.F_NUM_SM,
                                justify="left", anchor="w")
        self.lbl_acc.pack(fill="x", padx=12, pady=(4, 10))

        right = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        _page_title(right, "委托记录", "前置校验：代码 / 价格 / 数量 / 资金 / 持仓")
        cols = ("time", "code", "side", "price", "qty", "amount", "status")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=22)
        for key, title, width in (("time", "时间", 90), ("code", "代码", 80),
                                  ("side", "方向", 70), ("price", "价格", 80),
                                  ("qty", "数量", 70), ("amount", "金额", 110),
                                  ("status", "状态", 90)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._paint_account()

    def _paint_account(self):
        mv = 0.0
        for code, (qty, cost) in self.positions.items():
            q = self.app.quotes.get(code)
            mv += (q.price if q and q.price else cost) * qty
        self.lbl_acc.configure(
            text="总资产  ¥%s\n可用资金  ¥%s\n持仓市值  ¥%s\n持仓 %d 只" % (
                format(int(self.cash + mv), ","), format(int(self.cash), ","),
                format(int(mv), ","), len(self.positions)))

    def _order(self, side):
        import time as _t
        code = self.var_code.get().strip()
        q = self.app.quotes.get(code)
        try:
            price = float(self.var_price.get())
            qty = int(self.var_qty.get())
        except ValueError:
            self.app.toast("委托失败", "价格/数量格式错误")
            return
        if not q:
            self.app.toast("委托失败", "代码不存在或行情未加载")
            return
        if qty <= 0 or qty % 100:
            self.app.toast("委托失败", "数量必须为 100 股整数倍")
            return
        if q.pre_close and abs(price / q.pre_close - 1) > 0.21:
            self.app.toast("委托失败", "价格超出涨跌停范围")
            return
        amt = price * qty
        if side == "买入":
            if amt > self.cash:
                self.app.toast("委托失败", "可用资金不足")
                return
            self.cash -= amt
            pos = self.positions.setdefault(code, [0, price])
            pos[1] = (pos[1] * pos[0] + amt) / (pos[0] + qty)
            pos[0] += qty
        else:
            pos = self.positions.get(code)
            if not pos or pos[0] < qty:
                self.app.toast("委托失败", "可卖数量不足")
                return
            pos[0] -= qty
            self.cash += amt
            if pos[0] == 0:
                self.positions.pop(code, None)
        self.orders.append((_t.strftime("%H:%M:%S"), code, side, price, qty, amt, "已成交"))
        self.tree.insert("", "end", values=(_t.strftime("%H:%M:%S"), code, side, "%.2f" % price,
                                            qty, "¥%s" % format(int(amt), ","), "已成交"))
        self._paint_account()

    def on_tick(self):
        self._paint_account()


class ReviewPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self._build()

    def _build(self):
        left = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        _page_title(left, "复盘笔记 · 示例数据", "结构演示 · 可替换为自己的解析结果")
        body = tk.Frame(left, bg=T.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        canvas = tk.Canvas(body, bg=T.PANEL, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview, width=10,
                          relief="flat", bd=0)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        inner = tk.Frame(canvas, bg=T.PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        for ts, tag, claim, note in REVIEW_POINTS:
            card = tk.Frame(inner, bg="#fbfcfe", highlightbackground=T.LINE, highlightthickness=1)
            card.pack(fill="x", pady=4, padx=2)
            top = tk.Frame(card, bg="#fbfcfe")
            top.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(top, text=ts, bg=T.ACCENT_SOFT, fg=T.ACCENT, font=T.F_NUM_SM,
                     padx=6).pack(side="left")
            tk.Label(top, text=tag, bg=T.PANEL_ALT, fg=T.SUB, font=T.F_UI_SM,
                     padx=6).pack(side="left", padx=6)
            tk.Label(card, text=claim, bg="#fbfcfe", fg=T.TEXT, font=T.F_UI_BD,
                     anchor="w", justify="left", wraplength=520).pack(fill="x", padx=10)
            tk.Label(card, text=note, bg="#fbfcfe", fg=T.SUB, font=T.F_UI_SM, anchor="w",
                     justify="left", wraplength=520).pack(fill="x", padx=10, pady=(2, 8))

        right = tk.Frame(self, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
        right.pack(side="left", fill="y", padx=(4, 8), pady=8)
        right.configure(width=380)
        right.pack_propagate(False)
        _page_title(right, "交易体系 DSL", "可复用的执行规则")
        box = tk.Frame(right, bg=T.PANEL)
        box.pack(fill="x", padx=14, pady=8)
        for k, v in (("名称", SYSTEM_DSL["name"]), ("市况", SYSTEM_DSL["regime"]),
                     ("入场", SYSTEM_DSL["entry"]), ("仓位", SYSTEM_DSL["position"]),
                     ("止损", SYSTEM_DSL["stop"])):
            tk.Label(box, text=k, bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM, anchor="w").pack(fill="x")
            tk.Label(box, text=v, bg=T.PANEL, fg=T.TEXT, font=T.F_UI, anchor="w",
                     justify="left", wraplength=330).pack(fill="x", pady=(0, 6))
        tk.Button(right, text="应用到选股器", command=self._apply, relief="flat", bg=T.ACCENT,
                  fg="#fff", padx=14, pady=6).pack(fill="x", padx=14, pady=(4, 10))
        tk.Label(right, text="本页为演示数据，仅展示「观点 → 交易体系」的结构，不构成投资建议。",
                 bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM, wraplength=330,
                 justify="left").pack(fill="x", padx=14, pady=(0, 12))

    def _apply(self):
        page = self.app.pages.get("选股")
        if not page:
            return
        page.rules = [{"f": f, "op": op, "v": v} for f, op, v in SYSTEM_DSL["filters"]]
        page._paint_rules()
        page.run()
        self.app.show_page("选股")
