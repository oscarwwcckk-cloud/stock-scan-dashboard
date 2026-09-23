# -*- coding: utf-8 -*-
"""成分股明細頁 — 從板塊强度表「明細」連結點入。

讀 query param ?sector=<key>,顯示該板塊所有成分股的個股績效:
RS 評分(1-99)、40/20/20/20 加權分、10/30/60 日報酬,加一張 60 日紅綠柱圖。
資料走 market_service.sector_constituents_performance(@st.cache_data ttl=1h)。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.style import (
    apply_dark_theme, BG, GRID, TXT, SUB, GREEN, RED, _chart_cfg, line_hover,
)
from lib.market_service import sector_constituents_performance


def render():
    apply_dark_theme()
    sector_key = st.query_params.get("sector")
    if not sector_key:
        st.warning("未指定板塊。請從「市場概覽」頁的板塊表點「明細」進入。")
        return

    data = sector_constituents_performance(sector_key)
    if data is None:
        st.error(f"找不到板塊:{sector_key}")
        return

    name = data["name"]
    bench = data["benchmark"]
    cons = data["constituents"]
    st.title(f"🏢 {name} 成分股")
    st.caption(f"基准 {bench}　|　成分股 {len(cons)} 檔　|　"
               "RS 評分 1-99(越高越強,vs SPX);報酬為個股絕對漲跌 %。")

    if not cons:
        st.warning("此板塊成分股資料抓取失敗(yfinance 可能限流),稍後再試。")
        return

    df = pd.DataFrame(cons)
    disp = df[["ticker", "rs_rating", "rs_score", "r_10d", "r_30d", "r_60d"]].copy()
    disp.columns = ["代碼", "RS 評分", "加權分", "10日 (%)", "30日 (%)", "60日 (%)"]
    st.dataframe(
        disp, use_container_width=True, hide_index=True,
        column_config={
            "RS 評分": st.column_config.ProgressColumn(
                "RS 評分", min_value=0, max_value=99, format="%d"),
            "加權分": st.column_config.NumberColumn("加權分", format="%.2f"),
            "10日 (%)": st.column_config.NumberColumn("10日 (%)", format="+.2f%%"),
            "30日 (%)": st.column_config.NumberColumn("30日 (%)", format="+.2f%%"),
            "60日 (%)": st.column_config.NumberColumn("60日 (%)", format="+.2f%%"),
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
