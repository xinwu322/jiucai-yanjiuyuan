"""通达信行情接入层。

关键点
------
1. 直接复用 pytdx 的协议实现，但**跳过第 3 个握手包**（SetupCmd3）。
   新版行情服务器收到旧的客户端身份包后会切换响应编码，导致 K 线/快照解析成空或乱码；
   去掉该包后 7709 端口的 600519 日线、五档、历史分时都能正常返回（已实测）。
2. 双连接：连接 A 专供全市场快照轮询，连接 B 供 K 线/分时等按需请求，
   避免详情页点开时排在 60 多个快照请求后面。
3. 代码表按板块归类，只保留 A 股：主板 / 创业板 / 科创板 / 北交所。
"""
import re
import socket
import threading
import time
from collections import OrderedDict

import pytdx.parser.setup_commands as _setup

# 关键兼容处理：不发客户端身份包
_setup.SetupCmd3.call_api = lambda self: None

from pytdx.hq import TdxHq_API                      # noqa: E402
from pytdx.config.hosts import hq_hosts             # noqa: E402

CAT_30MIN = 2
CAT_DAY = 9
CAT_QUARTER = 10
CAT_YEAR = 11

BOARD_MAIN = "主板"
BOARD_GEM = "创业板"
BOARD_STAR = "科创板"
BOARD_BJ = "北交所"


class Quote(object):
    __slots__ = ("market", "code", "name", "price", "pre_close", "open", "high",
                 "low", "vol", "amount", "pct", "bid1", "ask1", "time", "board",
                 "vr", "spark")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def change(self):
        if not self.price or not self.pre_close:
            return 0.0
        return self.price - self.pre_close


def board_of(market, code):
    """A 股板块归类；非 A 股返回 None。"""
    if market == 2:
        return BOARD_BJ
    if market == 1:
        if code.startswith("688"):
            return BOARD_STAR
        if code.startswith("60"):
            return BOARD_MAIN
        return None
    if market == 0:
        if code.startswith("30"):
            return BOARD_GEM
        if code.startswith(("00", "001", "002", "003")):
            return BOARD_MAIN
        if code.startswith(("43", "83", "87", "92")):
            return BOARD_BJ
        return None
    return None


class TdxError(Exception):
    pass


class _Conn(object):
    """单条连接，带自动重连。"""

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.api = None
        self.lock = threading.RLock()
        self.last_ok = 0.0
        self.latency = 0

    def connect(self, timeout=5):
        with self.lock:
            if self.api is not None:
                try:
                    self.api.disconnect()
                except Exception:
                    pass
                self.api = None
            api = TdxHq_API(auto_retry=False, heartbeat=False)
            t0 = time.time()
            try:
                ok = api.connect(self.host, self.port, time_out=timeout)
            except Exception as exc:
                raise TdxError("连接 %s:%s 失败：%s" % (self.host, self.port, exc))
            if not ok:
                raise TdxError("连接 %s:%s 失败" % (self.host, self.port))
            self.api = api
            self.latency = int((time.time() - t0) * 1000)
            self.last_ok = time.time()
            return True

    def call(self, fn, *args, **kw):
        with self.lock:
            if self.api is None:
                self.connect()
            try:
                res = fn(self.api, *args, **kw)
            except Exception:
                res = None
            if res is None:
                # 断线重连后重试一次
                try:
                    self.connect()
                    res = fn(self.api, *args, **kw)
                except Exception:
                    res = None
            if res is not None:
                self.last_ok = time.time()
            return res

    def close(self):
        with self.lock:
            if self.api is not None:
                try:
                    self.api.disconnect()
                except Exception:
                    pass
                self.api = None


