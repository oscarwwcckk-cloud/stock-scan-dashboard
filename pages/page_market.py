# -*- coding: utf-8 -*-
"""Market Situation 頁 — 指數健康度 + 產業輪動 + 市場廣度。

三區全部 fetcher @st.cache_data(ttl=3600)(移植自舊 stock-dashboard backend 純 Python 邏輯),
任一區抓失敗優雅降級(warning)不崩潰 —— 雲端對 Finviz egress 可能被擋。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.style import (
    apply_dark_theme, kpi_card, refresh_button, BG, CARD, GRID, TXT, SUB,
    ORANGE, BLUE, GREEN, RED, TEAL, _chart_cfg, line_hover,
)
from lib.market_service import (
    index_health, market_breadth, breadth_available, feargreed,
)
from lib.market_score import compute_market_score

# trend_state → 顏色
TREND_COLOR = {
    "Confirmed Uptrend": GREEN,
    "Uptrend Under Pressure": ORANGE,
    "Recovery Attempt": ORANGE,
    "Market in Correction": RED,
    "Bear Market": RED,
    "Insufficient Data": GRID,
}
# trend_state → 繁體中文顯示
TREND_ZH = {
    "Confirmed Uptrend": "確認上升趨勢",
    "Uptrend Under Pressure": "上升趨勢承壓",
    "Recovery Attempt": "嘗試復甦",
    "Market in Correction": "市場修正中",
    "Bear Market": "熊市",
    "Insufficient Data": "資料不足",
}
# market_signal(英文句子)→ 繁體中文
SIGNAL_ZH = {
    "Not enough history to classify trend": "歷史資料不足以判定趨勢",
    "Price above MA50 > MA200. Healthy bull market — follow the trend.": "站上 MA50 且 MA50 > MA200,多頭結構健康 — 順勢而為。",
    "Price pulled below MA50 but remains above MA200. Wait for base to form.": "跌破 MA50 但仍守在 MA200 之上,等待底部形成。",
    "Price above MA50 but MA50 < MA200 (death cross zone). Needs follow-through day.": "站回 MA50 之上,但 MA50 仍低於 MA200(死亡交叉區),需等待確認日。",
    "Significant pullback. Price below both MAs. Watch MA200 as support.": "明顯回檔,價格跌破兩條均線,觀察 MA200 支撐。",
    "Price and MA50 both below MA200. Capital preservation mode.": "價格與 MA50 都在 MA200 之下,進入資金保全模式。",
}


def _fmt_pct(v, suffix="%"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:+.2f}{suffix}" if suffix == "%" else f"{v:.2f}"


def _index_chart(ohlc, title=""):
    """TradingView 風格蠟燭圖:K 線(紅漲綠跌)+ 成交量 + MA50/MA200。
    ohlc: DataFrame(open/high/low/close/volume)。取近 ~126 根(6 個月)。"""
    if ohlc is None or "close" not in ohlc or len(ohlc) < 2:
        return
    df = ohlc.iloc[-126:].copy() if len(ohlc) > 126 else ohlc.copy()
    # 補齊 OHLCV 欄(防缺欄)
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df:
            df[col] = df["close"] if col != "volume" else 0
    up = df["close"] >= df["open"]                      # 漲
    # TradingView 預設:綠漲紅跌
    UP_C, DN_C = GREEN, RED

    ma50 = df["close"].rolling(50, min_periods=1).mean()

    def _rgba(hexc, alpha):
        return f"rgba({int(hexc[1:3],16)},{int(hexc[3:5],16)},{int(hexc[5:7],16)},{alpha})"

    fig = go.Figure()
    # 成交量(放次軸,半透明,顏色隨漲跌:漲綠跌紅)
    vol_max = float(df["volume"].max()) if df["volume"].max() > 0 else 1
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"], name="Vol",
        marker_color=[_rgba(UP_C, 0.35) if u else _rgba(DN_C, 0.35) for u in up],
        yaxis="y2", hovertemplate="Vol: %{y}<extra></extra>", showlegend=False))
    # K 線(TradingView 預設:綠漲紅跌)
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="Price",
        increasing_line_color=UP_C, decreasing_line_color=DN_C,
        increasing_fillcolor=UP_C, decreasing_fillcolor=DN_C,
        whiskerwidth=0.4, line=dict(width=0.5)))
    # MA50
    fig.add_trace(go.Scatter(x=df.index, y=ma50, name="MA50",
                            line=dict(color=ORANGE, width=1.3), mode="lines"))

    fig.update_layout(
        height=300, margin=dict(l=8, r=8, t=24, b=8),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TXT, size=10),
        showlegend=True, legend=dict(orientation="h", y=1.1, x=0, font=dict(size=9)),
        xaxis=dict(rangeslider=dict(visible=False), showgrid=False, color=GRID,
                   rangebreaks=[dict(bounds=["sat","mon"], pattern="day of week")]),
        yaxis=dict(domain=[0.22, 1], showgrid=True, gridcolor=GRID, color=GRID,
                   side="right"),
        yaxis2=dict(domain=[0, 0.18], showgrid=False, color=GRID, side="right",
                    range=[0, vol_max * 1.15]),
        title=dict(text=title, font=dict(size=11, color=SUB)) if title else None,
    )
    fig.update_traces(selector=dict(type="candlestick"), hoverlabel=dict(bgcolor=CARD))
    line_hover(fig)
    st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))


def _render_env_score():
    """市場環境分析 — 總分卡(1-100 + 評語)+ 六項子分數清單。

    總分由 index_health/feargreed/market_breadth/sector_rotation 合成(全快取),
    單源失敗權重按比例重分配。子分數卡:名稱+分數(色)+權重+細節說明。"""
    st.subheader("🎯 市場環境分析")
    r = compute_market_score()
    if r is None:
        st.warning("市場環境評分資料不足(所有資料源抓取失敗)。稍後再試。")
        return

    sub_color = r["sub_color"]
    # 左:總分大卡;右:子分數清單
    tc, rc = st.columns([1, 2.2])
    with tc:
        st.markdown(
            f'<div class="kpi" style="text-align:center;min-height:180px;'
            f'display:flex;flex-direction:column;justify-content:center">'
            f'<div class="lbl" style="font-size:15px;font-weight:700">市場環境評分</div>'
            f'<div class="val" style="color:{r["color"]};font-size:54px;'
            f'font-weight:800;line-height:1.1">{r["total"]}</div>'
            f'<div class="sub" style="color:{r["color"]};font-size:18px;'
            f'font-weight:700">{r["label"]}</div>'
            f'<div class="sub" style="color:{SUB};font-size:11px">滿分 100 · 六項加權</div>'
            f'</div>', unsafe_allow_html=True)
    with rc:
        for s in r["subs"]:
            sc = s["score"]
            sc_txt = str(sc) if sc is not None else "—"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'padding:5px 0;border-bottom:1px solid {GRID}">'
                f'<div style="flex:0 0 110px;color:{TXT};font-weight:600;font-size:13px">'
                f'{s["name"]}</div>'
                f'<div style="flex:0 0 46px;text-align:center;color:{sub_color(sc)};'
                f'font-size:18px;font-weight:800">{sc_txt}</div>'
                f'<div style="flex:1;color:{SUB};font-size:11.5px">'
                f'{s["detail"]}　<span style="opacity:.6">(權重 {s["weight"]:.0%})</span></div>'
                f'</div>', unsafe_allow_html=True)
    if r["comment"]:
        st.caption(f"💡 {r['comment']}")


def _render_index_cards(health):
    st.subheader("📈 大盤指數健康度")
    keys = ["SPX", "NDX", "DJI"]
    cols = st.columns(len(keys))
    for c, key in zip(cols, keys):
        with c:
            d = health.get(key)
            if not d or d.get("result") is None:
                st.warning(f"{key} 資料抓取失敗")
                continue
            r = d["result"]
            vix = d.get("vix")
            color = TREND_COLOR.get(r.trend_state, GRID)
            chg = r.change_pct
            chg_color = GREEN if chg >= 0 else RED
            st.markdown(
                f'<div class="kpi"><div class="lbl">{key}</div>'
                f'<div class="val" style="color:{TXT}">{r.price:.2f}</div>'
                f'<div class="sub" style="color:{chg_color}">{_fmt_pct(chg)}</div>'
                f'<div class="sub" style="color:{color};font-weight:600">{TREND_ZH.get(r.trend_state, r.trend_state)}</div>'
                f'</div>', unsafe_allow_html=True)
            st.caption(
                f"MA50 {r.ma50:.1f}({_fmt_pct(r.pct_from_ma50)}) · "
                f"MA200 {r.ma200:.1f}({_fmt_pct(r.pct_from_ma200)})\n\n"
                f"RSI14 {r.rsi14:.1f} · 派發日 {r.dist_days} 天\n\n"
                f"52週區間 {r.low_52w:.1f}–{r.high_52w:.1f} "
                f"(距高點 {_fmt_pct(r.pct_from_52w_high)})"
            )
            _index_chart(d.get("ohlc"), key)
            st.markdown("")  # 卡間距


def vcolor(vix):
    return GREEN if vix < 20 else (ORANGE if vix < 25 else RED)


def vix_label(vix):
    if vix < 15:
        return "極度樂觀(可能自滿)"
    if vix < 20:
        return "平穩偏多"
    if vix < 25:
        return "謹慎"
    return "恐慌/避險升溫"


# Fear & Greed rating(英文)→ 繁體中文
FG_RATING_ZH = {
    "Extreme Fear": "極度恐懼",
    "Fear": "恐懼",
    "Neutral": "中性",
    "Greed": "貪婪",
    "Extreme Greed": "極度貪婪",
    "?": "—",
}


def _fg_color(value):
    """F&G 值 0-100 → 色(0 恐懼紅,50 中性,100 貪婪綠)。"""
    if value is None:
        return GRID
    if value < 25:
        return RED
    if value < 45:
        return ORANGE
    if value <= 55:
        return SUB
    if value < 75:
        return TEAL
    return GREEN


def _render_sentiment(health):
    """情緒面板:VIX + Fear & Greed 一行,Finviz 四項廣度一行。

    health = index_health() 結果(取 VIX)。F&G 走 feargreed() 即時抓
    (CNN dataviz API 優先、本機 playwright fallback)。
    Finviz 廣度走 market_breadth()(雲端 egress 被擋時四項全 None → 該行降級顯示)。"""
    st.subheader("🌡️ 市場情緒")
    # 情緒面板內:卡片標題(.lbl)放大粗體 + 副標(.sub)放大粗體
    # (不動其他頁面 .lbl/.sub 預設,只此面板 inline 蓋掉)
    LBL_LG = "font-size:15px;font-weight:700"
    SUB_LG = "font-size:14px;font-weight:600"
    # 情緒面板內卡片間距(左右讓卡之間留縫、下邊與下行拉開)
    CARD_GAP = "margin:0 6px 16px 6px"
    keys = ["SPX", "NDX", "DJI"]
    any_vix = next((health.get(k, {}) for k in keys if health.get(k)), None)
    vix = (any_vix or {}).get("vix") if any_vix else None

    # ── Fear & Greed(即時抓 CNN API;🔄 清快取後必是新鮮值)──
    fg = feargreed()

    # ── 第一行:VIX + Fear & Greed ──
    c1, c2 = st.columns(2)
    with c1:
        if vix is not None:
            st.markdown(
                f'<div class="kpi" style="{CARD_GAP}"><div class="lbl" style="{LBL_LG}">VIX 情緒</div>'
                f'<div class="val" style="color:{vcolor(vix)}">{vix:.1f}</div>'
                f'<div class="sub" style="{SUB_LG}">{vix_label(vix)}</div></div>',
                unsafe_allow_html=True)
        else:
            st.metric("VIX 情緒", "—")
    with c2:
        if fg and fg.get("value") is not None:
            val = fg["value"]
            rating = FG_RATING_ZH.get(fg.get("rating", "?"), fg.get("rating", "?"))
            st.markdown(
                f'<div class="kpi" style="{CARD_GAP}"><div class="lbl" style="{LBL_LG}">Fear & Greed Index</div>'
                f'<div class="val" style="color:{_fg_color(val)}">{val}</div>'
                f'<div class="sub" style="{SUB_LG}">{rating}</div></div>',
                unsafe_allow_html=True)
        else:
            st.metric("CNN Fear & Greed", "—")
            st.caption("F&G 即時抓取失敗(CNN API 與本機 playwright 都不可用)")

    # ── 第二行:Finviz 四項廣度(Adv/Dec · NH/NL · Above SMA50 · Above SMA200)──
    bd = market_breadth()
    if not breadth_available(bd):
        st.info("Finviz 廣度無法取得(雲端 egress 可能被擋;本機可正常顯示)。")
        return
    cols = st.columns(4)

    def _rgba(hexc, a):
        return f"rgba({int(hexc[1:3],16)},{int(hexc[3:5],16)},{int(hexc[5:7],16)},{a})"

    def _pair(col, title, hi, lo, good_when_high=True):
        """一張卡:大 % = 兩邊較大者(色隨多空:站上/漲/新高方較大=綠,對立方較大=紅)
        + 綠紅比例對比條(綠=站上/漲/新高、紅=對立)+ 兩端 % + 件數。"""
        with col:
            hp, hc = hi["pct"], hi["count"]
            lp, lc = lo["pct"], lo["count"]
            if hp is None and lp is None:
                st.metric(title, "—")
                return
            hp = hp or 0; lp = lp or 0
            # 大數字顯示「兩邊較大者」:站上/漲/新高方較大→綠(多方),否則紅(空方)
            big_is_hi = hp >= lp
            big_val = hp if big_is_hi else lp
            big_col = GREEN if big_is_hi == good_when_high else RED
            # 對比條:單一 div,linear-gradient 在 hp% 處分界,左綠右紅填滿整條
            # (綠=站上/漲/新高方 hp、紅=對立方 lp;即使 hp+lp≠100 如 adv/dec 有 unchanged,
            # 仍以 hp 為分界點,兩色各佔一邊)
            bar = (
                f'<div style="height:10px;border-radius:5px;margin:6px 0;'
                f'background:linear-gradient(90deg,'
                f'{_rgba(GREEN,.85)} 0%,{_rgba(GREEN,.85)} {hp:.1f}%,'
                f'{_rgba(RED,.85)} {hp:.1f}%,{_rgba(RED,.85)} 100%)"></div>'
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:.75em;color:{SUB}">'
                f'<span style="color:{GREEN}">{hp:.1f}%</span>'
                f'<span style="color:{RED}">{lp:.1f}%</span></div>'
            )
            st.markdown(
                f'<div class="kpi" style="{CARD_GAP}"><div class="lbl" style="{LBL_LG}">{title}</div>'
                f'<div class="val" style="color:{big_col}">{big_val:.1f}%</div>'
                f'{bar}'
                f'<div class="sub" style="color:{SUB};{SUB_LG}">{hc or 0} / {lc or 0} 檔</div></div>',
                unsafe_allow_html=True)

    _pair(cols[0], "上漲 / 下跌",
          bd["advancing"], bd["declining"])
    _pair(cols[1], "新高 / 新低",
          bd["new_high"], bd["new_low"])
    _pair(cols[2], "站上 / 跌破 SMA50",
          bd["above_sma50"], bd["below_sma50"])
    _pair(cols[3], "站上 / 跌破 SMA200",
          bd["above_sma200"], bd["below_sma200"])


def render():
    apply_dark_theme()
    tc, rc = st.columns([8, 1])
    with tc:
        st.title("📊 市場概覽")
    with rc:
        # 純 icon refresh 按鈕(靠右)
        refresh_button(key="refresh_market", help="清除快取並重新抓取 yfinance/Finviz/F&G")
    health = index_health()
    _render_env_score()
    st.divider()
    _render_index_cards(health)
    st.divider()
    _render_sentiment(health)
