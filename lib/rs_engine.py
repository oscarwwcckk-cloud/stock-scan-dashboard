"""
RS calculation engine.
weighted_return() is a faithful port of Fred6724's RS Rating indicator (Pine Script v5).
Sector composite RS extends it to group-level excess-return scoring.

Fred6724 source: https://www.tradingview.com/script/xYIOcQFQ-RS-Rating/
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RS_WEIGHTS = {"3mo": 0.40, "6mo": 0.20, "9mo": 0.20, "12mo": 0.20}
PERIODS = {"3mo": 63, "6mo": 126, "9mo": 189, "12mo": 252}

# ── Fred6724 percentile curve constants (replay-mode approximation) ───────────
# totalRsScore values at percentile boundaries 99/90/70/50/30/10/1
_T = {
    "first": 195.93,  # ~99th percentile
    "scnd":  117.11,  # ~90th
    "thrd":   99.04,  # ~70th  (≈100 = in line with market)
    "frth":   91.66,  # ~50th
    "ffth":   80.96,  # ~30th
    "sxth":   53.64,  # ~10th
    "svth":   24.86,  # ~1st
}


# ── Stock-level RS — Fred6724 method ─────────────────────────────────────────

def weighted_return(close: pd.Series) -> float:
    """
    Weighted composite price-ratio score (most recent last).
    40% 3mo + 20% 6mo + 20% 9mo + 20% 12mo.
    Mirrors stock-scanner/criteria/rs_rating.py _weighted_score() exactly.
    Returns nan if < 63 bars; shorter windows substitute for longer ones.
    """
    n = len(close)
    if n < 63:
        return float("nan")

    def ratio(days: int) -> float:
        start = float(close.iloc[-days])
        end = float(close.iloc[-1])
        return end / start if start > 0 else float("nan")

    r3  = ratio(63)
    r6  = ratio(126) if n >= 126 else r3
    r9  = ratio(189) if n >= 189 else r6
    r12 = ratio(252) if n >= 252 else r9
    if any(np.isnan(v) for v in (r3, r6, r9, r12)):
        return float("nan")
    return 0.4 * r3 + 0.2 * r6 + 0.2 * r9 + 0.2 * r12


def _f_attribute_percentile(score, taller, smaller, range_up, range_dn, weight):
    """Port of Pine Script f_attributePercentile() — piecewise linear interpolation."""
    s = score + (score - smaller) * weight
    if s > taller - 1:
        s = taller - 1
    k1 = smaller / range_dn
    k2 = (taller - 1) / range_up
    k3 = (k1 - k2) / (taller - 1 - smaller)
    denom = k1 - k3 * (score - smaller)
    if denom == 0:
        return float(range_dn)
    return max(float(range_dn), min(float(range_up), s / denom))


def _score_to_rating(score: float) -> int:
    """Map totalRsScore → RS Rating 1-99 via Fred6724's 7-segment percentile curve."""
    if score >= _T["first"]: return 99
    if score <= _T["svth"]:  return 1
    if   score >= _T["scnd"]: r = _f_attribute_percentile(score, _T["first"], _T["scnd"], 98, 90, 0.33)
    elif score >= _T["thrd"]: r = _f_attribute_percentile(score, _T["scnd"],  _T["thrd"], 89, 70, 2.1)
    elif score >= _T["frth"]: r = _f_attribute_percentile(score, _T["thrd"],  _T["frth"], 69, 50, 0)
    elif score >= _T["ffth"]: r = _f_attribute_percentile(score, _T["frth"],  _T["ffth"], 49, 30, 0)
    elif score >= _T["sxth"]: r = _f_attribute_percentile(score, _T["ffth"],  _T["sxth"], 29, 10, 0)
    else:                     r = _f_attribute_percentile(score, _T["sxth"],  _T["svth"],  9,  2, 0)
    return max(1, min(99, int(round(r))))


def rank_scores(scores: dict[str, float], spx_score: float = None) -> dict[str, int]:
    """
    Convert weighted price-ratio scores → RS Rating 1-99.

    With spx_score: normalises each stock's score against SPX then applies
    Fred6724's 7-segment percentile curve (ratings comparable to IBD RS).
    Without: falls back to pool-relative percentile rank.
    """
    if not scores:
        return {}

    use_spx = spx_score is not None and not np.isnan(spx_score) and spx_score > 0
    if use_spx:
        return {k: _score_to_rating(v / spx_score * 100) for k, v in scores.items()}

    # Fallback: relative percentile rank within the pool
    series = pd.Series(scores)
    ranks = series.rank(pct=True) * 99
    return {k: max(1, min(99, int(round(v)))) for k, v in ranks.items()}


