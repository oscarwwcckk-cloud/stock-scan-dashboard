# -*- coding: utf-8 -*-
"""Stock Scan Dashboard — 入口。

兩大分頁(深色飛書風格,仿 futu-dashboard):
    search  Stock Scanning   — kq 8 setup + SEPA 掃描結果,前端 slider 即時再篩選
    chart   Market Situation — 指數健康度 + 產業輪動 + 市場廣度

執行:
    streamlit run dashboard.py
"""
import streamlit as st
from lib.style import apply_dark_theme

from pages import page_scan, page_market, page_sectors, page_constituents

st.set_page_config(page_title="市場概覽 & 股票篩選", layout="wide",
                   initial_sidebar_state="expanded")
apply_dark_theme()


def _page_scan():
    apply_dark_theme()
    page_scan.render()


def _page_market():
    apply_dark_theme()
    page_market.render()


def _page_sectors():
    apply_dark_theme()
    page_sectors.render()


def _page_constituents():
    apply_dark_theme()
    page_constituents.render()


nav = st.navigation({
    # 空字串 section:頁面顯示在分組之前(頂層獨立項)
    "": [
        st.Page(_page_market, title="市場概覽", icon="📊", default=True),
        st.Page(_page_scan,  title="股票篩選",  icon="🔍"),
    ],
    # 「板塊分析」分組:板塊分析頁 + 板塊成分頁,sidebar 裡歸在同標題下
    "板塊分析": [
        st.Page(_page_sectors, title="板塊分析", icon="🏭"),
        st.Page(_page_constituents, title="板塊成分", icon="🏢", url_path="constituents"),
    ],
})
nav.run()
