# -*- coding: utf-8 -*-
"""板塊分析頁 — 板塊强度(表 + 60d 超額報酬柱圖)+ 板塊 RS 歷史折線圖。

第一區(板塊强度)自市場概覽頁遷入:sector_rotation() 當下快照。
第二區(板塊 RS 歷史):sector_rs_history() 各板塊相對基準強弱比值時間序列
(正規化 100 起點,線往上=跑贏、往下=落後),下拉選 3m/6m/1y。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.style import (
    apply_dark_theme, refresh_button, BG, GRID, TXT, SUB,
    GREEN, RED, _chart_cfg, line_hover,
)
from lib.market_service import sector_rotation
from lib.sector_history import sector_rs_history


def _render_sector_rotation():
    """板塊强度:當下快照表(RS 評分 + 10/30/60 日超額報酬)+ 60d 柱圖。"""
    st.subheader("💪 板塊强度")
    rows = sector_rotation()
    if not rows:
        st.warning("板塊强度資料抓取失敗(yfinance 可能限流)。稍後再試。")
        return
    df = pd.DataFrame(rows)
    # 表
    disp = df[["name", "benchmark", "rs_rating", "rs_10d", "rs_30d", "rs_60d", "n", "key"]].copy()
    disp.columns = ["板塊", "基准", "RS", "10日 (%)", "30日 (%)", "60日 (%)", "檔數", "明細"]
    # 「明細」欄放成分股頁連結(絕對路徑 + query param 帶 sector key)
    disp["明細"] = disp["明細"].map(lambda k: f"./constituents?sector={k}")
    st.dataframe(disp, use_container_width=True, hide_index=True,
                 column_config={
                     "RS": st.column_config.ProgressColumn(
                         "RS 評分", min_value=0, max_value=99, format="%d"),
                     "明細": st.column_config.LinkColumn(
                         "明細", display_text="成分股", help="點擊查看該板塊成分股明細"),
                 })
    st.caption("RS 評分 1-99(越高越強);柱形 = 60日超額報酬由強到弱排序"
               "(正=跑贏基准綠、負=落後紅、長度=幅度)。")
    # 水平柱形圖:60d 超額報酬排序,正綠負紅。可正可負(零軸分隔)。
    try:
        d = df[["name", "rs_60d"]].dropna().copy()
        d["rs_60d"] = d["rs_60d"].astype(float)
        d = d.sort_values("rs_60d", ascending=True)  # 升冪 → 最強在頂(plotly y 由下而上)
        names = d["name"].tolist()
        vals = d["rs_60d"].tolist()
        colors = [GREEN if v >= 0 else RED for v in vals]
        labels = [f"{v:+.2f}%" for v in vals]
        fig = go.Figure(data=go.Bar(
            y=names, x=vals, orientation="h",
            marker_color=colors,
            text=labels, textposition="outside",
            textfont=dict(size=11, color=SUB),
            hovertemplate="<b>%{y}</b><br>60日超額報酬: %{x:+.2f}%<extra></extra>",
            showlegend=False))
        fig.update_layout(
            height=max(440, 26 * len(names) + 50), margin=dict(l=10, r=60, t=10, b=30),
            paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TXT, size=11),
            bargap=0.5,
            xaxis=dict(title="60日超額報酬 (%)", color=SUB, gridcolor=GRID,
                       zeroline=True, zerolinecolor=GRID, zerolinewidth=1.5,
                       tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=11, color=TXT), showgrid=False, autorange=True))
        line_hover(fig)
        st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))
    except Exception:
        st.caption("板塊柱形圖繪製失敗")


def _line_color(latest: float | None) -> str:
    """線色由「最新值」定:≥100 跑贏基準=綠、<100 落後=紅。"""
    if latest is None:
        return SUB
    return GREEN if latest >= 100 else RED


def _render_rs_history():
    """板塊 RS 歷史折線圖:18 板塊相對基準強弱比值(100 起點),下拉選 3m/6m/1y。"""
    st.subheader("📈 板塊 RS 歷史")
    period = st.selectbox("區間", ["3m", "6m", "1y"], index=1,
                          format_func=lambda p: {"3m": "3 個月", "6m": "6 個月", "1y": "1 年"}[p],
                          key="rs_hist_period")
    data = sector_rs_history(period)
    if not data:
        st.warning("板塊 RS 歷史資料抓取失敗(yfinance 可能限流)。稍後再試。")
        return

    try:
        fig = go.Figure()
        for skey, v in data.items():
            s = v["series"]
            if s is None or len(s) < 2:
                continue
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values, mode="lines",
                name=f"{v['name']} ({v['benchmark']})",
                line=dict(color=_line_color(v.get("latest")), width=1.5),
                opacity=0.85,
                hovertemplate="%{fullData.name}: %{y:.1f}<extra></extra>",
                showlegend=True))
        # 100 基準線(與大盤同步)
        fig.add_hline(y=100, line=dict(color=GRID, width=1, dash="dash"))
        fig.update_layout(
            height=560, margin=dict(l=10, r=20, t=10, b=30),
            paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=TXT, size=11),
            legend=dict(orientation="h", y=-0.15, x=0,
                        font=dict(size=10), itemwidth=40),
            xaxis=dict(showgrid=True, gridcolor=GRID, color=SUB,
                       rangebreaks=[dict(bounds=["sat", "mon"], pattern="day of week")]),
            yaxis=dict(title="相對基準強弱(100 起點)", showgrid=True, gridcolor=GRID,
                       color=SUB, zeroline=False))
        line_hover(fig)
        st.plotly_chart(fig, use_container_width=True, config=_chart_cfg(fig))
        st.caption("每條線 = 板塊等權指數 ÷ 基準(QQQ/SPY),正規化 100 起點:"
                   "線往上=跑贏大盤、往下=落後;虛線=與大盤同步。"
                   "線色:綠=目前跑贏、紅=目前落後。")
    except Exception:
        st.caption("板塊 RS 歷史折線圖繪製失敗")


def render():
    apply_dark_theme()
    tc, rc = st.columns([8, 1])
    with tc:
        st.title("🏭 板塊分析")
    with rc:
        # 純 icon refresh 按鈕(靠右)
        refresh_button(key="refresh_sectors",
                       help="清除快取並重新抓取板塊 RS 與歷史(yfinance/SPDR 持倉)")
    _render_sector_rotation()
    st.divider()
    _render_rs_history()
