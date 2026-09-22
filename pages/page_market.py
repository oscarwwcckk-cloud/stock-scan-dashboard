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
    apply_dark_theme, kpi_card, BG, CARD, GRID, TXT, SUB,
    ORANGE, BLUE, GREEN, RED, TEAL, _chart_cfg, line_hover,
)
from lib.market_service import (
    index_health, sector_rotation, market_breadth, breadth_available,
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


def _index_chart(close, title=""):
    """畫 price + MA50 + MA200 線圖(取近 ~126 根 ≈ 6 個月,避免太擠)。
    仿舊 stock-dashboard 指數圖:三條線,深色飛書風。"""
    if close is None or len(close) < 2:
        return
    s = close.iloc[-126:] if len(close) > 126 else close
    ma50 = s.rolling(50, min_periods=1).mean()
    ma200 = s.rolling(200, min_periods=1).mean() if len(s) >= 30 else None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, name="Price",
                             line=dict(color=BLUE, width=2)))
    fig.add_trace(go.Scatter(x=ma50.index, y=ma50.values, name="MA50",
                             line=dict(color=ORANGE, width=1.3)))
    if ma200 is not None:
        fig.add_trace(go.Scatter(x=ma200.index, y=ma200.values, name="MA200",
                                 line=dict(color=SUB, width=1.3, dash="dot")))
    fig.update_layout(
        height=220, margin=dict(l=8, r=8, t=24, b=8),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TXT, size=10),
        showlegend=True, legend=dict(
            orientation="h", y=1.12, x=0, font=dict(size=9)),
        xaxis=dict(showgrid=False, color=GRID),
        yaxis=dict(showgrid=True, gridcolor=GRID, color=GRID),
        title=dict(text=title, font=dict(size=11, color=SUB)) if title else None,
    )
    line_hover(fig)
    st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))


def _render_index_cards():
    st.subheader("📈 大盤指數健康度")
    health = index_health()
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
            _index_chart(d.get("close"), key)
            st.markdown("")  # 卡間距
    # VIX 情緒
    any_vix = next((health.get(k, {}) for k in keys if health.get(k)), None)
    vix = (any_vix or {}).get("vix") if any_vix else None
    if vix is not None:
        vcol = GREEN if vix < 20 else (ORANGE if vix < 25 else RED)
        st.markdown(
            f'<div class="kpi" style="display:inline-block;min-width:160px">'
            f'<div class="lbl">VIX 情緒</div>'
            f'<div class="val" style="color:{vcolor(vix)}">{vix:.1f}</div>'
            f'<div class="sub">{vix_label(vix)}</div></div>',
            unsafe_allow_html=True)


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


def _render_breadth():
    st.subheader("🌍 市場廣度 / 情緒")
    bd = market_breadth()
    if not breadth_available(bd):
        st.warning("廣度資料無法取得(雲端對 Finviz egress 可能被擋,或本機網路問題)。")
        return
    cols = st.columns(4)
    def _card(col, title, pct, count, good_when_high=True):
        with col:
            if pct is None:
                st.metric(title, "—")
                return
            color = GREEN if (pct >= 50) == good_when_high else RED
            st.metric(title, f"{pct:.1f}%", f"{count or 0} 檔")
    a = bd["advancing"]["pct"]; d = bd["declining"]["pct"]
    _card(cols[0], "上漲", a, bd["advancing"]["count"])
    _card(cols[1], "下跌", d, bd["declining"]["count"], good_when_high=False)
    _card(cols[2], "站上 SMA50", bd["above_sma50"]["pct"], bd["above_sma50"]["count"])
    _card(cols[3], "站上 SMA200", bd["above_sma200"]["pct"], bd["above_sma200"]["count"])
    st.caption(f"新高 {bd['new_high']['pct'] or '—'}% / 新低 {bd['new_low']['pct'] or '—'}%　·　"
               f"快取 1h。抓取時間:{bd.get('fetched_at','?')}")


def render():
    apply_dark_theme()
    st.title("📊 Market Situation")
    st.caption("資料源:yfinance + Finviz(免 OpenD)。`@st.cache_data` 快取 1 小時。")
    _render_index_cards()
    st.divider()
    _render_sector_rotation()
    st.divider()
    _render_breadth()
