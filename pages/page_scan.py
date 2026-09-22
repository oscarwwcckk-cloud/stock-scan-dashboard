# -*- coding: utf-8 -*-
"""Stock Scanning 頁 — kq 8 setup + SEPA,前端 slider 即時再篩選。

讀兩個 committed xlsx(_sig 鍵避 mtime 陷阱),依當下 setup sheet 顯示對應 slider。
重要限制:前端 slider 只能「縮小」已掃出的清單,無法浮現 scanner 沒掃到的股
(要擴大需回本機改 scanner 門檻重跑)—— 此限制在頁首明示。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.style import apply_dark_theme, ORANGE, GREEN, RED, BLUE, TXT, SUB
from lib import local_rescan
from lib.data_loader import (
    KQ_SETUPS, load_kq, load_sepa,
    kq_signature, sepa_signature,
    kq_scan_date, sepa_scan_date,
)

# 各 KQ setup sheet 的專屬篩選欄:(欄名, op, default_factor)
# op: ">=" = 至少, "<=" = 至多;default_factor 是 min/max 的分位(0.0=取 min,1.0=取 max)
KQ_SETUP_FILTERS: dict[str, list[tuple[str, str]]] = {
    "EP Results":      [("PreMkt Gap%", ">="), ("PreMkt Vol", ">=")],
    "HTF Results":     [("Pole%", ">="), ("Flag Drawdown%", "<="), ("Vol Contract%", "<="), ("Quality", ">=")],
    "Breakout Results": [("Consol DD%", "<="), ("Prior Move%", ">="), ("Breakout VolX", ">="), ("Stop%", "<=")],
    "VCP Results":     [("Contractions", "<="), ("Base Depth%", "<="), ("Px vs Pivot%", ">="), ("Vol Dryup%", "<=")],
    "CWH Results":     [("Cup Depth%", "<="), ("Handle Depth%", "<="), ("Handle Days", "<="), ("Potential%", ">=")],
    "Double Bottom":   [("Bottom Diff%", "<="), ("Rebound%", ">="), ("Prior Decline%", ">=")],
    "IPO Base":        [("Base Duration (bars)", "<="), ("Tight Range%", ">="), ("IPO Decline%", ">=")],
    "Flat Base":       [("Correction%", "<="), ("Base Range%", "<="), ("Px vs Pivot%", ">=")],
}
# SEPA "SEPA Results" 的專屬欄
SEPA_RESULTS_FILTERS = [
    ("% from Buy Point", "<="), ("RS Rating", ">="),
    ("J.Law Score", ">="), ("Base Amplitude%", "<="),
]
SEPA_PATTERN_FILTERS = [
    ("% from Buy Point", "<="), ("RS Rating", ">="),
    ("VCP Contractions", "<="), ("Base Depth%", "<="),
]


def _num_range(df: pd.DataFrame, col: str):
    """回傳該數值欄的 (min, max),容錯空/非數值。"""
    if col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return None
    lo, hi = float(s.min()), float(s.max())
    if lo == hi:
        hi = lo + 1
    return lo, hi


def _slider(df: pd.DataFrame, col: str, op: str, key: str):
    """建一個 slider,回傳篩選值或 None。範圍用該欄 min/max。"""
    rng = _num_range(df, col)
    if rng is None:
        return None
    lo, hi = rng
    step = 1 if (hi - lo) > 20 else 0.1
    if step == 1:
        lo, hi = int(lo), int(hi)
    # 預設值:">="取 min(不篩掉任何),"<="取 max(不篩掉任何)
    default = lo if op == ">=" else hi
    label = f"{col} {op}"
    return st.slider(label, lo, hi, default, step=step, key=key)


def _apply_filter(df: pd.DataFrame, col: str, op: str, val) -> pd.DataFrame:
    if val is None or col not in df.columns:
        return df
    s = pd.to_numeric(df[col], errors="coerce")
    if op == ">=":
        return df[s >= val]
    if op == "<=":
        return df[s <= val]
    return df


def _price_col(df: pd.DataFrame) -> str | None:
    """EP 用 PreMkt Price,其餘用 Price;SEPA 用 Price。"""
    for c in ("Price", "PreMkt Price"):
        if c in df.columns:
            return c
    return None


def _render_table(df: pd.DataFrame, title: str):
    st.caption(f"**{len(df)}** of {len(df)} matches" if False else f"**{len(df)}** matches — {title}")
    if df.empty:
        st.info("No rows pass the current filters.")
        return
    show = df.copy()
    # 嘗試把 Rank/Ticker 放前面
    front = [c for c in ("Rank", "Ticker") if c in show.columns]
    rest = [c for c in show.columns if c not in front]
    show = show[front + rest]
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button("⬇ 下載篩選結果 CSV", show.to_csv(index=False).encode(),
                       file_name=f"{title.replace(' ','_')}.csv", mime="text/csv")


def render():
    apply_dark_theme()
    tc, rc = st.columns([8, 1])
    with tc:
        st.title("🔍 股票篩選")
    with rc:
        # 純 icon refresh 按鈕(靠右)。
        # 本機(OpenD 連得上):重跑 kq-scanner 產新 xlsx → copy 進 data/ → 清快取重讀。
        # 雲端(連不到 OpenD):只清快取(讀回 committed xlsx;要新資料需先 push 觸發重部署)。
        local = local_rescan.is_local()
        help_txt = ("本機:重跑 kq-scanner 並重讀最新結果(約數分鐘)"
                    if local else "雲端:僅清快取;新資料需先 push 觸發重部署")
        if st.button("🔄", key="refresh_scan", help=help_txt,
                     use_container_width=False):
            if local:
                with st.spinner("本機重掃中(跑 kq-scanner,約數分鐘)…"):
                    ok, msg = local_rescan.run_scan()
                    if ok:
                        local_rescan.copy_results()
                    else:
                        st.error(f"重掃失敗:{msg}")
                        st.stop()
            try:
                st.cache_data.clear()
            except Exception:
                pass
            st.rerun()

    # ── 載入(快取鍵用 _sig) ──
    kq = load_kq(kq_signature())
    sepa = load_sepa(sepa_signature())
    kq_date = kq_scan_date(kq)
    sepa_date = sepa_scan_date(sepa)

    st.caption(f"KQ 掃描時間: **{kq_date}**　|　SEPA 掃描時間: **{sepa_date}**")
    st.info(
        "⚠️ 前端 slider 只能**縮小**已掃出的清單,無法浮現 scanner 沒掃到的股票。"
        "若要擴大結果,需回本機調整 scanner 的 `config.py` 門檻後重跑。"
    )

    tab_kq, tab_sepa = st.tabs(["KQ Setups", "SEPA"])

    # ── KQ ──
    with tab_kq:
        setup_names = [f"{disp}　({kq[sheet].shape[0]} hits)" if sheet in kq else f"{disp}　(0 hits)"
                       for sheet, disp in KQ_SETUPS]
        sel = st.selectbox("選擇 setup", range(len(KQ_SETUPS)),
                           format_func=lambda i: setup_names[i], key="kq_setup")
        sheet, disp = KQ_SETUPS[sel]
        df = kq.get(sheet, pd.DataFrame())
        if df.empty:
            st.warning(f"{sheet} 無資料")
            return
        st.subheader(disp)
        with st.sidebar:
            st.markdown(f"### 篩選 · {disp}")
            pcol = _price_col(df)
            vals = {}
            if pcol:
                v = _slider(df, pcol, ">=", "kq_price")
                if v is not None:
                    vals[pcol] = (">=", v)
            for col in ("Avg Vol 50d", "ADR 20%"):
                v = _slider(df, col, ">=", f"kq_{col}")
                if v is not None:
                    vals[col] = (">=", v)
            st.markdown("**Setup 專屬**")
            for col, op in KQ_SETUP_FILTERS.get(sheet, []):
                v = _slider(df, col, op, f"kq_{sheet}_{col}")
                if v is not None:
                    vals[col] = (op, v)
        filtered = df.copy()
        for col, (op, v) in vals.items():
            filtered = _apply_filter(filtered, col, op, v)
        _render_table(filtered, disp)

    # ── SEPA ──
    with tab_sepa:
        sub_t1, sub_t2 = st.tabs(["SEPA Results", "Pattern Setups"])
        for sub_tab, sheet, filters, title in [
            (sub_t1, "SEPA Results", SEPA_RESULTS_FILTERS, "SEPA Results"),
            (sub_t2, "Pattern Setups", SEPA_PATTERN_FILTERS, "Pattern Setups"),
        ]:
            with sub_tab:
                df = sepa.get(sheet, pd.DataFrame())
                if df.empty:
                    st.warning(f"{sheet} 無資料")
                    continue
                with st.sidebar:
                    st.markdown(f"### 篩選 · {title}")
                    pcol = _price_col(df)
                    vals = {}
                    if pcol:
                        v = _slider(df, pcol, ">=", f"sepa_{sheet}_price")
                        if v is not None:
                            vals[pcol] = (">=", v)
                    st.markdown("**條件**")
                    for col, op in filters:
                        v = _slider(df, col, op, f"sepa_{sheet}_{col}")
                        if v is not None:
                            vals[col] = (op, v)
                filtered = df.copy()
                for col, (op, v) in vals.items():
                    filtered = _apply_filter(filtered, col, op, v)
                _render_table(filtered, title)
