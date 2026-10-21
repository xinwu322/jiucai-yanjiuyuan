"""通达信指标公式解析与求值（纯 Python，无第三方依赖）。

支持语法子集：
    VAR:=EXPR;                赋值（不画线）
    VAR:EXPR,COLORRED;        输出（画线），支持颜色/线型修饰
    MA(C,5)  EMA  SMA  REF  HHV  LLV  SUM  STD  CROSS  IF  ABS  MAX  MIN
    COUNT  EVERY  EXIST  BARSLAST  CONST  SQRT  POW  LOG  INTPART  MOD  SIGN
    BETWEEN  UPNDAY  DOWNNDAY  DMA  WMA
运算：+ - * / ( ) > < >= <= = <> AND OR NOT

绘图函数（STICKLINE / DRAWTEXT 等）会被识别并跳过，不参与计算。

源码被设计为「无 numpy」：全市场列表与单只 K 线最多 1000 根，
用纯列表足够快，同时让最终 exe 保持小体积。
"""
import re

__all__ = ["FormulaError", "parse", "evaluate", "DRAW_FUNCS"]


class FormulaError(Exception):
    """公式语法/求值错误，message 面向用户。"""


# --------------------------------------------------------------------------
# 词法
# --------------------------------------------------------------------------
TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<ident>[A-Za-z_\u4e00-\u9fa5][A-Za-z0-9_\u4e00-\u9fa5]*)"
    r"|(?P<op>:=|<>|>=|<=|[-+*/(),;:><=])"
    r"|(?P<other>\S)"
    r")"
)

DRAW_FUNCS = {
    "STICKLINE", "DRAWTEXT", "DRAWICON", "DRAWNUMBER", "DRAWLINE", "DRAWBAND",
    "DRAWKLINE", "POLYLINE", "PLOYLINE", "VERTLINE", "NOTEXT", "PARTLINE",
    "DRAWTEXT_FIX", "DRAWNUMBER_FIX", "DRAWLINE_FIX", "SIGNALS", "TEXT",
}

COLOR_WORDS = {
    "COLORRED", "COLORGREEN", "COLORBLUE", "COLORWHITE", "COLORYELLOW",
    "COLORMAGENTA", "COLORCYAN", "COLORBLACK", "COLORGRAY", "COLORLIGRAY",
    "COLORLIRED", "COLORLIGREEN", "COLORLIBLUE", "COLORLIGRAY", "COLORBROWN",
    "COLORSTICK", "VOLSTICK", "LINESTICK", "LINETHICK", "LINETHICK1",
    "LINETHICK2", "LINETHICK3", "LINETHICK4", "LINETHICK5", "LINETHICK6",
    "LINETHICK7", "LINETHICK8", "LINETHICK9", "POINTDOT", "CROSSDOT",
    "CIRCLEDOT", "DOTLINE", "NODRAW", "COLORRGB", "COLOR999999",
}


def _tokenize(src):
    src = re.sub(r"\{[^}]*\}", " ", src)          # 通达信注释 { ... }
    src = re.sub(r"//[^\n]*", " ", src)           # 行注释
    tokens, pos = [], 0
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            break
        pos = m.end()
        if m.group("num") is not None:
            tokens.append(("num", m.group("num")))
        elif m.group("ident") is not None:
            tokens.append(("ident", m.group("ident").upper()))
        elif m.group("op") is not None:
            tokens.append(("op", m.group("op")))
        elif m.group("other") is not None:
            ch = m.group("other")
            if ch in "%":
                tokens.append(("op", "/"))
                tokens.append(("num", "100"))
            else:
                raise FormulaError("无法识别的字符：%s" % ch)
    tokens.append(("eof", ""))
    return tokens


