# -*- coding: utf-8 -*-
"""Fear & Greed 抓取器 —— 雲端 + 本機皆可即時抓。

優先序(任一成功即回):
  1. CNN dataviz JSON API(純 requests,雲端可用,免 JS engine)→ 最可靠
  2. 本機 playwright(fallback,API 被擋時才用)

CNN gauge 即時值原本要 JS render,但 dataviz.cnn.io 開放 JSON API 直接回 score+rating。
此前靠本機 playwright 抓 JSON 存盤 commit → 雲端讀舊檔,點 refresh 也只重讀舊檔;
改走 API 後雲端也能即時抓,🔄 按下三項(指數/廣度/F&G)全部新鮮。
"""
from __future__ import annotations

import datetime as dt

import requests

# CNN dataviz 開放 JSON API(實測:純 GET + UA 即回 score/rating,免 auth/JS)
CNN_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 20


def _normalize_rating(raw: str | None) -> str:
    """API 回 'fear'/'greed'/'extreme_fear'/'extreme_greed'/'neutral' → 友善名。"""
    t = (raw or "").lower().strip().replace(" ", "_")
    if "extreme_greed" in t:
        return "Extreme Greed"
    if "extreme_fear" in t:
        return "Extreme Fear"
    if "greed" in t:
        return "Greed"
    if "fear" in t:
        return "Fear"
    if "neutral" in t:
        return "Neutral"
    return "?"


def _fetch_api() -> dict | None:
    """走 CNN dataviz JSON API。失敗回 None。"""
    try:
        r = requests.get(CNN_API_URL, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    fg = (data or {}).get("fear_and_greed") or {}
    score = fg.get("score")
    rating = fg.get("rating")
    if score is None and not rating:
        return None
    val = None
    if score is not None:
        try:
            val = round(float(score))
        except (TypeError, ValueError):
            val = None
    return {
        "value": val,
        "rating": _normalize_rating(rating),
        "index_label": rating,
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "CNN Fear & Greed (dataviz API)",
    }


def _fetch_playwright() -> dict | None:
    """本機 playwright fallback(解 API 角度等較舊呈現,或 API 被擋時)。

    走 repo根的 fetch_feargreed.fetch();import 失敗(雲端沒 playwright)回 None。
    """
    try:
        import importlib
        mod = importlib.import_module("fetch_feargreed")
        return mod.fetch()
    except Exception:
        return None


def fetch_feargreed_live() -> dict:
    """即時抓 F&G。API 優先,playwright fallback;都失敗回含 error 的 dict。

    回 {value, rating, fetched_at, source, error?}。value 可能 None(抓失敗)。
    """
    res = _fetch_api()
    if res and res.get("value") is not None:
        return res
    # API 失敗或拿不到 value → 本機 playwright
    pw = _fetch_playwright()
    if pw and pw.get("value") is not None:
        return pw
    # 都失敗
    return {
        "value": None,
        "rating": None,
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "CNN Fear & Greed (all sources failed)",
        "error": "API and playwright both unavailable",
    }
