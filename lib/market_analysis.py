"""
Market Analysis Engine for US major indices (SPX, NDX, DJI).
Computes daily technical indicators and trend classification (J.Law TTT 2.0 aligned).
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class MarketAnalysisResult:
    index_key: str
    ticker: str
    price: float
    change_pct: float
    # Moving averages
    ma20: Optional[float]
    ma50: Optional[float]
    ma200: Optional[float]
    pct_from_ma20: Optional[float]
    pct_from_ma50: Optional[float]
    pct_from_ma200: Optional[float]
    above_ma20: Optional[int]   # 1/0
    above_ma50: Optional[int]
    above_ma200: Optional[int]
    # Momentum
    rsi14: Optional[float]
    macd_line: Optional[float]
    macd_signal: Optional[float]
    macd_hist: Optional[float]
    # Volume
    volume: Optional[float]
    vol_avg50: Optional[float]
    vol_ratio: Optional[float]
    # 52-week range
    high_52w: Optional[float]
    low_52w: Optional[float]
    pct_from_52w_high: Optional[float]
    pct_from_52w_low: Optional[float]
    # Distribution days (last 25 sessions, price down ≥0.2% on above-avg volume)
    dist_days: int
    # Short-term performance
    change_5d: Optional[float]
    change_20d: Optional[float]
    change_63d: Optional[float]
    # Classification
    trend_state: str
    market_signal: str


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = avg_gain.iloc[-1] / last_loss
    return float(100 - (100 / (1 + rs)))


def _macd(close: pd.Series) -> tuple[float, float, float]:
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    line = ema12 - ema26
    signal = _ema(line, 9)
    hist = line - signal
    return float(line.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])


def _distribution_days(close: pd.Series, volume: pd.Series, window: int = 25) -> int:
    """
    Count days where price fell ≥0.2% on volume above its 50-day average.
    Classic IBD/J.Law distribution day definition.
    """
    if len(close) < 51 or len(volume) < 51:
        return 0

    vol_ma50 = volume.rolling(50).mean()
    count = 0
    # Only look at the most recent `window` sessions
    for i in range(max(1, len(close) - window), len(close)):
        if pd.isna(vol_ma50.iloc[i]) or vol_ma50.iloc[i] == 0:
            continue
        day_chg = (close.iloc[i] / close.iloc[i - 1] - 1) * 100
        vol_vs_avg = volume.iloc[i] / vol_ma50.iloc[i]
        if day_chg <= -0.2 and vol_vs_avg > 1.0:
            count += 1
    return count


def _classify_trend(
    price: float,
    ma50: Optional[float],
    ma200: Optional[float],
    dist_days: int,
) -> tuple[str, str]:
    if ma50 is None or ma200 is None:
        return "Insufficient Data", "Not enough history to classify trend"

    above_50 = price > ma50
    above_200 = price > ma200
    ma50_above_200 = ma50 > ma200

    if above_50 and above_200 and ma50_above_200:
        if dist_days >= 6:
            return (
                "Uptrend Under Pressure",
                f"Bull market structure intact but {dist_days} distribution days — handle with care",
            )
        return (
            "Confirmed Uptrend",
            "Price above MA50 > MA200. Healthy bull market — follow the trend.",
        )
    elif not above_50 and above_200 and ma50_above_200:
        return (
            "Market in Correction",
            "Price pulled below MA50 but remains above MA200. Wait for base to form.",
        )
    elif above_50 and above_200 and not ma50_above_200:
        return (
            "Recovery Attempt",
            "Price above MA50 but MA50 < MA200 (death cross zone). Needs follow-through day.",
        )
    elif not above_50 and not above_200 and ma50_above_200:
        return (
            "Market in Correction",
            "Significant pullback. Price below both MAs. Watch MA200 as support.",
        )
    else:
        return (
            "Bear Market",
            "Price and MA50 both below MA200. Capital preservation mode.",
        )


def compute(
    index_key: str,
    ticker: str,
    close: pd.Series,
    volume: Optional[pd.Series] = None,
) -> MarketAnalysisResult:
    close = close.dropna().sort_index()
    if volume is not None:
        volume = volume.reindex(close.index).fillna(0)

    if len(close) < 2:
        raise ValueError(f"Insufficient price data for {ticker}")

    price = float(close.iloc[-1])
    change_pct = (price / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0.0

    def _ma(n: int) -> Optional[float]:
        if len(close) >= n:
            return float(close.rolling(n).mean().iloc[-1])
        return None

    ma20 = _ma(20)
    ma50 = _ma(50)
    ma200 = _ma(200)

    pct_from_ma20 = ((price / ma20) - 1) * 100 if ma20 else None
    pct_from_ma50 = ((price / ma50) - 1) * 100 if ma50 else None
    pct_from_ma200 = ((price / ma200) - 1) * 100 if ma200 else None
    above_ma20 = int(price > ma20) if ma20 is not None else None
    above_ma50 = int(price > ma50) if ma50 is not None else None
    above_ma200 = int(price > ma200) if ma200 is not None else None

    rsi14 = _rsi(close, 14)

    macd_line = macd_sig = macd_hist = None
    if len(close) >= 35:
        macd_line, macd_sig, macd_hist = _macd(close)

    vol_now = vol_avg50 = vol_ratio = None
    if volume is not None and len(volume) >= 1:
        vol_now = float(volume.iloc[-1])
        if len(volume) >= 50:
            avg = float(volume.rolling(50).mean().iloc[-1])
            if avg > 0:
                vol_avg50 = avg
                vol_ratio = vol_now / avg

    lookback = min(len(close), 252)
    period_close = close.iloc[-lookback:]
    high_52w = float(period_close.max())
    low_52w = float(period_close.min())
    pct_from_52w_high = (price / high_52w - 1) * 100 if high_52w else None
    pct_from_52w_low = (price / low_52w - 1) * 100 if low_52w else None

    dist_days = 0
    if volume is not None:
        dist_days = _distribution_days(close, volume, window=25)

    change_5d = ((price / float(close.iloc[-6])) - 1) * 100 if len(close) >= 6 else None
    change_20d = ((price / float(close.iloc[-21])) - 1) * 100 if len(close) >= 21 else None
    change_63d = ((price / float(close.iloc[-64])) - 1) * 100 if len(close) >= 64 else None

    trend_state, market_signal = _classify_trend(price, ma50, ma200, dist_days)

    def _r(v, d=2):
        return round(v, d) if v is not None and not np.isnan(v) else None

    return MarketAnalysisResult(
        index_key=index_key,
        ticker=ticker,
        price=_r(price),
        change_pct=_r(change_pct),
        ma20=_r(ma20),
        ma50=_r(ma50),
        ma200=_r(ma200),
        pct_from_ma20=_r(pct_from_ma20),
        pct_from_ma50=_r(pct_from_ma50),
        pct_from_ma200=_r(pct_from_ma200),
        above_ma20=above_ma20,
        above_ma50=above_ma50,
        above_ma200=above_ma200,
        rsi14=_r(rsi14, 1),
        macd_line=_r(macd_line),
        macd_signal=_r(macd_sig),
        macd_hist=_r(macd_hist),
        volume=vol_now,
        vol_avg50=_r(vol_avg50),
        vol_ratio=_r(vol_ratio),
        high_52w=_r(high_52w),
        low_52w=_r(low_52w),
        pct_from_52w_high=_r(pct_from_52w_high),
        pct_from_52w_low=_r(pct_from_52w_low),
        dist_days=dist_days,
        change_5d=_r(change_5d),
        change_20d=_r(change_20d),
        change_63d=_r(change_63d),
        trend_state=trend_state,
        market_signal=market_signal,
    )
