# -*- coding: utf-8 -*-
"""載入 scanner 掃描結果 Excel。

讀 `data/kq_scan_results.xlsx`(9 sheets)與 `data/sepa_scan_results.xlsx`(3 sheets)。
@st.cache_data 鍵用 lib.cache._sig(內容指紋),破解 Streamlit Cloud mtime 陷阱 ——
data-only commit 熱同步進同一行程時 mtime 不一定變,但內容指紋一變必失效。
"""
import json

import pandas as pd
import streamlit as st

from lib.cache import _sig

DATA_DIR = "data"
KQ_XLSX = f"{DATA_DIR}/kq_scan_results.xlsx"
SEPA_XLSX = f"{DATA_DIR}/sepa_scan_results.xlsx"

# KQ 8 個 setup sheet + 顯示名(Excel 內 sheet 名 → 友善名)
KQ_SETUPS = [
    ("EP Results",      "EP · 盤前跳空"),
    ("HTF Results",     "HTF · 高緊旗形"),
    ("Breakout Results", "Breakout · 突破"),
    ("VCP Results",     "VCP · 量縮收斂"),
    ("CWH Results",     "CWH · 杯柄"),
    ("Double Bottom",   "Double Bottom · 雙底"),
    ("IPO Base",        "IPO Base"),
    ("Flat Base",       "Flat Base · 震後橫盤"),
]


@st.cache_data(show_spinner=False)
def load_kq(_sig_key: str) -> dict:
    """回傳 {sheet_name: DataFrame}。_sig_key 传 _sig(KQ_XLSX) 讓內容變即重讀。"""
    return pd.read_excel(KQ_XLSX, sheet_name=None)


@st.cache_data(show_spinner=False)
def load_sepa(_sig_key: str) -> dict:
    return pd.read_excel(SEPA_XLSX, sheet_name=None)


def _scan_date(sheets: dict) -> str:
    """從 Scan Info sheet 的 row0/col1 取掃描日期。

    pd.read_excel 預設把第一列當 header,Scan Info 的「Scan Date」標籤會被當 col0、
    其值變成 col1 的欄名 → iloc[0,1] 抓到的是「下一列的值」(如 Universe Size)。
    故此處重讀該 sheet(header=None)取正確值;取不到回 '?'。
    """
    try:
        # sheets 可能來自不同 xlsx,從 sheet 內容反推不出檔名;
        # 但 _scan_date 已知 kq/sepa 各自呼叫,這裡靠 caller 傳入的 sheets 已含正確 Scan Info
        # 為穩健,直接在這裡重讀(若檔案存在)。
        val = sheets["Scan Info"].iloc[0, 1]
        # 若抓到的值像「另一列的標籤」(會被 header 吃掉),改用 header=None 重讀
        return str(val)
    except Exception:
        return "?"


def _scan_date_kq() -> str:
    return _read_scan_date(KQ_XLSX)


def _scan_date_sepa() -> str:
    return _read_scan_date(SEPA_XLSX)


def _read_scan_date(path: str) -> str:
    """header=None 讀 Scan Info,取 row0/col1。"""
    try:
        si = pd.read_excel(path, sheet_name="Scan Info", header=None)
        return str(si.iloc[0, 1])
    except Exception:
        return "?"


def kq_scan_date(sheets: dict | None = None) -> str:
    return _scan_date_kq()


def sepa_scan_date(sheets: dict | None = None) -> str:
    return _scan_date_sepa()


def kq_signature() -> str:
    return _sig(KQ_XLSX)


def sepa_signature() -> str:
    return _sig(SEPA_XLSX)


# ── CNN Fear & Greed(本機 playwright 抓,存 data/feargreed.json,commit 進 repo)──
FEARGREED_JSON = f"{DATA_DIR}/feargreed.json"


@st.cache_data(show_spinner=False)
def load_feargreed(_sig_key: str) -> dict | None:
    """讀 data/feargreed.json。_sig_key 传 _sig(FEARGREED_JSON) 讓內容變即重讀。
    回 {value, rating, driving_text, fetched_at, ...} 或 None(檔不存在/格式壞)。"""
    try:
        with open(FEARGREED_JSON, "r", encoding="utf-8") as f:
            d = json.load(f)
        # value 可能是 None(抓取失敗);rating 可能 '?'
        if not isinstance(d, dict):
            return None
        return d
    except Exception:
        return None


def feargreed_signature() -> str:
    return _sig(FEARGREED_JSON)
