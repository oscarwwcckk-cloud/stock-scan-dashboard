# -*- coding: utf-8 -*-
"""市場環境評分(1-100)— 綜合儀表。

合成七項子分數(0-100)加權平均:
  指數趨勢  30% — SPX(權重 50%)/NDX(25%)/DJI(25%) vs MA50/MA200:
                  站上雙均線=100、跌破 MA50(中短期趨勢轉弱)=55、
                  跌破 MA200(長期趨勢轉弱)=40、雙破(無支撐,可能熊市開端)=15
  VIX       15% — <15 極度樂觀(自滿微扣)、<20 平穩偏多、<25 謹慎、≥25 恐慌重扣
  F&G       15% — 極度恐懼重扣、極度貪婪過熱略扣
  市場廣度  15% — Finviz 全市場 % 站上 SMA50/SMA200(抓「指數在線上但個股先跌」背離)
  加權背離  10% — 市值加權(QQQ/SPY)vs 等權(QQQE/RSP)20 日報酬背離:
                  市值加權漲但等權跌=漲勢只來自少數大權值股(頭重腳輕,不健康)
  板塊廣度   7% — 18 板塊中 RS≥70 佔比(漲勢收窄=危險)
  派發日     8% — SPX dist_days(O'Neil:機構出貨頻率)

子分數缺資料(雲端單源被擋)時,權重按比例重分配給其餘可用項,總分不炸。
資料多來自已快取 service(index_health/feargreed/market_breadth/sector_rotation);
加權背離另抓 QQQ/QQQE/SPY/RSP(@st.cache_data ttl=1h)。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.market_service import (
    index_health, market_breadth, breadth_available, feargreed, sector_rotation,
)
from lib.style import GREEN, TEAL, SUB, ORANGE, RED


@st.cache_data(ttl=3600, show_spinner=False)
def _capw_vs_eqw() -> dict | None:
    """市值加權 vs 等權 20 日報酬背離。回 {ndx_diff, spx_diff} 或 None。

    ndx_diff = QQQ 20d% − QQQE(Nasdaq-100 等權)20d%
    spx_diff = SPY 20d% − RSP(S&P 等權)20d%
    正值且大 = 市值加權漲得比等權多 = 漲勢集中於大權值股(不健康)。

    不用 yfinance_fetcher.fetch_closes_batch(它濾掉 <63 根的序列,2mo 不足 63)。
    直接 yf.download 一次抓四檔,只要 ≥21 根即可算 20 日報酬。
    """
    import yfinance as yf
    try:
        d = yf.download(["QQQ", "QQQE", "SPY", "RSP"], period="3mo",
                        interval="1d", auto_adjust=True, progress=False, threads=True)
    except Exception:
        return None
    if d is None or d.empty or "Close" not in d:
        return None
    close = d["Close"] if isinstance(d.columns, pd.MultiIndex) else pd.DataFrame({"_": d["Close"]})

    def _ret20(t):
        if t not in close.columns:
            return None
        s = close[t].dropna()
        if len(s) < 21:
            return None
        r = (float(s.iloc[-1]) / float(s.iloc[-21]) - 1) * 100
        return r if r == r else None  # nan check

    qqq, qqe, spy, rsp = _ret20("QQQ"), _ret20("QQQE"), _ret20("SPY"), _ret20("RSP")
    out = {}
    if qqq is not None and qqe is not None:
        out["ndx_diff"] = round(qqq - qqe, 2)
        out["ndx_capw"] = round(qqq, 2)
        out["ndx_eqw"] = round(qqe, 2)
    if spy is not None and rsp is not None:
        out["spx_diff"] = round(spy - rsp, 2)
        out["spx_capw"] = round(spy, 2)
        out["spx_eqw"] = round(rsp, 2)
    return out or None



# ── 各子分數計算(回 (score 0-100|None, detail 中文說明)) ──────────────────

def _index_sub(health: dict) -> tuple[int | None, str]:
    """指數 vs MA50/200。SPX 50% + NDX/DJI 各 25%(NDX/DJI 常先於 SPX 轉弱)。"""
    weights = {"SPX": 0.5, "NDX": 0.25, "DJI": 0.25}
    total, wsum, notes = 0.0, 0.0, []
    for k, w in weights.items():
        r = (health.get(k) or {}).get("result")
        if not r:
            continue
        p50, p200 = r.pct_from_ma50, r.pct_from_ma200
        # None/nan/0 → False(0 視為貼線=跌破);nan 為 truthy 但 nan>0=False
        above50 = bool(p50 and p50 > 0)
        above200 = bool(p200 and p200 > 0)
        if above50 and above200:
            s = 100
        elif above200:
            s = 55   # 跌破 MA50,守 MA200 → 中短期趨勢轉弱
        elif above50:
            s = 40   # 守 MA50 但跌破 MA200 → 死亡交叉區
        else:
            s = 15   # 雙破 → 無支撐,可能熊市開端
        total += s * w
        wsum += w
        if s < 100:
            notes.append((k, s))
    if wsum == 0:
        return None, "無指數資料"
    if not notes:
        detail = "三指數皆站上 MA50/MA200"
    else:
        detail = "、".join(
            f"{k} 跌破 MA50(中短期轉弱)" if s == 55 else
            f"{k} 跌破 MA200(長期轉弱)" if s == 40 else
            f"{k} 雙均線皆破(無支撐,熊市警戒)"
            for k, s in notes)
    return round(total / wsum), detail


def _vix_sub(vix: float | None) -> tuple[int | None, str]:
    if vix is None:
        return None, "無資料"
    if vix < 15:
        return 85, f"VIX {vix:.1f} 極度樂觀(留意自滿)"
    if vix < 20:
        return 78, f"VIX {vix:.1f} 平穩偏多"
    if vix < 25:
        return 50, f"VIX {vix:.1f} 謹慎"
    if vix < 30:
        return 30, f"VIX {vix:.1f} 恐慌升溫"
    return 15, f"VIX {vix:.1f} 恐慌/避險"


def _fg_sub(fg: dict | None) -> tuple[int | None, str]:
    v = (fg or {}).get("value")
    if v is None:
        return None, "無資料"
    rating = (fg or {}).get("rating") or ""
    if v >= 90:
        s, note = 70, "極度貪婪(過熱)"
    elif v >= 75:
        s, note = 85, "貪婪"
    elif v >= 55:
        s, note = 75, "偏貪婪"
    elif v >= 45:
        s, note = 55, "中性"
    elif v >= 25:
        s, note = 45, "恐懼"
    else:
        s, note = 20, "極度恐懼"
    return s, f"{v} {note}" + (f"({rating})" if rating and rating != "?" else "")


def _breadth_sub(bd: dict | None) -> tuple[int | None, str]:
    """Finviz 全市場 % 站上 SMA50/SMA200 平均。"""
    if not breadth_available(bd or {}):
        return None, "無資料(雲端 egress 可能被擋)"
    p50 = (bd["above_sma50"] or {}).get("pct")
    p200 = (bd["above_sma200"] or {}).get("pct")
    vals = []
    for p in (p50, p200):
        if p is None:
            continue
        vals.append(85 if p >= 60 else 68 if p >= 45 else 48 if p >= 35 else 30 if p >= 25 else 15)
    if not vals:
        return None, "無資料"
    detail = (f"{p50:.0f}% 個股站上 SMA50 · {p200:.0f}% 站上 SMA200"
              if p50 is not None and p200 is not None else "部分無資料")
    return round(sum(vals) / len(vals)), detail


def _capw_sub() -> tuple[int | None, str]:
    """市值加權 vs 等權 20 日報酬背離。

    diff = 市值加權% − 等權%(NDX 用 QQQ/QQQE、SPX 用 SPY/RSP 各算,取平均)。
    diff 越大且為正 = 市值加權遠跑贏等權 = 漲勢集中於少數大權值股(頭重腳輕,不健康);
    diff ≤0(等權跟得上甚至跑贏)= 廣度健康。"""
    d = _capw_vs_eqw()
    if not d:
        return None, "無資料"
    diffs = []
    parts = []
    if "ndx_diff" in d:
        diffs.append(d["ndx_diff"])
        parts.append(f"NDX 加權{d['ndx_capw']:+.1f}% vs 等權{d['ndx_eqw']:+.1f}%")
    if "spx_diff" in d:
        diffs.append(d["spx_diff"])
        parts.append(f"SPX 加權{d['spx_capw']:+.1f}% vs 等權{d['spx_eqw']:+.1f}%")
    if not diffs:
        return None, "無資料"
    avg_diff = sum(diffs) / len(diffs)
    # 正差越大越扣:≤0 健康、0~2 輕微、2~5 頭重腳輕、>5 嚴重集中
    if avg_diff <= 0:
        s = 85
    elif avg_diff < 2:
        s = 70
    elif avg_diff < 5:
        s = 45
    else:
        s = 22
    tag = "(漲勢集中於大權值股)" if avg_diff > 2 else ""
    return s, "、".join(parts) + (f" {tag}" if tag else "")


def _sector_sub() -> tuple[int | None, str]:
    """18 板塊中 RS≥70 佔比。"""
    rows = sector_rotation()
    rated = [r.get("rs_rating") for r in rows if r.get("rs_rating") is not None]
    if not rated:
        return None, "無資料"
    n70 = sum(1 for x in rated if x >= 70)
    pct = n70 / len(rated) * 100
    score = 85 if pct >= 50 else 68 if pct >= 35 else 48 if pct >= 22 else 25
    return score, f"{n70}/{len(rated)} 板塊 RS≥70"


def _dist_sub(health: dict) -> tuple[int | None, str]:
    """SPX 派發日(O'Neil:跌+放量=機構出貨)。"""
    r = (health.get("SPX") or {}).get("result")
    if not r or r.dist_days is None:
        return None, "無資料"
    d = int(r.dist_days)
    score = 85 if d <= 2 else 68 if d <= 4 else 45 if d <= 6 else 25
    note = "(出貨訊號頻繁)" if d >= 5 else ""
    return score, f"SPX 派發日 {d} 日{note}"


# ── 總分合成 ──────────────────────────────────────────────────────────────

_SUB_DEFS = [  # (顯示名, 權重, 計算函式(吃 ctx))
    ("指數趨勢", 0.30, lambda c: _index_sub(c["health"])),
    ("VIX",      0.15, lambda c: _vix_sub(c["vix"])),
    ("Fear & Greed", 0.15, lambda c: _fg_sub(c["fg"])),
    ("市場廣度", 0.15, lambda c: _breadth_sub(c["bd"])),
    ("加權背離", 0.10, lambda c: _capw_sub()),
    ("板塊 RS 廣度", 0.07, lambda c: _sector_sub()),
    ("派發日",   0.08, lambda c: _dist_sub(c["health"])),
]


def _score_color(s: int | None) -> str:
    if s is None:
        return SUB
    if s >= 70:
        return GREEN
    if s >= 45:
        return ORANGE
    return RED


def _label(total: float) -> tuple[str, str]:
    if total >= 75:
        return "多頭環境", GREEN
    if total >= 60:
        return "偏多環境", TEAL
    if total >= 45:
        return "中性震盪", SUB
    if total >= 30:
        return "偏空謹慎", ORANGE
    return "空頭警戒", RED


def compute_market_score() -> dict | None:
    """算市場環境總分 + 子分數。回 None = 全部資料源都掛了。"""
    health = index_health() or {}
    any_vix = next((health.get(k, {}) for k in ("SPX", "NDX", "DJI") if health.get(k)), None)
    ctx = {
        "health": health,
        "vix": (any_vix or {}).get("vix"),
        "fg": feargreed(),
        "bd": market_breadth(),
    }

    subs = []
    used_w, total = 0.0, 0.0
    for name, w, fn in _SUB_DEFS:
        score, detail = fn(ctx)
        if score is not None:
            total += score * w
            used_w += w
        subs.append({"name": name, "weight": w, "score": score, "detail": detail})

    if used_w == 0:
        return None
    final = round(total / used_w)
    label, color = _label(final)

    # 評語:最強項=主要支撐、最弱項=主要風險
    available = [s for s in subs if s["score"] is not None]
    comment = ""
    if len(available) >= 2:
        hi = max(available, key=lambda s: s["score"])
        lo = min(available, key=lambda s: s["score"])
        if hi["score"] != lo["score"]:
            # 支撐項只報名稱+分數(detail 多為負面描述,掛在支撐上讀起來矛盾);
            # 風險項帶 detail 說明拖累原因
            comment = (f"主要支撐:{hi['name']}({hi['score']})　"
                       f"主要風險:{lo['name']}({lo['score']},{lo['detail']})")
    return {
        "total": final,
        "label": label,
        "color": color,
        "subs": subs,
        "comment": comment,
        "sub_color": _score_color,
    }
