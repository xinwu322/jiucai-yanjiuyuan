"""复权处理（前复权 / 后复权 / 不复权）。基于通达信 XDXR 除权除息数据。"""


def _date_of(e):
    return "%04d-%02d-%02d" % (e.get("year") or 0, e.get("month") or 0, e.get("day") or 0)


def build_events(xdxr):
    """从 xdxr 记录中提取除权除息事件及其除权比例。"""
    events = []
    for e in xdxr or []:
        if e.get("category") != 1:
            continue
        fenhong = e.get("fenhong") or 0.0
        song = e.get("songzhuangu") or 0.0
        peigu = e.get("peigu") or 0.0
        peigujia = e.get("peigujia") or 0.0
        if not (fenhong or song or peigu):
            continue
        # 每股口径：每 10 股数据需除以 10
        ratio = (song + peigu) / 10.0
        cash = fenhong / 10.0
        price = peigujia
        # 除权除息比例：r = (前收 - 现金 + 配股价×配股比例) / (前收 × (1+送转配比例))
        # 用当日实际前收更准确，这里先用相对形式，在 adjust_bars 里用当日前收计算
        events.append({"date": _date_of(e), "cash": cash, "ratio": ratio,
                       "peigu": peigu / 10.0, "peigujia": price})
    events.sort(key=lambda x: x["date"])
    return events


def adjust_bars(bars, events, mode="none"):
    """mode: none / qfq（前复权） / hfq（后复权）。返回新的 bar 列表（不修改原数据）。"""
    if mode == "none" or not events or not bars:
        return bars

    # 每个事件用「事件当日的前收盘」计算真实除权比例
    ratios = []
    for ev in events:
        prev_close = None
        for b in bars:
            if b["dt"][:10] >= ev["date"]:
                break
            prev_close = b["c"]
        if not prev_close or prev_close <= 0:
            ratios.append((ev["date"], 1.0))
            continue
        r = (prev_close - ev["cash"] + ev["peigujia"] * ev["peigu"]) / (
            prev_close * (1.0 + ev["ratio"]))
        if not (0.05 < r <= 1.2):
            r = 1.0
        ratios.append((ev["date"], r))

    out = []
    for b in bars:
        d = b["dt"][:10]
        factor = 1.0
        if mode == "hfq":
            for ed, r in ratios:
                if ed <= d:
                    factor /= r
        else:  # qfq
            for ed, r in ratios:
                if ed > d:
                    factor *= r
        out.append({
            "dt": b["dt"],
            "o": b["o"] * factor, "h": b["h"] * factor,
            "l": b["l"] * factor, "c": b["c"] * factor,
            "v": b["v"], "a": b["a"],
        })
    return out
