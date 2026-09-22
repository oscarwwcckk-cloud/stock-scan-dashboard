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
    index_health, sector_rotation, market_breadth, breadth_available,
)
from lib.data_loader import (
    load_feargreed, feargreed_signature,
)

# trend_state → 顏色
TREND_COLOR = {
    "Confirmed Uptrend": GREEN,
    "Uptrend Under Pressure": ORANGE,
    "Recovery Attempt": ORANGE,
    "Market in Correction": RED,
    "Bear Market": RED,
    "Insufficient Data": GRID,
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
                f'<div class="sub" style="color:{color};font-weight:600">{r.trend_state}</div>'
                f'</div>', unsafe_allow_html=True)
            st.caption(
                f"MA50 {r.ma50:.1f}({_fmt_pct(r.pct_from_ma50)}) · "
                f"MA200 {r.ma200:.1f}({_fmt_pct(r.pct_from_ma200)})\n\n"
                f"RSI14 {r.rsi14:.1f} · Dist days {r.dist_days}\n\n"
                f"52w {r.low_52w:.1f}–{r.high_52w:.1f} "
                f"({_fmt_pct(r.pct_from_52w_high)} from high)"
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


def _render_sector_rotation():
    st.subheader("🏭 產業類股輪動")
    rows = sector_rotation()
    if not rows:
        st.warning("類股輪動資料抓取失敗(yfinance 可能限流)。稍後再試。")
        return
    df = pd.DataFrame(rows)
    # 表
    disp = df[["name", "benchmark", "rs_rating", "rs_1d", "rs_5d", "rs_20d", "rs_63d", "n"]].copy()
    disp.columns = ["Sector", "Bench", "RS", "1d", "5d", "20d", "63d", "N"]
    st.dataframe(disp, use_container_width=True, hide_index=True,
                 column_config={"RS": st.column_config.ProgressColumn(
                     "RS Rating", min_value=0, max_value=99, format="%d")})
    st.caption("RS Rating 1-99(越高越強);1d/5d/20d/63d 為相對 benchmark 的超額報酬%(正綠負紅)。")
    # 熱力圖
    try:
        mat = df[["rs_1d", "rs_5d", "rs_20d", "rs_63d"]].astype(float).values
        fig = go.Figure(data=go.Heatmap(
            z=mat, x=["1d", "5d", "20d", "63d"],
            y=df["name"], colorscale="RdYlGn",
            zmid=0, hovertemplate="%{y} %{x}: %{z:+.2f}%<extra></extra>"))
        fig.update_layout(
            height=max(300, 26 * len(df)), margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(color=TXT), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))
    except Exception:
        st.caption("熱力圖繪製失敗")


def _render_sentiment(health):
    """情緒面板:VIX + Fear & Greed 一行,Finviz 四項廣度一行。

    health = index_health() 結果(取 VIX)。F&G 走 load_feargreed(本機 playwright 抓的 JSON)。
    Finviz 廣度走 market_breadth()(雲端 egress 被擋時四項全 None → 該行降級顯示)。"""
    st.subheader("🌡️ 市場情緒 / 廣度")
    # 情緒面板內副標統一:放大 + 粗體(不動其他頁面的 .sub 預設 12px)
    SUB_LG = "font-size:14px;font-weight:600"
    keys = ["SPX", "NDX", "DJI"]
    any_vix = next((health.get(k, {}) for k in keys if health.get(k)), None)
    vix = (any_vix or {}).get("vix") if any_vix else None

    # ── Fear & Greed(本機抓的 JSON,可能過時或抓失敗)──
    fg = load_feargreed(feargreed_signature())

    # ── 第一行:VIX + Fear & Greed ──
    c1, c2 = st.columns(2)
    with c1:
        if vix is not None:
            st.markdown(
                f'<div class="kpi"><div class="lbl">VIX 情緒</div>'
                f'<div class="val" style="color:{vcolor(vix)}">{vix:.1f}</div>'
                f'<div class="sub" style="{SUB_LG}">{vix_label(vix)}</div></div>',
                unsafe_allow_html=True)
        else:
            st.metric("VIX 情緒", "—")
    with c2:
        if fg and fg.get("value") is not None:
            val = fg["value"]
            rating = fg.get("rating", "?")
            st.markdown(
                f'<div class="kpi"><div class="lbl">Fear & Greed Index</div>'
                f'<div class="val" style="color:{_fg_color(val)}">{val}</div>'
                f'<div class="sub" style="{SUB_LG}">{rating}</div></div>',
                unsafe_allow_html=True)
            st.caption(f"本機 playwright 抓取:{fg.get('fetched_at','?')}")
        else:
            st.metric("CNN Fear & Greed", "—")
            st.caption("本機未抓取(feargreed.json 不存在或抓失敗)")

    # ── 第二行:Finviz 四項廣度(Adv/Dec · NH/NL · Above SMA50 · Above SMA200)──
    bd = market_breadth()
    if not breadth_available(bd):
        st.info("Finviz 廣度無法取得(雲端 egress 可能被擋;本機可正常顯示)。")
        return
    cols = st.columns(4)

    def _rgba(hexc, a):
        return f"rgba({int(hexc[1:3],16)},{int(hexc[3:5],16)},{int(hexc[5:7],16)},{a})"

    def _pair(col, title, hi, lo, good_when_high=True):
        """一張卡:大 %(站上/漲/新高,綠)+ 綠紅比例對比條 + 對立 % + 件數。"""
        with col:
            hp, hc = hi["pct"], hi["count"]
            lp, lc = lo["pct"], lo["count"]
            if hp is None and lp is None:
                st.metric(title, "—")
                return
            hp = hp or 0; lp = lp or 0
            hi_col = GREEN if (hp >= lp) == good_when_high else RED
            bar = (
                f'<div style="display:flex;height:10px;border-radius:5px;overflow:hidden;'
                f'background:{GRID};margin:6px 0">'
                f'<div style="width:{hp:.1f}%;background:{_rgba(GREEN,.85)}"></div>'
                f'<div style="width:{lp:.1f}%;background:{_rgba(RED,.85)}"></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:.75em;color:{SUB}">'
                f'<span style="color:{GREEN}">{hp:.1f}%</span>'
                f'<span style="color:{RED}">{lp:.1f}%</span></div>'
            )
            st.markdown(
                f'<div class="kpi"><div class="lbl">{title}</div>'
                f'<div class="val" style="color:{hi_col}">{hp:.1f}%</div>'
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
    st.caption("Finviz 廣度 · 綠 = 漲/新高/站上均線 · 快取 1h · "
               f"抓取時間:{bd.get('fetched_at','?')}")


def render():
    apply_dark_theme()
    tc, rc = st.columns([8, 1])
    with tc:
        st.title("📊 Market Situation")
    with rc:
        # 純 icon refresh 按鈕(靠右)
        refresh_button(key="refresh_market", help="清除快取並重新抓取 yfinance/Finviz/F&G")
    st.caption("資料源:yfinance + Finviz(免 OpenD)。`@st.cache_data` 快取 1 小時。")
    health = index_health()
    _render_index_cards(health)
    st.divider()
    _render_sentiment(health)
    st.divider()
    _render_sector_rotation()
