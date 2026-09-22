"""
Batch yfinance data fetcher.
Uses yf.download() to fetch all tickers in a single HTTP session.
"""
import logging
import time
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_closes_batch(
    tickers: list[str],
    period: str = "14mo",
) -> dict[str, pd.Series]:
    """
    Fetch adjusted close prices for all tickers in one yf.download() call.
    Returns dict: ticker -> pd.Series of daily closes (ascending date, no NaN).
    Only includes series with >= 63 bars (minimum for RS calculation).
    """
    if not tickers:
        return {}

    logger.info(f"Batch-fetching {len(tickers)} tickers ({period})...")
    try:
        data = yf.download(
            tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.error(f"yf.download failed: {e}")
        return {}

    result: dict[str, pd.Series] = {}

    if isinstance(data.columns, pd.MultiIndex):
        # Multi-ticker: columns are (field, ticker)
        if "Close" not in data.columns.get_level_values(0):
            logger.warning("No 'Close' field in multi-ticker download")
            return {}
        close_df = data["Close"]
        for ticker in tickers:
            if ticker in close_df.columns:
                s = close_df[ticker].dropna().sort_index()
                if len(s) >= 63:
                    result[ticker] = s
    else:
        # Single ticker
        if "Close" in data.columns and tickers:
            s = data["Close"].dropna().sort_index()
            if len(s) >= 63:
                result[tickers[0]] = s

    logger.info(f"Got usable close series for {len(result)}/{len(tickers)} tickers")
    return result


def fetch_ohlcv_batch(
    tickers: list[str],
    period: str = "14mo",
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """
    单次下载同时返回收盘价和成交量。
    Returns: (closes_dict, volumes_dict)
    两个 dict 中的 ticker 集合相同（至少 63 根 K 线）。
    """
    if not tickers:
        return {}, {}

    logger.info(f"Batch-fetching OHLCV for {len(tickers)} tickers ({period})...")
    try:
        data = yf.download(
            tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.error(f"yf.download (ohlcv) failed: {e}")
        return {}, {}

    closes: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}

    if isinstance(data.columns, pd.MultiIndex):
        close_df = data.get("Close")
        volume_df = data.get("Volume")
        if close_df is None:
            return {}, {}
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            c = close_df[ticker].dropna().sort_index()
            if len(c) < 63:
                continue
            closes[ticker] = c
            if volume_df is not None and ticker in volume_df.columns:
                v = volume_df[ticker].reindex(c.index).fillna(0)
                volumes[ticker] = v
    else:
        if "Close" in data.columns and tickers:
            c = data["Close"].dropna().sort_index()
            if len(c) >= 63:
                t = tickers[0]
                closes[t] = c
                if "Volume" in data.columns:
                    volumes[t] = data["Volume"].reindex(c.index).fillna(0)

    logger.info(f"Got OHLCV for {len(closes)}/{len(tickers)} tickers")
    return closes, volumes


def fetch_ohlc_batch(
    tickers: list[str],
    period: str = "14mo",
) -> dict[str, pd.DataFrame]:
    """
    單次下載回傳每檔完整 OHLCV，供 K 線圖用。
    Returns: dict ticker -> DataFrame（DatetimeIndex 升序，欄位 open/high/low/close/volume）。
    只保留 >= 63 根的序列。
    """
    if not tickers:
        return {}

    logger.info(f"Batch-fetching OHLC bars for {len(tickers)} tickers ({period})...")
    try:
        data = yf.download(
            tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.error(f"yf.download (ohlc bars) failed: {e}")
        return {}

    fields = ["Open", "High", "Low", "Close", "Volume"]
    result: dict[str, pd.DataFrame] = {}

    if isinstance(data.columns, pd.MultiIndex):
        lv0 = set(data.columns.get_level_values(0))
        if "Close" not in lv0:
            return {}
        close_df = data["Close"]
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            cols = {
                f.lower(): data[f][ticker]
                for f in fields
                if f in lv0 and ticker in data[f].columns
            }
            if "close" not in cols:
                continue
            df = pd.DataFrame(cols).dropna(subset=["close"]).sort_index()
            if len(df) >= 63:
                result[ticker] = df
    else:
        if "Close" in data.columns and tickers:
            df = pd.DataFrame({f.lower(): data[f] for f in fields if f in data.columns})
            if "close" in df.columns:
                df = df.dropna(subset=["close"]).sort_index()
                if len(df) >= 63:
                    result[tickers[0]] = df

    logger.info(f"Got OHLC bars for {len(result)}/{len(tickers)} tickers")
    return result


def fetch_stock_meta(ticker: str) -> Optional[dict]:
    """
    Fetch name, sector, industry for a single ticker via yfinance.
    Returns None on failure. Caller is responsible for rate-limiting.
    """
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
        }
    except Exception as e:
        logger.debug(f"fetch_stock_meta({ticker}) failed: {e}")
        return None


def fetch_stock_meta_batch(tickers: list[str], sleep_s: float = 0.1) -> dict[str, dict]:
    """
    Fetch name/sector/industry for multiple tickers sequentially.
    Returns dict: ticker -> {name, sector, industry}.
    """
    result = {}
    for i, ticker in enumerate(tickers):
        meta = fetch_stock_meta(ticker)
        if meta:
            result[ticker] = meta
        if i % 50 == 0 and i > 0:
            logger.info(f"  Meta fetched {i}/{len(tickers)}")
        time.sleep(sleep_s)
    return result
