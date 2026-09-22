"""
J.Law TTT 2.0 形态识别引擎。
规则来源：J.Law-The18Rules.pdf, J.Law-TheTradingGuideline.pdf

买入名单条件（即将突破）：
  - tight_base: 整理幅度 < 10%（紧凑盘整）
  - vol_contracting: 整理期间量能递减（缩量蓄势）
  - within_buy_zone: 价格在轴心点上方 0-5%（买入区间）
  - rs_line_near_high: RS 线接近 52 周高点（领涨地位）
  - jlaw_score >= 3

观察名单条件（形态构建中）：
  - below_pivot: 价格仍低于轴心点（突破前）
  - tight_base: 整理紧凑
  - vol_contracting: 量能收缩
  - jlaw_score >= 2
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

# ── 阈值参数（与 stock-scanner config.py 一致）─────────────────────────────────
BASE_LOOKBACK = 20          # 回望交易日数（整理窗口）
MAX_BASE_AMPLITUDE = 10.0   # 整理幅度上限 %
PIVOT_LOOKBACK = 30         # 轴心点回望窗口（交易日）
PIVOT_MIN_AGE_DAYS = 5      # 轴心点最小有效日龄
MAX_CHASE_PCT = 5.0         # 轴心点以上最大追涨距离 %（Rule 8）
VOL_CONTRACTION_RATIO = 1.0 # 量能收缩比例阈值（近期/前期 < 1.0 为收缩）
RS_LINE_NEAR_HIGH_PCT = 5.0 # RS 线距 52 周高点的最大容忍距离 %


@dataclass
class JLawResult:
    # 整理质量
    base_amplitude: float    # 整理幅度 %（越小越紧凑）
    tight_base: bool         # 幅度 < 10%
    base_length: int         # 距上次触及轴心高点的交易日数

    # 量能
    vol_contracting: bool    # 量能递减
    vol_slope_ratio: float   # 近 10 日均量 / 前 10 日均量

    # 轴心点
    pivot_price: float       # 突破轴心价格
    pct_from_pivot: float    # 距轴心点 %（正=在上方，负=在下方）
    within_buy_zone: bool    # 在轴心点上方 0-5%（买入区间）
    below_pivot: bool        # 价格仍低于轴心点（形态构建中）

    # RS 线
    rs_line_near_high: bool       # RS 线在 52 周高点 5% 以内
    rs_line_pct_from_high: float  # RS 线距 52 周高点 %

    # 综合评分 0-4
    jlaw_score: int


def compute(
    close: pd.Series,
    volume: pd.Series,
    spy_close: pd.Series | None = None,
) -> JLawResult:
    """
    计算 J.Law 形态指标。

    close: 日收盘价 Series（升序）
    volume: 日成交量 Series（升序，与 close 同长度）
    spy_close: SPY 收盘价 Series（用于计算 RS 线，可为 None）
    """
    close = close.astype(float)
    volume = volume.astype(float)

    # ── 整理幅度 ─────────────────────────────────────────────────────────────
    lookback = min(BASE_LOOKBACK, len(close))
    base_close = close.iloc[-lookback:]
    base_high = base_close.max()
    base_low = base_close.min()
    base_amplitude = ((base_high - base_low) / base_low * 100) if base_low > 0 else 999.0
    base_amplitude = round(base_amplitude, 1)
    tight_base = base_amplitude < MAX_BASE_AMPLITUDE

    # ── 量能收缩 ─────────────────────────────────────────────────────────────
    half = lookback // 2
    recent_vol_avg = volume.iloc[-half:].mean()
    prior_vol_avg = volume.iloc[-lookback:-half].mean() if len(volume) >= lookback else recent_vol_avg
    vol_slope_ratio = round(recent_vol_avg / prior_vol_avg, 2) if prior_vol_avg > 0 else 1.0
    vol_contracting = vol_slope_ratio < VOL_CONTRACTION_RATIO

    # ── 轴心点计算 ───────────────────────────────────────────────────────────
    # 轴心点 = 满足条件的最高收盘价：
    #   1. 当日成交量 >= 50 日均量（机构参与）
    #   2. 至少 5 个交易日前（整理时间足够）
    pivot_lookback = min(PIVOT_LOOKBACK, len(close))
    vol_ma50 = volume.iloc[-50:].mean() if len(volume) >= 50 else volume.mean()

    recent_close = close.iloc[-pivot_lookback:]
    recent_vol = volume.iloc[-pivot_lookback:]

    min_age = PIVOT_MIN_AGE_DAYS
    aged_close = recent_close.iloc[:-min_age] if len(recent_close) > min_age else recent_close
    aged_vol = recent_vol.iloc[:-min_age] if len(recent_vol) > min_age else recent_vol

    high_vol_days = aged_close[aged_vol >= vol_ma50]
    pivot_price = float(high_vol_days.max() if not high_vol_days.empty else aged_close.max())

    # ── 整理长度 ─────────────────────────────────────────────────────────────
    above_mask = (close >= pivot_price).values
    if above_mask.any():
        last_above_pos = int(np.where(above_mask)[0][-1])
        base_length = len(close) - 1 - last_above_pos
    else:
        base_length = len(close)

    current_price = float(close.iloc[-1])
    pct_from_pivot = round(((current_price / pivot_price) - 1.0) * 100, 1)
    within_buy_zone = 0 <= pct_from_pivot <= MAX_CHASE_PCT
    below_pivot = pct_from_pivot < 0

    # ── RS 线距 52 周高点 ─────────────────────────────────────────────────────
    rs_line_near_high = False
    rs_line_pct_from_high = 0.0

    if spy_close is not None and len(spy_close) >= 50:
        try:
            stock_s = close.copy()
            stock_s.index = pd.to_datetime(stock_s.index)
            spy_s = spy_close.astype(float).copy()
            spy_s.index = pd.to_datetime(spy_s.index)

            aligned = pd.concat(
                [stock_s.rename("stock"), spy_s.rename("spy")], axis=1
            ).dropna()

            if len(aligned) >= 50:
                rs_line = aligned["stock"] / aligned["spy"]
                rs_current = float(rs_line.iloc[-1])
                rs_52wk = rs_line.iloc[-252:].max() if len(rs_line) >= 252 else rs_line.max()
                rs_line_pct_from_high = round(((rs_current / rs_52wk) - 1.0) * 100, 1)
                rs_line_near_high = rs_line_pct_from_high >= -RS_LINE_NEAR_HIGH_PCT
        except Exception:
            pass

    # ── J.Law 综合评分 ────────────────────────────────────────────────────────
    jlaw_score = int(sum([
        tight_base,
        vol_contracting,
        within_buy_zone,
        rs_line_near_high,
    ]))

    return JLawResult(
        base_amplitude=base_amplitude,
        tight_base=tight_base,
        base_length=base_length,
        vol_contracting=vol_contracting,
        vol_slope_ratio=vol_slope_ratio,
        pivot_price=pivot_price,
        pct_from_pivot=pct_from_pivot,
        within_buy_zone=within_buy_zone,
        below_pivot=below_pivot,
        rs_line_near_high=rs_line_near_high,
        rs_line_pct_from_high=rs_line_pct_from_high,
        jlaw_score=jlaw_score,
    )


# ── 名单筛选标准 ───────────────────────────────────────────────────────────────

def is_buy_candidate(result: JLawResult, rs_score: float) -> bool:
    """买入名单：即将突破，处于买入区间 0-5%"""
    return (
        result.within_buy_zone
        and result.tight_base
        and result.jlaw_score >= 3
        and rs_score >= 70
    )


def is_watch_candidate(result: JLawResult, rs_score: float) -> bool:
    """观察名单：形态构建中，尚未突破轴心点"""
    return (
        result.below_pivot
        and result.tight_base
        and result.vol_contracting
        and result.jlaw_score >= 2
        and rs_score >= 60
    )