def probe_servers(limit=24, timeout=1.2):
    """并发测速，返回按延迟升序的 [(name, ip, port, ms)]。"""
    results = []
    lock = threading.Lock()

    def check(item):
        name, ip, port = item
        try:
            s = socket.create_connection((ip, port), timeout=timeout)
            s.close()
            t0 = time.time()
            api = TdxHq_API(auto_retry=False)
            api.connect(ip, port, time_out=timeout)
            api.get_security_count(1)
            ms = int((time.time() - t0) * 1000)
            api.disconnect()
            with lock:
                results.append((name, ip, port, ms))
        except Exception:
            return

    threads = []
    for item in hq_hosts[:limit]:
        t = threading.Thread(target=check, args=(item,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout + 2.5)
    results.sort(key=lambda x: x[3])
    return results


class TdxFeed(object):
    """行情服务门面：代码表、快照、K 线、分时。"""

    def __init__(self, servers=None):
        self.quote_conn = None
        self.data_conn = None
        self.server = servers
        self.stocks = []          # [(market, code, name, board)]
        self.by_code = {}
        self.connected = False
        self.last_error = ""
        self.latency = 0
        self.list_time = 0
        self._xdxr_cache = {}

    # ---------------- 连接 ----------------
    def connect(self, prefer=None):
        candidates = []
        if prefer:
            candidates.append(("手动", prefer[0], prefer[1], 0))
        try:
            candidates += probe_servers()
        except Exception:
            pass
        if not candidates:
            raise TdxError("没有可用的行情服务器（请检查网络或代理）")

        last = None
        for name, ip, port, ms in candidates[:6]:
            try:
                a = _Conn(ip, port)
                a.connect()
                b = _Conn(ip, port)
                b.connect()
                self.quote_conn, self.data_conn = a, b
                self.server = (ip, port)
                self.latency = a.latency
                self.connected = True
                self.last_error = ""
                return True
            except Exception as exc:
                last = exc
                continue
        self.connected = False
        self.last_error = str(last or "连接失败")
        raise TdxError(self.last_error)

    # ---------------- 代码表 ----------------
    def load_stocks(self, force=False):
        stocks = []
        for market in (1, 0, 2):
            count = self.data_conn.call(lambda api, m: api.get_security_count(m), market) or 0
            start = 0
            while start < count:
                page = self.data_conn.call(
                    lambda api, m, s: api.get_security_list(m, s), market, start)
                if not page:
                    # 服务器偶发丢弃连接后的首个请求：同页重试一次再前进
                    page = self.data_conn.call(
                        lambda api, m, s: api.get_security_list(m, s), market, start)
                if not page:
                    start += 1000
                    if start > count + 1000:
                        break
                    continue
                for item in page:
                    code = item.get("code", "")
                    name = (item.get("name") or "").strip()
                    board = board_of(market, code)
                    if board and name:
                        stocks.append((market, code, name, board))
                start += 1000
        # 去重（同代码保留首个）
        seen, uniq = set(), []
        for s in stocks:
            if s[1] in seen:
                continue
            seen.add(s[1])
            uniq.append(s)
        self.stocks = uniq
        self.by_code = {s[1]: s for s in uniq}
        self.list_time = time.time()
        return uniq

    # ---------------- 快照 ----------------
    def quotes(self, pairs):
        """pairs: [(market, code)]，自动按 80 个一批。"""
        out = {}
        for i in range(0, len(pairs), 80):
            chunk = pairs[i:i + 80]
            res = self.quote_conn.call(
                lambda api, c: api.get_security_quotes(c), chunk)
            if not res:
                continue
            for item in res:
                code = item.get("code")
                if not code:
                    continue
                st = self.by_code.get(code)
                pre = item.get("last_close") or 0
                price = item.get("price") or 0
                q = Quote(
                    market=item.get("market"), code=code,
                    name=st[2] if st else code,
                    board=st[3] if st else "",
                    price=price, pre_close=pre,
                    open=item.get("open") or 0, high=item.get("high") or 0,
                    low=item.get("low") or 0,
                    vol=item.get("vol") or 0, amount=item.get("amount") or 0,
                    pct=((price / pre - 1) * 100) if pre else 0.0,
                    bid1=item.get("bid1") or 0, ask1=item.get("ask1") or 0,
                    time=item.get("servertime") or "",
                )
                out[code] = q
        return out

    # ---------------- K 线 ----------------
    def bars(self, market, code, category, count=400):
        res = self.data_conn.call(
            lambda api, c, m, s, n: api.get_security_bars(c, m, s, 0, n),
            category, market, code, count)
        if not res:
            return []
        rows = []
        for b in res:
            dt = b.get("datetime") or ""
            rows.append({
                "dt": dt,
                "o": b.get("open") or 0, "h": b.get("high") or 0,
                "l": b.get("low") or 0, "c": b.get("close") or 0,
                "v": b.get("vol") or 0, "a": b.get("amount") or 0,
            })
        rows.sort(key=lambda x: x["dt"])
        return rows

    def bars_all(self, market, code, category, limit=24000):
        """翻页拉取上市以来全部 K 线（每页 800 根）。"""
        rows, start = [], 0
        while len(rows) < limit:
            part = self.data_conn.call(
                lambda api, c, m, s, st, n: api.get_security_bars(c, m, s, st, n),
                category, market, code, start, 800)
            if not part:
                break
            rows = list(part) + rows
            if len(part) < 800:
                break
            start += 800
        out, seen = [], set()
        for b in rows:
            dt = b.get("datetime") or ""
            if not dt or dt in seen:
                continue
            seen.add(dt)
            out.append({"dt": dt, "o": b.get("open") or 0, "h": b.get("high") or 0,
                        "l": b.get("low") or 0, "c": b.get("close") or 0,
                        "v": b.get("vol") or 0, "a": b.get("amount") or 0})
        out.sort(key=lambda x: x["dt"])
        return out

    def xdxr(self, market, code):
        """除权除息数据，带内存缓存。"""
        key = (market, code)
        if key in self._xdxr_cache:
            return self._xdxr_cache[key]
        res = self.data_conn.call(
            lambda api, m, c: api.get_xdxr_info(m, c), market, code) or []
        self._xdxr_cache[key] = res
        return res

    # ---------------- 分时 ----------------
    def minutes(self, market, code, date_int):
        """历史分时（含当日收盘后），返回 [(price, vol, avg)]，240 点。"""
        res = self.data_conn.call(
            lambda api, m, c, d: api.get_history_minute_time_data(m, c, d),
            market, code, date_int)
        if not res:
            return []
        pts, cum_v, cum_a = [], 0, 0.0
        for item in res:
            p = item.get("price") or 0
            v = item.get("vol") or 0
            if p <= 0:
                continue
            cum_v += v
            cum_a += p * v * 100
            pts.append((p, v, (cum_a / (cum_v * 100)) if cum_v else p))
        return pts

    def today_minutes(self, market, code):
        res = self.data_conn.call(
            lambda api, m, c: api.get_minute_time_data(m, c), market, code)
        if not res:
            return []
        pts = []
        last = 0.0
        for item in res:
            p = item.get("price") or 0
            if p <= 0:
                continue
            last = p
            pts.append((p, item.get("vol") or 0, p))
        return pts


# ---------------------------------------------------------------------------
# 日线成交量预热：用于计算量比（当日累计量 / 过去 5 日平均量）
# ---------------------------------------------------------------------------
class VolumeWarmer(object):
    def __init__(self, feed, cache_path):
        self.feed = feed
        self.cache_path = cache_path
        self.data = {}
        self.running = False
        self.done = 0
        self.total = 0
        self._lock = threading.Lock()

    def load(self):
        import json
        import os
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as fp:
                    self.data = json.load(fp)
            except Exception:
                self.data = {}

    def save(self):
        import json
        import os
        tmp = self.cache_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(self.data, fp)
            os.replace(tmp, self.cache_path)
        except Exception:
            pass

    def start(self, stocks, workers=2):
        if self.running:
            return
        todo = [s for s in stocks if s[1] not in self.data]
        if not todo:
            return
        self.running = True
        self.done = 0
        self.total = len(todo)

        def worker(items):
            for market, code, _name, _board in items:
                rows = self.feed.bars(market, code, CAT_DAY, 7)
                if rows:
                    vols = [r["v"] for r in rows[-6:-1]]
                    if vols:
                        with self._lock:
                            self.data[code] = sum(vols) / float(len(vols))
                with self._lock:
                    self.done += 1

        chunks = [todo[i::workers] for i in range(workers)]
        for part in chunks:
            threading.Thread(target=worker, args=(part,), daemon=True).start()

    def avg(self, code):
        return self.data.get(code)

    def ratio(self, code, vol, elapsed_ratio=1.0):
        """量比：当前累计量 / (5 日均量 × 已开市比例)。"""
        avg = self.data.get(code)
        if not avg or not vol:
            return None
        base = avg * max(0.08, min(1.0, elapsed_ratio))
        return vol / base if base else None
