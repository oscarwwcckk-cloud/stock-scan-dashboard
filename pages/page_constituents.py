# -*- coding: utf-8 -*-
"""成分股頁 — 三層導航(query param 驅動)。

    無 param                  → 板塊總覽卡片頁(18 板塊,點卡片進入)
    ?sector=xxx               → 該板塊成分股清單(表格 + 60 日紅綠柱圖)
    ?sector=xxx&ticker=NVDA   → 個股 TradingView Advanced Chart widget

個股績效(RS 評分/加權分/10-30-60 日報酬)走 market_service.sector_constituents_performance
(@st.cache_data ttl=1h);板塊 RS 走 sector_rotation()。TV widget 走 lib/tv_widget.py,
瀏覽器端載入,伺服器無需 egress。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.style import (
    apply_dark_theme, BG, GRID, TXT, SUB, GREEN, ORANGE, RED, _chart_cfg, line_hover,
)
from lib.market_service import sector_rotation, sector_constituents_performance
from lib.tv_widget import tv_symbol, embed_html


def _rs_color(rating: int) -> str:
    """RS 1-99 → 色(≥70 綠、45-69 橘、<45 紅)。"""
    if rating is None:
        return SUB
    if rating >= 70:
        return GREEN
    if rating >= 45:
        return ORANGE
    return RED


def _sector_url(key: str = "", ticker: str = "") -> str:
    """組本頁導航 URL:./constituents[?sector=k[&ticker=t]]。"""
    params = []
    if key:
        params.append(f"sector={key}")
    if ticker:
        params.append(f"ticker={ticker}")
    return "./constituents?" + "&".join(params) if params else "./constituents"


def _render_overview():
    """板塊總覽卡片頁(default)。"""
    st.title("🏢 板塊成分股")
    st.caption("點板塊卡片 → 查看成分股清單與個股 RS 評分;再點個股看 TradingView 即時圖表。")
    rows = sector_rotation()
    if not rows:
        st.warning("板塊資料抓取失敗(yfinance 可能限流)。稍後再試。")
        return

    cols = st.columns(4)
    for i, r in enumerate(rows):
        with cols[i % 4]:
            rating = r.get("rs_rating")
            color = _rs_color(rating)
            st.markdown(
                f'<div class="kpi">'
                f'<div class="lbl">{r["name"]}</div>'
                f'<div class="val" style="color:{color}">{rating if rating is not None else "—"}</div>'
                f'<div class="sub" style="color:{SUB}">RS 評分 · {r.get("n", 0)} 檔 · {r.get("benchmark","")}</div>'
                f'</div>', unsafe_allow_html=True)
            st.link_button("成分股 →", url=_sector_url(r["key"]),
                           use_container_width=True, key=f"ov_{r['key']}")


def _render_constituents(sector_key: str):
    """某板塊成分股清單頁(表格 + 60 日柱圖)。"""
    data = sector_constituents_performance(sector_key)
    if data is None:
        st.error(f"找不到板塊:{sector_key}")
        return

    name = data["name"]
    bench = data["benchmark"]
    cons = data["constituents"]
    st.title(f"🏢 {name} 成分股")
    st.link_button("← 板塊總覽", url=_sector_url(), use_container_width=False)
    st.caption(f"基准 {bench}　|　成分股 {len(cons)} 檔　|　"
               "RS 評分 1-99(越高越強,vs SPX);報酬為個股絕對漲跌 %。點「📈 圖表」看個股即時走勢。")

    if not cons:
        st.warning("此板塊成分股資料抓取失敗(yfinance 可能限流),稍後再試。")
        return

    df = pd.DataFrame(cons)
    disp = df[["ticker", "rs_rating", "rs_score", "r_10d", "r_30d", "r_60d"]].copy()
    disp.columns = ["代碼", "RS 評分", "加權分", "10日 (%)", "30日 (%)", "60日 (%)"]
    disp["圖表"] = df["ticker"].map(lambda t: _sector_url(sector_key, t))
    st.dataframe(
        disp, use_container_width=True, hide_index=True,
        column_config={
            "RS 評分": st.column_config.ProgressColumn(
                "RS 評分", min_value=0, max_value=99, format="%d"),
            "加權分": st.column_config.NumberColumn("加權分", format="%.2f"),
            "10日 (%)": st.column_config.NumberColumn("10日 (%)", format="%+.2f%%"),
            "30日 (%)": st.column_config.NumberColumn("30日 (%)", format="%+.2f%%"),
            "60日 (%)": st.column_config.NumberColumn("60日 (%)", format="%+.2f%%"),
            "圖表": st.column_config.LinkColumn(
                "圖表", display_text="📈 圖表", help="查看個股 TradingView 即時圖表"),
        },
    )

    # 60 日報酬水平柱圖:升冪(最強在頂)、正綠負紅,零軸分隔
    try:
        d = df[["ticker", "r_60d"]].dropna().copy()
        d["r_60d"] = d["r_60d"].astype(float)
        d = d.sort_values("r_60d", ascending=True)
        names = d["ticker"].tolist()
        vals = d["r_60d"].tolist()
        colors = [GREEN if v >= 0 else RED for v in vals]
        labels = [f"{v:+.2f}%" for v in vals]
        fig = go.Figure(data=go.Bar(
            y=names, x=vals, orientation="h",
            marker_color=colors,
            text=labels, textposition="outside",
            textfont=dict(size=10, color=SUB),
            hovertemplate="<b>%{y}</b><br>60日報酬: %{x:+.2f}%<extra></extra>",
            showlegend=False))
        fig.update_layout(
            height=max(440, 26 * len(names) + 50), margin=dict(l=10, r=60, t=10, b=30),
            paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TXT, size=11),
            bargap=0.5,
            xaxis=dict(title="60日報酬 (%)", color=SUB, gridcolor=GRID,
                       zeroline=True, zerolinecolor=GRID, zerolinewidth=1.5,
                       tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=11, color=TXT), showgrid=False, autorange=True))
        line_hover(fig)
        st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))
    except Exception:
        st.caption("成分股 60 日柱圖繪製失敗")


def _fmt(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _render_stock_chart(sector_key: str, ticker: str):
    """個股 TradingView 圖表頁。"""
    data = sector_constituents_performance(sector_key)
    name = data["name"] if data else sector_key
    st.title(f"📈 {ticker}")
    st.link_button(f"← {name} 成分股", url=_sector_url(sector_key), use_container_width=False)

    # 從 cache 資料找該股績效摘要
    perf = None
    if data and data["constituents"]:
        perf = next((c for c in data["constituents"] if c["ticker"] == ticker), None)
    if perf:
        r = perf["rs_rating"]
        st.caption(
            f"RS 評分 **{r}**　|　加權分 **{perf['rs_score']}**　|　"
            f"10日 {_fmt(perf['r_10d'])}　|　30日 {_fmt(perf['r_30d'])}　|　60日 {_fmt(perf['r_60d'])}")

    # 成分股切換(同板塊內換股)
    tickers = [c["ticker"] for c in data["constituents"]] if data and data["constituents"] else []
    if tickers:
        sel = st.selectbox("切換成分股", tickers,
                           index=tickers.index(ticker) if ticker in tickers else 0,
                           key="stock_switch")
        if sel != ticker:
            st.query_params["ticker"] = sel
            st.rerun()

    symbol = tv_symbol(ticker)
    # st.iframe(height="content"):iframe 內 <script src> 會正常執行(TV widget 載入),
    # Streamlit 自動量 widget 容器高度(內嵌 JS 鎖正方形)讓 iframe 貼合。
    st.iframe(embed_html(symbol), height="content")


def render():
    apply_dark_theme()
    sector_key = st.query_params.get("sector")
    ticker = st.query_params.get("ticker")

    if not sector_key:
        _render_overview()
    elif not ticker:
        _render_constituents(sector_key)
    else:
        _render_stock_chart(sector_key, ticker)
