"""配色与字体。浅色专业盘面，A 股习惯：涨红跌绿。"""
import sys

BG = "#f2f4f8"
PANEL = "#ffffff"
PANEL_ALT = "#fafbfd"
LINE = "#e3e8f0"
LINE_SOFT = "#eef1f6"
TEXT = "#1b2330"
SUB = "#6b7789"
HINT = "#9aa5b6"
UP = "#e0322a"
DOWN = "#12a05c"
FLAT = "#8b95a5"
ACCENT = "#2563eb"
ACCENT_SOFT = "#e8efff"
HOVER = "#f3f7ff"
SEL = "#e6eeff"
WARN = "#d97706"
GRID = "#eef1f6"
CROSS = "#8d99ac"

_IS_WIN = sys.platform.startswith("win")
_IS_MAC = sys.platform == "darwin"

if _IS_WIN:
    UI_FAMILY = "Microsoft YaHei UI"
elif _IS_MAC:
    UI_FAMILY = "PingFang SC"
else:
    UI_FAMILY = "Noto Sans CJK SC"

NUM_FAMILY = "Consolas" if _IS_WIN else ("Menlo" if _IS_MAC else "DejaVu Sans Mono")

F_UI = (UI_FAMILY, 9)
F_UI_SM = (UI_FAMILY, 8)
F_UI_BD = (UI_FAMILY, 9, "bold")
F_TITLE = (UI_FAMILY, 12, "bold")
F_BIG = (NUM_FAMILY, 20, "bold")
F_BIG_SM = (NUM_FAMILY, 13)
F_NUM = (NUM_FAMILY, 10)
F_NUM_SM = (NUM_FAMILY, 9)
F_NUM_BD = (NUM_FAMILY, 10, "bold")
F_TAB = (UI_FAMILY, 9)


def color_of(value):
    if value is None:
        return FLAT
    if value > 0:
        return UP
    if value < 0:
        return DOWN
    return FLAT