# ── Sector composite RS ───────────────────────────────────────────────────────

def _period_return(close: pd.Series, days: int) -> float:
    """% return over `days` bars. Returns nan if insufficient data."""
    n = len(close)
    if n < days:
        return float("nan")
    start = float(close.iloc[-days])
    end = float(close.iloc[-1])
    if start <= 0:
        return float("nan")
    return (end - start) / start * 100


def sector_composite_returns(
    constituent_closes: dict[str, pd.Series],
) -> dict[str, float]:
    """
    Equal-weighted average % return for each lookback period across constituents.
    Returns dict: period_key -> avg_return (nan if no constituents qualify).
    """
    results = {}
    for key, days in PERIODS.items():
        rets = [
            _period_return(s, days)
            for s in constituent_closes.values()
            if not np.isnan(_period_return(s, days))
        ]
        results[key] = float(np.mean(rets)) if rets else float("nan")
    return results


def sector_rs_rating(
    constituent_closes: dict[str, pd.Series],
    spx_score: Optional[float],
) -> Optional[int]:
    """
    板塊 RS Rating（1-99），vs SPX，採 Fred6724 RS Rating 指標方法。
    等權綜合：對各成分股各自算 weighted_return（40/20/20/20 加權價格比），取平均，
    再 normalise against SPX（avg / spx_score * 100）後套 7 段百分位曲線 → 1-99。
    與個股 rank_scores(..., spx_score) / ETF rs_rating 同一基準，板塊間可直接比較。
    """
    if not constituent_closes or spx_score is None or np.isnan(spx_score) or spx_score <= 0:
        return None
    scores = [weighted_return(s) for s in constituent_closes.values()]
    scores = [v for v in scores if not np.isnan(v)]
    if not scores:
        return None
    avg = float(np.mean(scores))
    return _score_to_rating(avg / spx_score * 100)


def sector_rs_metrics(
    constituent_closes: dict[str, pd.Series],
    benchmark_close: pd.Series,
) -> dict:
    """
    Compute sector RS vs benchmark.
    rs_score = same 40/20/20/20 weighted formula applied to excess returns.
    rs_Nd = sector return minus benchmark return for that period (excess return %).
    Returns dict with: rs_score, rs_10d, rs_30d, rs_60d.
    """
    sect = sector_composite_returns(constituent_closes)
    bench = {k: _period_return(benchmark_close, d) for k, d in PERIODS.items()}

    # Excess returns per period
    excess: dict[str, float] = {}
    for key in PERIODS:
        s, b = sect[key], bench[key]
        excess[key] = s - b if not (np.isnan(s) or np.isnan(b)) else float("nan")

    parts = [
        RS_WEIGHTS["3mo"]  * excess["3mo"],
        RS_WEIGHTS["6mo"]  * excess["6mo"],
        RS_WEIGHTS["9mo"]  * excess["9mo"],
        RS_WEIGHTS["12mo"] * excess["12mo"],
    ]
    rs_score = sum(parts) if not any(np.isnan(p) for p in parts) else float("nan")

    # Short-term excess (1d, 5d, 20d) — separate from the main score
    def excess_n(days: int) -> Optional[float]:
        s = _period_return(next(iter(constituent_closes.values()), benchmark_close), days)
        b = _period_return(benchmark_close, days)
        # Use sector composite for short periods
        rets = [_period_return(c, days) for c in constituent_closes.values()
                if not np.isnan(_period_return(c, days))]
        s_avg = float(np.mean(rets)) if rets else float("nan")
        return round(s_avg - b, 2) if not (np.isnan(s_avg) or np.isnan(b)) else None

    return {
        "rs_score":  round(rs_score, 2) if not np.isnan(rs_score) else None,
        "rs_10d":    excess_n(10),
        "rs_30d":    excess_n(30),
        "rs_60d":    excess_n(60),
    }


# ── RS history ratios ─────────────────────────────────────────────────────────

def compute_rs_history(
    stock_close: pd.Series,
    benchmark_close: pd.Series,
    lookback: int = 252,
) -> pd.Series:
    """
    Compute rolling RS ratio = stock_close / benchmark_close, aligned on common dates.
    Returned series has DatetimeIndex and float values (raw ratio, not normalized).
    Frontend normalizes to 100 at start of window.
    """
    aligned = pd.concat(
        [stock_close.rename("stock"), benchmark_close.rename("bench")], axis=1
    ).dropna()

    if len(aligned) < 10:
        return pd.Series(dtype=float)

    aligned = aligned.tail(lookback)
    ratio = aligned["stock"] / aligned["bench"]
    return ratio
