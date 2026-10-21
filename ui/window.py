"""主窗口：左侧五个工作区、行情数据中枢、全局搜索。"""
import os
import queue
import threading
import time
import tkinter as tk

from core import catalog, formula, store
from core.adjust import adjust_bars, build_events
from core.tdx import TdxFeed, BOARD_BJ, CAT_DAY
from . import theme as T
from .page_market import MarketPage, CATS
from .page_other import AlertsPage, ReviewPage, ScreenerPage, TradePage

NAV = [("行情", "▤"), ("选股", "◎"), ("提醒", "◔"), ("交易", "▣"), ("复盘", "▷")]

BUILTIN = {
    "MACD": "DIF:EMA(CLOSE,12)-EMA(CLOSE,26);\nDEA:EMA(DIF,9);\nMACD:2*(DIF-DEA),COLORSTICK;",
    "KDJ": "RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100;\n"
           "K:SMA(RSV,3,1);\nD:SMA(K,3,1);\nJ:3*K-2*D;",
    "RSI": "LC:=REF(CLOSE,1);\nRSI1:SMA(MAX(CLOSE-LC,0),6,1)/SMA(ABS(CLOSE-LC),6,1)*100;",
    "BOLL": "MID:MA(CLOSE,20);\nUPPER:MID+2*STD(CLOSE,20);\nLOWER:MID-2*STD(CLOSE,20);",
    "均线系统": "MA5:MA(CLOSE,5);\nMA10:MA(CLOSE,10);\nMA20:MA(CLOSE,20);\nMA60:MA(CLOSE,60),COLORGRAY;",
    "量能异动": "V5:MA(VOL,5);\nV10:MA(VOL,10);\n量比:VOL/V5,COLORYELLOW;",
    "趋势强度": "TR1:=ABS(HIGH-LOW);\nHD:=HIGH-REF(HIGH,1);\nLD:=REF(LOW,1)-LOW;\n"
                "DMP:=SUM(IF(HD>0 AND HD>LD,HD,0),14);\nDMM:=SUM(IF(LD>0 AND LD>HD,LD,0),14);\n"
                "PDI:DMP/SUM(TR1,14)*100;\nMDI:DMM/SUM(TR1,14)*100;\nADX:MA(ABS(MDI-PDI)/(MDI+PDI)*100,6);",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("韭菜研究院 · 通达信实盘行情")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1600, sw - 30), min(960, sh - 50)
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 2)))
        self.minsize(1180, 700)
        self.configure(bg=T.BG)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.cfg = store.load_config()
        self.watch_groups = store.load_watch_groups()
        self.builtin = set(BUILTIN)
        self.formulas = dict(BUILTIN)
        self.formulas.update(store.load_user_formulas())

        self.feed = TdxFeed()
        self.quotes = {}
        self.by_code = {}
        self.stocks = []
        self.alerts = []
        self.keyword = ""
        self.trade_date = None
        self.quote_ms = 0
        self.last_update = "--:--:--"
        self.running = True
        self.ready = False
        self.warming = None
        self.spark_done = set()
        self.minute_cache = {}
        self._kl_cache = {}
        self._toast_frame = None

        self.req = queue.Queue()
        self.res = queue.Queue()
        self.spark_q = queue.Queue()
        self.handlers = {"mk:kline": self._h_kline, "mk:minute": self._h_minute,
                         "mk:mini": self._h_mini}

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(120, self._poll)
        threading.Thread(target=self._boot, daemon=True).start()

    # ------------------------------------------------------------ 布局
    def _build(self):
        head = tk.Frame(self, bg=T.PANEL, height=52)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="韭", bg=T.ACCENT, fg="#fff", font=(T.UI_FAMILY, 12, "bold"),
                 width=2).pack(side="left", padx=(10, 8), pady=9)
        tk.Label(head, text="韭菜研究院", bg=T.PANEL, fg=T.TEXT,
                 font=(T.UI_FAMILY, 12, "bold")).pack(side="left")
        tk.Label(head, text="通达信实时行情 · 全市场 5,200+", bg=T.PANEL, fg=T.HINT,
                 font=T.F_UI_SM).pack(side="left", padx=(10, 0))
        self.lbl_conn = tk.Label(head, text="● 连接中…", bg=T.PANEL, fg=T.WARN, font=T.F_UI)
        self.lbl_conn.pack(side="left", padx=16)

        self.var_search = tk.StringVar()
        box = tk.Frame(head, bg=T.PANEL_ALT, highlightbackground=T.LINE, highlightthickness=1)
        box.pack(side="right", padx=12, pady=10)
        tk.Label(box, text="⌕", bg=T.PANEL_ALT, fg=T.HINT).pack(side="left", padx=(6, 2))
        ent = tk.Entry(box, textvariable=self.var_search, bd=0, bg=T.PANEL_ALT, fg=T.TEXT,
                       width=20, insertbackground=T.TEXT, font=T.F_UI)
        ent.pack(side="left", ipady=3)
        ent.bind("<Return>", lambda e: self._search_jump())
        self.var_search.trace_add("write", lambda *a: self._search_changed())
        self.lbl_search = tk.Label(head, text="", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM)
        self.lbl_search.pack(side="right", padx=(0, 4))

        self.lbl_clock = tk.Label(head, text="--:--:--", bg=T.PANEL, fg=T.SUB, font=T.F_NUM)
        self.lbl_clock.pack(side="right", padx=12)
        tk.Frame(self, bg=T.LINE, height=1).pack(fill="x")

        bar = tk.Frame(self, bg=T.PANEL, height=24)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=T.LINE, height=1).pack(fill="x", side="top")
        self.lbl_status = tk.Label(bar, text="正在连接通达信行情服务器…", bg=T.PANEL, fg=T.SUB,
                                   font=T.F_UI_SM)
        self.lbl_status.pack(side="left", padx=10)
        self.lbl_mkt = tk.Label(bar, text="", bg=T.PANEL, fg=T.HINT, font=T.F_UI_SM)
        self.lbl_mkt.pack(side="right", padx=10)

        body = tk.Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True)

        nav = tk.Frame(body, bg="#fbfcfe", width=78)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Frame(nav, bg=T.LINE, width=1).pack(side="right", fill="y")
        self.nav_btns = {}
        for name, glyph in NAV:
            b = tk.Frame(nav, bg="#fbfcfe", cursor="hand2")
            b.pack(fill="x", pady=2, padx=6)
            icon = tk.Label(b, text=glyph, bg="#fbfcfe", fg=T.SUB, font=(T.UI_FAMILY, 14))
            icon.pack(pady=(8, 0))
            label = tk.Label(b, text=name, bg="#fbfcfe", fg=T.SUB, font=T.F_UI_SM)
            label.pack(pady=(1, 8))
            for widget in (b, icon, label):
                widget.bind("<Button-1>", lambda e, n=name: self.show_page(n))
                widget.bind("<Enter>", lambda e, n=name: self._nav_hover(n, True))
                widget.bind("<Leave>", lambda e, n=name: self._nav_hover(n, False))
            self.nav_btns[name] = (b, icon, label)

        self.container = tk.Frame(body, bg=T.BG)
        self.container.pack(side="left", fill="both", expand=True)

        self.pages = {
            "行情": MarketPage(self.container, self),
            "选股": ScreenerPage(self.container, self),
            "提醒": AlertsPage(self.container, self),
            "交易": TradePage(self.container, self),
            "复盘": ReviewPage(self.container, self),
        }
        self.current = "行情"
        self.pages["行情"].pack(fill="both", expand=True)

        self._paint_nav()

    def _nav_hover(self, name, on):
        if name == self.current:
            return
        for widget in self.nav_btns[name]:
            try:
                widget.configure(bg="#f1f5fc" if on else "#fbfcfe")
            except Exception:
                pass

    def _paint_nav(self):
        for name, widgets in self.nav_btns.items():
            on = name == self.current
            bg = T.ACCENT_SOFT if on else "#fbfcfe"
            for i, widget in enumerate(widgets):
                if i == 0:
                    widget.configure(bg=bg)
                else:
                    widget.configure(bg=bg, fg=T.ACCENT if on else T.SUB)

    def show_page(self, name):
        if name not in self.pages or name == self.current:
            return
        self.pages[self.current].pack_forget()
        self.current = name
        self.pages[name].pack(fill="both", expand=True)
        self._paint_nav()
        if name == "行情":
            self.pages["行情"].refresh()

    def open_stock(self, code):
        self.show_page("行情")
        page = self.pages["行情"]
        page.selected = code
        page.table.select(code)
        page.table.jump_to(code)
        page._update_header()
        page._update_star()
        page._reload()

    # ------------------------------------------------------------ 搜索
    def _search_changed(self):
        kw = self.var_search.get().strip()
        self.keyword = kw
        if self.current == "行情":
            page = self.pages["行情"]
            page.refresh()
            self.lbl_search.configure(text=("%d 只命中" % len(page.table.rows)) if kw else "")
        else:
            self.lbl_search.configure(text="")

    def _search_jump(self):
        if not self.var_search.get().strip():
            return
        page = self.pages["行情"]
        page.refresh()
        if page.table.rows:
            self.show_page("行情")
            self.open_stock(page.table.rows[0]["code"])

    # ------------------------------------------------------------ 数据
    def _boot(self):
        try:
            self.feed.connect(self.cfg.get("server"))
            stocks = store.load_stock_cache()
            if not stocks:
                stocks = self.feed.load_stocks()
                store.save_stock_cache(stocks)
            else:
                self.feed.stocks = [tuple(s) for s in stocks]
                self.feed.by_code = {s[1]: tuple(s) for s in stocks}
            self.stocks = self.feed.stocks
            self.by_code = self.feed.by_code
            self._load_bj_seed()
            self._resolve_trade_date()
            self.ready = True
            self.res.put(("sys:ready", None))
            self._start_warm()
        except Exception as exc:
            self.res.put(("sys:fail", str(exc)))
            return
        for fn in (self._quote_loop, self._spark_loop, self._worker_loop):
            threading.Thread(target=fn, daemon=True).start()

    def _start_warm(self):
        from core.tdx import VolumeWarmer
        path = os.path.join(store.app_dir(), "vol5_%s.json" % time.strftime("%Y%m%d"))
        warmer = VolumeWarmer(self.feed, path)
        warmer.load()
        self._warmer = warmer
        self.warming = warmer
        order = [s for s in self.stocks if s[3] != BOARD_BJ]
        warmer.start(order, workers=2)

    def _load_bj_seed(self):
        if any(s[3] == BOARD_BJ for s in self.feed.stocks):
            return
        path = os.path.join(store.resource_dir(), "core", "bj_seed.json")
        if not os.path.exists(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            extra = [(2, c, n, BOARD_BJ) for c, n in data]
            self.feed.stocks.extend(extra)
            for s in extra:
                self.feed.by_code[s[1]] = s
        except Exception:
            pass

    def _resolve_trade_date(self):
        for market, code, _n, _b in self.stocks[:8]:
            rows = self.feed.bars(market, code, CAT_DAY, 3)
            if rows:
                self.trade_date = int(rows[-1]["dt"][:10].replace("-", ""))
                return
        self.trade_date = int(time.strftime("%Y%m%d"))

    def _quote_loop(self):
        while self.running:
            t0 = time.time()
            pairs = [(s[0], s[1]) for s in self.stocks]
            got = {}
            for i in range(0, len(pairs), 80):
                if not self.running:
                    return
                got.update(self.feed.quotes(pairs[i:i + 80]))
            if got:
                self.quotes.update(got)
                self.quote_ms = int((time.time() - t0) * 1000)
                self.last_update = time.strftime("%H:%M:%S")
                self._apply_vr()
                self.res.put(("sys:quotes", None))
            time.sleep(max(1.0, 3.0 - (time.time() - t0)))

    def _apply_vr(self):
        warmer = getattr(self, "_warmer", None)
        if not warmer:
            return
        ratio = self._elapsed_ratio()
        for q in self.quotes.values():
            q.vr = warmer.ratio(q.code, q.vol, ratio)

    @staticmethod
    def _elapsed_ratio():
        now = time.localtime()
        hm = now.tm_hour * 60 + now.tm_min
        if now.tm_wday >= 5:
            return 1.0
        if hm < 570:
            return 0.05
        if hm <= 690:
            return (hm - 570) / 240.0
        if hm < 780:
            return 0.5
        if hm <= 900:
            return (120 + hm - 780) / 240.0
        return 1.0

    def _spark_loop(self):
        while self.running:
            try:
                code = self.spark_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if code in self.spark_done:
                continue
            st = self.feed.by_code.get(code)
            if not st or not self.trade_date:
                continue
            pts = self.feed.minutes(st[0], code, self.trade_date)
            if pts:
                self.spark_done.add(code)
                self.res.put(("sys:spark", (code, pts)))
            time.sleep(0.12)

    def _worker_loop(self):
        while self.running:
            try:
                kind, payload = self.req.get(timeout=0.5)
            except queue.Empty:
                continue
            fn = self.handlers.get(kind)
            if not fn:
                continue
            try:
                self.res.put((kind, fn(payload)))
            except Exception as exc:
                self.res.put(("sys:error", "%s: %s" % (kind, exc)))

    def submit(self, kind, payload):
        self.req.put((kind, payload))

    def _h_kline(self, payload):
        market, code, period, mode = payload
        cat = CATS[period]
        key = (code, cat)
        if key not in self._kl_cache:
            self._kl_cache[key] = self.feed.bars_all(market, code, cat)
        raw = self._kl_cache[key]
        if mode == "none" or not raw:
            return (code, period, raw, mode)
        events = build_events(self.feed.xdxr(market, code))
        return (code, period, adjust_bars(raw, events, mode), mode)

    def _h_minute(self, payload):
        market, code, n = payload
        rows = self.feed.bars(market, code, CAT_DAY, n + 1)
        if not rows:
            return (code, None)
        days, labels, pres = [], [], []
        for i in range(1, len(rows)):
            d = int(rows[i]["dt"][:10].replace("-", ""))
            key = (code, d)
            if key not in self.minute_cache:
                self.minute_cache[key] = self.feed.minutes(market, code, d)
            pts = self.minute_cache[key]
            if not pts:
                continue
            days.append(pts)
            pres.append(rows[i - 1]["c"])
            labels.append("%d-%02d" % (d // 10000, d // 100 % 100))
        if not days:
            return (code, None)
        return (code, {"days": days, "labels": labels, "pres": pres, "bars": rows})

    def _h_mini(self, payload):
        market, code, chart = payload
        bars = self.feed.bars_all(market, code, CAT_DAY)
        return (chart, code, bars[-120:])

    # ------------------------------------------------------------ 轮询
    def _poll(self):
        try:
            for _ in range(60):
                kind, payload = self.res.get_nowait()
                self._dispatch(kind, payload)
        except queue.Empty:
            pass
        if self.warming and self.warming.total and self.warming.done < self.warming.total:
            self.lbl_status.configure(
                text="正在预热历史成交量（量比）… %d/%d" % (self.warming.done, self.warming.total))
        self.after(150, self._poll)

    def _dispatch(self, kind, payload):
        if kind == "sys:ready":
            self._on_ready()
        elif kind == "sys:fail":
            self.lbl_conn.configure(text="● 连接失败", fg=T.UP)
            self.lbl_status.configure(text="行情服务器连接失败：%s　请检查网络后重启" % payload)
        elif kind == "sys:quotes":
            self._on_quotes()
        elif kind == "sys:spark":
            code, pts = payload
            self.pages["行情"].table.set_spark(code, pts)
        elif kind == "sys:error":
            self.lbl_status.configure(text="数据请求失败：%s" % payload)
        elif kind == "mk:mini":
            chart, code, bars = payload
            try:
                chart.set_kline(bars, code, "")
            except Exception:
                pass
        else:
            page = self.pages.get(self.current)
            if page and hasattr(page, "on_data"):
                page.on_data(kind, payload)

    def _on_ready(self):
        self.lbl_conn.configure(text="● 已连接 %s:%s  %dms" % (
            self.feed.server[0], self.feed.server[1], self.feed.latency), fg=T.DOWN)
        self.lbl_status.configure(text="已加载 %d 只 A 股　行情源：通达信 %s:%s" % (
            len(self.stocks), self.feed.server[0], self.feed.server[1]))

    def _on_quotes(self):
        page = self.pages["行情"]
        page.refresh()
        page.update_quotes()
        if not page.selected and page.table.rows:
            self.open_stock(page.table.rows[0]["code"])
        self._check_alerts()
        self._queue_sparks()
        ups = sum(1 for q in self.quotes.values() if q.pct > 0)
        downs = sum(1 for q in self.quotes.values() if q.pct < 0)
        self.lbl_mkt.configure(text="全市场  涨 %d  跌 %d  平 %d   %dms   %s" % (
            ups, downs, len(self.quotes) - ups - downs, self.quote_ms, self.last_update))
        self.lbl_clock.configure(text=time.strftime("%H:%M:%S"))
        if self.current == "交易":
            self.pages["交易"].on_tick()

    def _queue_sparks(self):
        for r in self.pages["行情"].table.rows[:80]:
            if r["code"] not in self.spark_done:
                try:
                    self.spark_q.put_nowait(r["code"])
                except queue.Full:
                    return

    def _check_alerts(self):
        fired = []
        for a in self.alerts:
            q = self.quotes.get(a["code"])
            if not q:
                continue
            prev = a.get("last")
            a["last"] = q.price
            if prev is None or a.get("status") == "已触发":
                continue
            hit = False
            if a["type"] == "价格上穿" and prev < a["target"] <= q.price:
                hit = True
            elif a["type"] == "价格下穿" and prev > a["target"] >= q.price:
                hit = True
            elif a["type"] == "涨幅突破" and q.pct >= a["target"]:
                hit = True
            elif a["type"] == "量比突破" and (q.vr or 0) >= a["target"]:
                hit = True
            if hit:
                a["status"] = "已触发"
                a["time"] = time.strftime("%H:%M:%S")
                fired.append((q, a))
        for q, a in fired:
            self.toast("提醒触发 · %s" % q.name,
                       "%s %s 已达成，现价 %.2f" % (a["type"], a["target"], q.price))
            try:
                self.pages["提醒"].on_tick()
            except Exception:
                pass

    def refresh_formula_boxes(self):
        page = self.pages["行情"]
        subs = ["无"] + sorted(self.formulas.keys())
        for cb in page.sub_boxes:
            cb.configure(values=subs)
        page.cb_main.configure(values=["无"] + sorted(self.formulas.keys()))

    def toast(self, title, desc):
        if self._toast_frame is not None:
            try:
                if self._toast_frame.winfo_exists():
                    self._toast_frame.destroy()
            except Exception:
                pass
        f = tk.Frame(self, bg="#1b2330", padx=14, pady=9)
        tk.Label(f, text=title, bg="#1b2330", fg="#fff", font=T.F_UI_BD, anchor="w").pack(fill="x")
        tk.Label(f, text=desc, bg="#1b2330", fg="#c9d3e3", font=T.F_UI_SM, anchor="w",
                 wraplength=300, justify="left").pack(fill="x")
        f.place(relx=0.985, rely=0.94, anchor="se")
        self._toast_frame = f
        self.after(4200, lambda: f.destroy() if f.winfo_exists() else None)

    def _close(self):
        self.running = False
        try:
            store.save_config(self.cfg)
            store.save_watch_groups(self.watch_groups)
        except Exception:
            pass
        self.destroy()
