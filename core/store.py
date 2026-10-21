"""本地配置、自选股、股票列表缓存。"""
import json
import os
import sys
import time

APP_NAME = "JiuYanTerminal"


def app_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    else:
        path = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def resource_dir():
    """打包后资源随 exe 释放到 _MEIPASS；开发态取脚本目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEFAULTS = {
    "server": None,
    "refresh": 3,
    "filter": "全部",
    "sort_key": "pct",
    "sort_desc": True,
    "period": "分时",
}


def _read(name, fallback):
    path = os.path.join(app_dir(), name)
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return fallback


def _write(name, data):
    path = os.path.join(app_dir(), name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULTS)
    cfg.update(_read("config.json", {}))
    return cfg


def save_config(cfg):
    _write("config.json", cfg)


def load_watchlist():
    return list(dict.fromkeys(_read("watchlist.json", [])))


def save_watchlist(codes):
    _write("watchlist.json", codes)


def load_watch_groups():
    """自选股分组：{分组名: [代码...]}，兼容旧的平铺列表。"""
    raw = _read("watch_groups.json", None)
    if isinstance(raw, dict) and raw:
        return {k: list(dict.fromkeys(v)) for k, v in raw.items()}
    flat = load_watchlist()
    return {"默认分组": flat} if flat else {"默认分组": []}


def save_watch_groups(groups):
    _write("watch_groups.json", groups)
    codes = []
    for v in groups.values():
        codes += v
    save_watchlist(list(dict.fromkeys(codes)))


def load_stock_cache(max_age=6 * 3600):
    data = _read("stocks.json", None)
    if not data or "ts" not in data:
        return None
    if time.time() - data["ts"] > max_age:
        return None
    return data["list"]


def save_stock_cache(stocks):
    _write("stocks.json", {"ts": time.time(), "list": stocks})


def user_formula_dir():
    path = os.path.join(app_dir(), "formulas")
    os.makedirs(path, exist_ok=True)
    return path


def load_user_formulas():
    """返回 {名称: 源码}，来自用户目录下的 .txt/.tdx 文件。"""
    out = {}
    for name in sorted(os.listdir(user_formula_dir())):
        if not name.lower().endswith((".txt", ".tdx", ".form")):
            continue
        path = os.path.join(user_formula_dir(), name)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fp:
                out[os.path.splitext(name)[0]] = fp.read()
        except Exception:
            continue
    return out


def save_user_formula(name, source):
    safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "自定义指标"
    path = os.path.join(user_formula_dir(), safe + ".txt")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(source)
    return safe
