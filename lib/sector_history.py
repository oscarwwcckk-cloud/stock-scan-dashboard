# -*- coding: utf-8 -*-
"""板塊 RS 歷史折線圖資料層。

sector_rs_history(period) 回各板塊「相對基準的強弱比值」時間序列(正規化 100 起點),
供板塊分析頁畫折線圖:線往上=跑贏基準、往下=落後。

演算法(板塊層級,延伸自 rs_engine.compute_rs_history 個股層級):
  板塊等權序列 = pd.concat(成分股收盤, axis=1).mean(axis=1)  # 自動對齊共同日期、缺股不影響
  比值歷史      = compute_rs_history(等權序列, 基準序列, lookback)  # 對齊+比值
  正規化 100    = ratio / ratio.iloc[0] * 100

18 板塊各一條線。tech 板塊 vs QQQ、traditional 板塊 vs SPY,各自起點 100 → 跨板塊
比的是「相對各自基準的超額 %」,可比。3m/6m/1y 從同一條 16mo 長序列切片。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from lib import rs_engine, yfinance_fetcher, holdings_fetcher
from lib.sector_map import SECTOR_MAP

# 抓 16mo 歷史:1y 窗需 252 交易日 + 等權對齊損失,16mo 保險;3m/6m 從長序列 tail 切片。
_HIST_PERIOD = "16mo"
_LOOKBACK = {"3m": 63, "6m": 126, "1y": 252}


@st.cache_data(ttl=3600, show_spinner=False)
def sector_rs_history(period: str = "6m") -> dict:
    """各板塊相對基準的強弱比值歷史(正規化 100 起點)。

    period ∈ {"3m","6m","1y"} → lookback 交易日。回 {sector_key: {name, benchmark, series}}。
    series: pd.Series(DatetimeIndex, float),值=板塊等權指數/基準 ×100/首值。
    抓失敗/某板塊無資料 → 該板塊略過;整體失敗回 {}(頁面降級 warning)。
    """
    lookback = _LOOKBACK.get(period, 126)
    try:
        # 依 benchmark 分桶(邏輯照搬 market_service.sector_rotation)
        buckets: dict[str, dict[str, list[str]]] = {}
        for skey, info in SECTOR_MAP.items():
            bench = info.get("benchmark", "SPY")
            cons = list(info.get("constituents") or [])
            if not cons and info.get("etf"):
                cons = holdings_fetcher.fetch_spdr_holdings(info["etf"])
            buckets.setdefault(bench, {})[skey] = cons

        out: dict[str, dict] = {}
        for bench, sec2tick in buckets.items():
            all_tickers = sorted({t for ts in sec2tick.values() for t in ts})
            if not all_tickers:
                continue
            closes = yfinance_fetcher.fetch_closes_batch(all_tickers + [bench],
                                                          period=_HIST_PERIOD)
            bench_close = closes.get(bench)
            if bench_close is None or len(bench_close) < lookback:
                continue
            for skey, cons in sec2tick.items():
                cons_closes = {t: closes[t] for t in cons if t in closes}
                if len(cons_closes) < 3:  # 太少股算不出有意義的等權序列
                    continue
                eq = pd.concat(cons_closes, axis=1).mean(axis=1)
                ratio = rs_engine.compute_rs_history(eq, bench_close, lookback=lookback)
                if ratio is None or len(ratio) < 10:
                    continue
                norm = (ratio / float(ratio.iloc[0]) * 100).round(2)
                if norm.isna().all() or len(norm) < 10:
                    continue
                info = SECTOR_MAP[skey]
                out[skey] = {
                    "name": info.get("name", skey),
                    "benchmark": bench,
                    "group": info.get("group", ""),
                    "series": norm,  # DatetimeIndex, float(100 起點)
                    "latest": float(norm.iloc[-1]) if not np.isnan(norm.iloc[-1]) else None,
                }
        return out
    except Exception:
        return {}
