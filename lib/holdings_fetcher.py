# -*- coding: utf-8 -*-
"""動態抓 SPDR 板塊 ETF 每日持倉 → 成分股 ticker 清單。

取代 sector_map 裡過時的手動成分股清單:SPDR 板塊 ETF(XLE/XLF/...)每日更新持倉,
基金經理自動處理併購/改名/下市 → 成分股永遠新鮮,不會再有 delisted ticker。

URL 格式(已驗證 11 個 SPDR 板塊 ETF 全部可用):
    https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/
    etfs/us/holdings-daily-us-en-{ticker_lower}.xlsx

xlsx 格式:前 ~4 行是 header(基金名/日期),第 5 行起是表格,欄含
Name/Ticker/Identifier/SEDOL/Weight/Sector。Ticker 欄可能有 cash/cash-equiv('-')要濾掉。

@st.cache_data(ttl=86400) ── 持倉每日才更新一次,1 天快取足夠。
"""
from __future__ import annotations

import io
import urllib.request

import pandas as pd
import streamlit as st

SPDR_HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/library-content/products/"
    "fund-data/etfs/us/holdings-daily-us-en-{etf_lower}.xlsx"
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _parse_holdings_xlsx(data: bytes) -> list[str]:
    """從 SPDR holdings xlsx 抽成分股 ticker(濾掉 cash/cash-equiv 與非股票)。"""
    # 前 ~4 行是表頭敘述,skiprows=4 落到表格;表格第一欄是 Name,Ticker 在第 2 欄
    xls = pd.read_excel(io.BytesIO(data), skiprows=4)
    if "Ticker" not in xls.columns:
        # 不同 ETF 偶爾欄名微差,容錯找含 ticker 的欄
        tkr_col = next((c for c in xls.columns if "ticker" in str(c).lower()), None)
        if tkr_col is None:
            return []
    else:
        tkr_col = "Ticker"
    tickers = []
    for v in xls[tkr_col].dropna():
        s = str(v).strip()
        # 濾掉 cash / cash equivalents / 衍生品('-' 或含 cash 字樣)
        if not s or s == "-" or "cash" in s.lower():
            continue
        # ticker 應是純字母(可能含 . / -),濾掉明顯非 ticker 的長字串
        if len(s) > 8:
            continue
        tickers.append(s)
    return tickers


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_spdr_holdings(etf: str) -> list[str]:
    """抓某 SPDR 板塊 ETF 的成分股 ticker 清單。失敗回 [](頁面降級跳過該板塊)。"""
    url = SPDR_HOLDINGS_URL.format(etf_lower=etf.lower())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        return _parse_holdings_xlsx(data)
    except Exception:
        return []