# --------------------------------------------------------------------------
# 语法：递归下降
# --------------------------------------------------------------------------
class _Parser:
    def __init__(self, tokens, src):
        self.t = tokens
        self.i = 0
        self.src = src

    def peek(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def accept(self, value):
        kind, val = self.peek()
        if val == value:
            self.i += 1
            return True
        return False

    def expect(self, value):
        kind, val = self.peek()
        if val != value:
            raise FormulaError("第 %d 个记号处缺少 “%s”" % (self.i + 1, value))
        self.i += 1
        return val

    # --- 表达式层级 ---
    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.peek()[1] == "OR":
            self.next()
            node = ("bin", "OR", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.peek()[1] == "AND":
            self.next()
            node = ("bin", "AND", node, self.parse_cmp())
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.peek()[1] in ("=", "<>", ">", "<", ">=", "<="):
            op = self.next()[1]
            node = ("bin", op, node, self.parse_add())
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            node = ("bin", op, node, self.parse_mul())
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek()[1] in ("*", "/"):
            op = self.next()[1]
            node = ("bin", op, node, self.parse_unary())
        return node

    def parse_unary(self):
        kind, val = self.peek()
        if val == "-":
            self.next()
            return ("un", "-", self.parse_unary())
        if val == "+":
            self.next()
            return self.parse_unary()
        if val == "NOT":
            self.next()
            return ("un", "NOT", self.parse_unary())
        return self.parse_atom()

    def parse_atom(self):
        kind, val = self.next()
        if kind == "num":
            return ("num", float(val))
        if val == "(":
            node = self.parse_expr()
            self.expect(")")
            return node
        if kind == "ident":
            if self.peek()[1] == "(":
                self.next()
                args = []
                if self.peek()[1] != ")":
                    args.append(self.parse_expr())
                    while self.accept(","):
                        args.append(self.parse_expr())
                self.expect(")")
                return ("call", val, args)
            return ("var", val)
        raise FormulaError("表达式不完整，意外的记号 “%s”" % val)

    # --- 语句 ---
    def parse_program(self):
        stmts = []
        while self.peek()[0] != "eof":
            while self.accept(";"):
                pass
            if self.peek()[0] == "eof":
                break
            kind, val = self.peek()
            if kind != "ident":
                raise FormulaError("语句必须以变量名开头，遇到 “%s”" % val)
            # 纯绘图函数语句：跳过
            if self.peek(1)[1] == "(" and val in DRAW_FUNCS:
                self._skip_statement()
                continue
            name = self.next()[1]
            if self.accept(":="):
                expr = self.parse_expr()
                self._skip_modifiers()
                stmts.append(("assign", name, expr, []))
            elif self.accept(":"):
                expr = self.parse_expr()
                mods = self._skip_modifiers()
                stmts.append(("output", name, expr, mods))
            else:
                raise FormulaError("变量 %s 之后应为 := 或 :" % name)
            self.accept(";")
        if not stmts:
            raise FormulaError("公式为空")
        return stmts

    def _skip_modifiers(self):
        mods = []
        while True:
            kind, val = self.peek()
            if kind == "eof" or val in (";",):
                break
            if kind == "ident" and (val in COLOR_WORDS or val.startswith("COLOR")):
                mods.append(self.next()[1])
                self.accept(",")
                continue
            if val == ",":
                self.next()
                continue
            break
        return mods

    def _skip_statement(self):
        depth = 0
        while self.peek()[0] != "eof":
            _, val = self.next()
            if val == "(":
                depth += 1
            elif val == ")":
                depth -= 1
            elif val == ";" and depth <= 0:
                return


def parse(src):
    """把公式源码解析为语句列表。"""
    parser = _Parser(_tokenize(src), src)
    return parser.parse_program()


# --------------------------------------------------------------------------
# 求值
# --------------------------------------------------------------------------
def _is_num(v):
    return v is not None


def _win(seq, i, n):
    """返回 seq[i-n+1 .. i]，不足或含 None 时返回 None。"""
    if i < n - 1:
        return None
    chunk = seq[i - n + 1:i + 1]
    if any(v is None for v in chunk):
        return None
    return chunk


def _rolling(seq, n, fn):
    out = []
    for i in range(len(seq)):
        chunk = _win(seq, i, n)
        out.append(None if chunk is None else fn(chunk))
    return out


def _ema(seq, n):
    out, prev = [], None
    k = 2.0 / (n + 1)
    for v in seq:
        if v is None:
            out.append(prev)
            continue
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def _sma(seq, n, m):
    out, prev = [], None
    for v in seq:
        if v is None:
            out.append(prev)
            continue
        prev = v if prev is None else (m * v + (n - m) * prev) / n
        out.append(prev)
    return out


def _to_bool(v):
    return 1.0 if (v not in (None, 0)) else 0.0


def _shift(seq, n):
    if n <= 0:
        return list(seq)
    return [None] * n + list(seq[:len(seq) - n])


def _arg_num(node, ctx_len, name):
    if node[0] != "num":
        raise FormulaError("%s 的第 %d 个参数必须是常数" % (name, 1))
    return int(node[1])


class _Evaluator:
    def __init__(self, ctx, n):
        self.ctx = ctx
        self.n = n
        self.vars = dict(ctx)

    def eval(self, node):
        kind = node[0]
        if kind == "num":
            return [node[1]] * self.n
        if kind == "var":
            name = node[1]
            if name not in self.vars:
                raise FormulaError("未定义的变量：%s" % name)
            return self.vars[name]
        if kind == "un":
            v = self.eval(node[2])
            if node[1] == "-":
                return [None if x is None else -x for x in v]
            return [None if x is None else (0.0 if x else 1.0) for x in v]
        if kind == "bin":
            return self._bin(node[1], self.eval(node[2]), self.eval(node[3]))
        if kind == "call":
            return self._call(node[1], node[2])
        raise FormulaError("未知表达式")

    def _bin(self, op, a, b):
        out = []
        for x, y in zip(a, b):
            if x is None or y is None:
                out.append(None)
                continue
            if op == "+":
                out.append(x + y)
            elif op == "-":
                out.append(x - y)
            elif op == "*":
                out.append(x * y)
            elif op == "/":
                out.append(None if y == 0 else x / y)
            elif op == ">":
                out.append(1.0 if x > y else 0.0)
            elif op == "<":
                out.append(1.0 if x < y else 0.0)
            elif op == ">=":
                out.append(1.0 if x >= y else 0.0)
            elif op == "<=":
                out.append(1.0 if x <= y else 0.0)
            elif op == "=":
                out.append(1.0 if abs(x - y) < 1e-9 else 0.0)
            elif op == "<>":
                out.append(1.0 if abs(x - y) >= 1e-9 else 0.0)
            elif op == "AND":
                out.append(1.0 if (x != 0 and y != 0) else 0.0)
            elif op == "OR":
                out.append(1.0 if (x != 0 or y != 0) else 0.0)
            else:
                raise FormulaError("不支持的运算符：%s" % op)
        return out

    def _call(self, name, args):
        n = self.n
        if name in ("MA",):
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(v, p, lambda c: sum(c) / len(c))
        if name == "EMA":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _ema(v, p)
        if name == "SMA":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            m = self.eval(args[2])[0] if len(args) > 2 else 1
            return _sma(v, p, m)
        if name == "DMA":
            a = self.eval(args[0]); b = self.eval(args[1])
            out, prev = [], None
            for x, y in zip(a, b):
                if x is None:
                    out.append(prev)
                    continue
                prev = x if prev is None else prev + (x - prev) * (y if y is not None else 0)
                out.append(prev)
            return out
        if name == "WMA":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            def w(c):
                s = sum((i + 1) * x for i, x in enumerate(c))
                return s / (len(c) * (len(c) + 1) / 2)
            return _rolling(v, p, w)
        if name == "REF":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _shift(v, p)
        if name == "HHV":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(v, p, max)
        if name == "LLV":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(v, p, min)
        if name == "SUM":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(v, p, sum)
        if name == "STD":
            v = self.eval(args[0]); p = _arg_num(args[1], n, name)
            def std(c):
                m = sum(c) / len(c)
                return (sum((x - m) ** 2 for x in c) / len(c)) ** 0.5
            return _rolling(v, p, std)
        if name == "CROSS":
            a = self.eval(args[0]); b = self.eval(args[1])
            out = []
            for i in range(n):
                if i == 0 or None in (a[i], b[i], a[i - 1], b[i - 1]):
                    out.append(0.0 if i else None)
                else:
                    out.append(1.0 if (a[i] > b[i] and a[i - 1] <= b[i - 1]) else 0.0)
            return out
        if name == "IF":
            c = self.eval(args[0]); a = self.eval(args[1]); b = self.eval(args[2])
            return [None if ci is None else (ai if ci else bi) for ci, ai, bi in zip(c, a, b)]
        if name == "ABS":
            return [None if x is None else abs(x) for x in self.eval(args[0])]
        if name == "MAX":
            a, b = self.eval(args[0]), self.eval(args[1])
            return [None if x is None or y is None else max(x, y) for x, y in zip(a, b)]
        if name == "MIN":
            a, b = self.eval(args[0]), self.eval(args[1])
            return [None if x is None or y is None else min(x, y) for x, y in zip(a, b)]
        if name == "SQRT":
            return [None if x is None or x < 0 else x ** 0.5 for x in self.eval(args[0])]
        if name == "POW":
            a, b = self.eval(args[0]), self.eval(args[1])
            return [None if x is None or y is None else x ** y for x, y in zip(a, b)]
        if name == "LOG":
            import math
            return [None if x is None or x <= 0 else math.log(x) for x in self.eval(args[0])]
        if name == "INTPART":
            return [None if x is None else float(int(x)) for x in self.eval(args[0])]
        if name == "MOD":
            a, b = self.eval(args[0]), self.eval(args[1])
            return [None if x is None or y in (None, 0) else x % y for x, y in zip(a, b)]
        if name == "SIGN":
            return [None if x is None else (1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
                    for x in self.eval(args[0])]
        if name == "CONST":
            v = self.eval(args[0])
            val = v[0] if v else 0.0
            return [val] * n
        if name == "COUNT":
            c = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(c, p, lambda ch: float(sum(1 for x in ch if x)))
        if name == "EVERY":
            c = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(c, p, lambda ch: 1.0 if all(x for x in ch) else 0.0)
        if name == "EXIST":
            c = self.eval(args[0]); p = _arg_num(args[1], n, name)
            return _rolling(c, p, lambda ch: 1.0 if any(x for x in ch) else 0.0)
        if name == "BARSLAST":
            c = self.eval(args[0])
            out, last = [], None
            for i, x in enumerate(c):
                if x:
                    last = i
                out.append(None if last is None else float(i - last))
            return out
        if name == "BETWEEN":
            x = self.eval(args[0]); a = self.eval(args[1]); b = self.eval(args[2])
            return [None if None in (xi, ai, bi) else (1.0 if ai <= xi <= bi else 0.0)
                    for xi, ai, bi in zip(x, a, b)]
        if name in ("UPNDAY", "DOWNNDAY"):
            c = self.eval(args[0]); p = _arg_num(args[1], n, name)
            out = []
            for i in range(n):
                if i < p:
                    out.append(None)
                    continue
                ok = True
                for k in range(p):
                    if c[i - k] is None or c[i - k - 1] is None:
                        ok = False
                        break
                    if name == "UPNDAY" and not c[i - k] > c[i - k - 1]:
                        ok = False
                        break
                    if name == "DOWNNDAY" and not c[i - k] < c[i - k - 1]:
                        ok = False
                        break
                out.append(1.0 if ok else 0.0)
            return out
        raise FormulaError("暂不支持的函数：%s" % name)

    def run(self, stmts):
        outputs = []
        for kind, name, expr, mods in stmts:
            values = self.eval(expr)
            self.vars[name] = values
            if kind == "output":
                outputs.append({
                    "name": name,
                    "values": values,
                    "mods": mods,
                    "style": "bar" if any(m in ("COLORSTICK", "VOLSTICK", "LINESTICK") for m in mods)
                             else "line",
                    "color": _mod_color(mods),
                    "hidden": "NODRAW" in mods,
                })
        return outputs


_COLOR_MAP = {
    "COLORRED": "#e0322a", "COLORGREEN": "#12a05c", "COLORBLUE": "#2f6fd0",
    "COLORWHITE": "#ffffff", "COLORYELLOW": "#e8a33d", "COLORMAGENTA": "#c04fd6",
    "COLORCYAN": "#12a3b8", "COLORGRAY": "#8b95a5", "COLORLIGRAY": "#b7c0cd",
    "COLORLIRED": "#f2777a", "COLORLIGREEN": "#4fc08d", "COLORLIBLUE": "#7aa7e8",
    "COLORBROWN": "#a1711b",
}

_PALETTE = ["#e8a33d", "#2f6fd0", "#c04fd6", "#12a3b8", "#e0322a", "#5b8c2a"]


def _mod_color(mods):
    for m in mods:
        if m in _COLOR_MAP:
            return _COLOR_MAP[m]
    return None


_ALIAS = {"O": "OPEN", "H": "HIGH", "L": "LOW", "C": "CLOSE", "V": "VOL", "A": "AMOUNT"}


def evaluate(src, ctx, n):
    """解析并计算。ctx 需含 O/H/L/C/V/A 六个等长序列，别名自动补全。"""
    ctx = dict(ctx)
    for short, long_name in _ALIAS.items():
        if short in ctx and long_name not in ctx:
            ctx[long_name] = ctx[short]
        elif long_name in ctx and short not in ctx:
            ctx[short] = ctx[long_name]
    stmts = parse(src)
    ev = _Evaluator(ctx, n)
    outs = ev.run(stmts)
    for i, o in enumerate(outs):
        if o["color"] is None:
            o["color"] = _PALETTE[i % len(_PALETTE)]
    return outs
