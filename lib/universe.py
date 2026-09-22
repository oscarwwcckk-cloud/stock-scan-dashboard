"""
Stock universe: S&P 500 + NASDAQ 100 tickers.
Fetched from Wikipedia; cached in memory for the process lifetime.
"""
import logging
import pandas as pd
from lib.sector_map import EXPLICIT_TICKER_MAP

logger = logging.getLogger(__name__)

_cached_universe: list[str] | None = None


def get_universe() -> list[str]:
    global _cached_universe
    if _cached_universe is not None:
        return _cached_universe

    tickers: set[str] = set()

    _ua = {"User-Agent": "Mozilla/5.0 (compatible; stock-dashboard/1.0)"}

    # S&P 500
    try:
        sp500 = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            storage_options=_ua,
        )[0]
        tickers.update(sp500["Symbol"].str.replace(".", "-", regex=False).tolist())
        logger.info(f"SP500: {len(sp500)} tickers")
    except Exception as e:
        logger.warning(f"SP500 fetch failed: {e}")

    # NASDAQ 100
    try:
        ndx = pd.read_html(
            "https://en.wikipedia.org/wiki/Nasdaq-100",
            storage_options=_ua,
        )[4]
        col = "Ticker" if "Ticker" in ndx.columns else ndx.columns[1]
        tickers.update(ndx[col].dropna().str.strip().tolist())
        logger.info(f"NDX100 added, total so far: {len(tickers)}")
    except Exception as e:
        logger.warning(f"NDX100 fetch failed: {e}")

    # Always include explicit sector map constituents
    tickers.update(EXPLICIT_TICKER_MAP.keys())

    # Remove known bad tickers / duplicates
    tickers.discard("")
    tickers.discard("nan")

    _cached_universe = sorted(tickers)
    logger.info(f"Universe: {len(_cached_universe)} unique tickers")
    return _cached_universe


def invalidate_cache() -> None:
    global _cached_universe
    _cached_universe = None
