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

from pages import page_scan, page_market

st.set_page_config(page_title="市場概覽 & 股票篩選", layout="wide",
                   initial_sidebar_state="expanded")
apply_dark_theme()


def _page_scan():
    apply_dark_theme()
    page_scan.render()


def _page_market():
    apply_dark_theme()
    page_market.render()


nav = st.navigation([
    st.Page(_page_market, title="市場概覽", icon="📊", default=True),
    st.Page(_page_scan,  title="股票篩選",  icon="🔍"),
])
nav.run()
