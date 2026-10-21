"""板块 / 行业 / 拼音首字母。"""
import json
import os

from . import store

# 拼音首字母：只在首次用到时加载 pypinyin，缺失则退化为纯代码匹配
try:
    from pypinyin import Style, lazy_pinyin
except Exception:
    lazy_pinyin = None

_INDUSTRY = None
_INITIAL_CACHE = {}


def load_industry():
    """{code: (行业, 名称)}；打包后从 _MEIPASS 读取。"""
    global _INDUSTRY
    if _INDUSTRY is not None:
        return _INDUSTRY
    path = os.path.join(store.resource_dir(), "core", "industry.json")
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                raw = json.load(fp)
            for code, val in raw.items():
                if isinstance(val, list) and val:
                    data[code] = val[0]
                elif isinstance(val, str):
                    data[code] = val
        except Exception:
            data = {}
    _INDUSTRY = data
    return data


def industry_of(code):
    return load_industry().get(code, "")


def industry_list():
    return sorted({v for v in load_industry().values() if v})


def initials(name):
    """名称 → 拼音首字母，如 贵州茅台 → GZMT。"""
    if not name:
        return ""
    hit = _INITIAL_CACHE.get(name)
    if hit is not None:
        return hit
    if lazy_pinyin is None:
        out = ""
    else:
        try:
            parts = lazy_pinyin(name, style=Style.FIRST_LETTER, errors="ignore")
            out = "".join(p[:1].upper() for p in parts if p)
        except Exception:
            out = ""
    _INITIAL_CACHE[name] = out
    return out


BOARD_ORDER = ["沪市主板", "深市主板", "创业板", "科创板", "北交所"]


def market_label(market, code, board):
    if board == "主板":
        return "沪市主板" if market == 1 else "深市主板"
    return board or "其他"


def all_codes_by_industry(industry):
    return [c for c, v in load_industry().items() if v == industry]
