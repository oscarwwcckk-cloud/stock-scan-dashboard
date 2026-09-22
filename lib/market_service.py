# -*- coding: utf-8 -*-
"""市場狀況服務層:把移植的 fetcher + compute 包進 @st.cache_data(ttl=3600)。

所有函式 try/except 回 None/空,讓頁面能優雅降級(雲端 egress 被擋、yfinance 限流
都不致崩潰)。雲端 Streamlit container 會 sleep,所以 TTL 1h 平衡新鮮度與資源。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from lib import market_analysis, rs_engine, sector_map, finviz_scraper, yfinance_fetcher
from lib.sector_map import SECTOR_MAP, INDEX_TICKERS

# 指數 ticker → 友善鍵
INDEX_TICKS = INDEX_TICKERS  # {"^GSPC":"SPX","^NDX":"NDX","^DJI":"DJI"}
VIX_TICK = "^VIX"

# 類股成分股分組:依 benchmark(QQQ/SPY)分桶,各桶一次 yf.download
# (SECTOR_MAP 的 traditional 類股 constituents 可能為空,靠 universe + assign_sector 補)
_SECTOR_PERIOD = "14mo"


def _safe_close(ticker: str, period: str = _SECTOR_PERIOD) -> pd.Series | None:
    try:
        d = yfinance_fetcher.fetch_closes_batch([ticker], period=period)
        return d.get(ticker)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def index_health() -> dict:
    """三指數(SPX/NDX/DJI)技術健康度 + VIX。回傳 {key: {result: MarketAnalysisResult, vix: float}}。
    任一指數抓失敗就略過,不影響其他。"""
    out: dict[str, dict] = {}
    # 一次抓三指數 + VIX 的 OHLCV
    ticks = list(INDEX_TICKS.keys()) + [VIX_TICK]
    try:
        closes, vols = yfinance_fetcher.fetch_ohlcv_batch(ticks, period=_SECTOR_PERIOD)
    except Exception:
        closes, vols = {}, {}
    vix_close = closes.get(VIX_TICK)
    vix_level = float(vix_close.iloc[-1]) if vix_close is not None and len(vix_close) else None
    for tkr, key in INDEX_TICKS.items():
        c = closes.get(tkr)
        v = vols.get(tkr)
        if c is None or len(c) < 2:
            out[key] = None
            continue
        try:
            r = market_analysis.compute(key, tkr, c, v)
            out[key] = {"result": r, "vix": vix_level, "close": c}
        except Exception:
            out[key] = None
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def sector_rotation() -> list[dict]:
    """18 類股 RS 排名。回傳 list[dict] 已按 rs_rating desc 排序,
    每項 {key, name, benchmark, rs_rating, rs_score, rs_1d, rs_5d, rs_20d, rs_63d, n}。
    抓不到就回 []。"""
    try:
        # 收集各類股成分股,依 benchmark 分桶
        buckets: dict[str, dict[str, list[str]]] = {}  # benchmark -> {sector_key: [tickers]}
        for skey, info in SECTOR_MAP.items():
            bench = info.get("benchmark", "SPY")
            cons = info.get("constituents") or []
            buckets.setdefault(bench, {})[skey] = list(cons)
        # SPY 桶補 traditional 類股的 universe 成分(assign_sector 太慢,這裡只用顯式 constituents)
        rows: list[dict] = []
        for bench, sec2tick in buckets.items():
            all_tickers = sorted({t for ts in sec2tick.values() for t in ts})
            if not all_tickers:
                continue
            closes = yfinance_fetcher.fetch_closes_batch(all_tickers, period=_SECTOR_PERIOD)
            bench_close = closes.get(bench)
            if bench_close is None:
                # 補抓 benchmark
                bench_close = _safe_close(bench)
            if bench_close is None:
                continue
            # SPX score 用 SPY 近似(指數 ^GSPC 抓得到更好,但 SPY 已足夠相對比較)
            spx_score = rs_engine.weighted_return(bench_close) if bench_close is not None else None
            for skey, cons in sec2tick.items():
                cons_closes = {t: closes[t] for t in cons if t in closes}
                if not cons_closes:
                    continue
                rating = rs_engine.sector_rs_rating(cons_closes, spx_score)
                metrics = rs_engine.sector_rs_metrics(cons_closes, bench_close)
                info = SECTOR_MAP[skey]
                rows.append({
                    "key": skey,
                    "name": info.get("name", skey),
                    "group": info.get("group", ""),
                    "benchmark": bench,
                    "rs_rating": rating,
                    "rs_score": metrics.get("rs_score") if metrics else None,
                    "rs_1d": metrics.get("rs_1d") if metrics else None,
                    "rs_5d": metrics.get("rs_5d") if metrics else None,
                    "rs_20d": metrics.get("rs_20d") if metrics else None,
                    "rs_63d": metrics.get("rs_63d") if metrics else None,
                    "n": len(cons_closes),
                })
        rows.sort(key=lambda r: (r["rs_rating"] or 0), reverse=True)
        return rows
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def market_breadth() -> dict:
    """Finviz 市場廣度。失敗回 _empty_result()(全 None pct),頁面據此顯示 warning。"""
    try:
        return finviz_scraper.fetch_market_breadth()
    except Exception:
        return finviz_scraper._empty_result()


def breadth_available(bd: dict) -> bool:
    """判斷廣度是否有真實數字(雲端 egress 被擋時全 None)。"""
    if not bd:
        return False
    return any(bd.get(k, {}).get("pct") is not None
               for k in ("advancing", "declining", "new_high", "above_sma50", "above_sma200"))
