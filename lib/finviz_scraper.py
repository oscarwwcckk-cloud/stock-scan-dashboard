"""Scrape Finviz homepage for market breadth statistics.

HTML structure (4 × .market-stats divs):
  .market-stats_labels_left  → <p>Label</p><p>X.X% (N)</p>
  .market-stats_labels_right → <p>Label</p><p>(N) X.X%</p>
Identified by data-boxover-html attribute.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_URL = "https://finviz.com/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 20


def _parse_left(text: str) -> tuple[Optional[float], Optional[int]]:
    """Parse 'X.X% (N)' → (pct, count)."""
    m = re.search(r"([\d.]+)%\s*\((\d+)\)", text)
    if m:
        return float(m.group(1)), int(m.group(2))
    return None, None


def _parse_right(text: str) -> tuple[Optional[int], Optional[float]]:
    """Parse '(N) X.X%' → (count, pct)."""
    m = re.search(r"\((\d+)\)\s*([\d.]+)%", text)
    if m:
        return int(m.group(1)), float(m.group(2))
    return None, None


def _empty_result() -> dict:
    metric = {"pct": None, "count": None}
    return {
        "advancing": dict(metric), "declining": dict(metric),
        "new_high": dict(metric), "new_low": dict(metric),
        "above_sma50": dict(metric), "below_sma50": dict(metric),
        "above_sma200": dict(metric), "below_sma200": dict(metric),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_market_breadth() -> dict:
    """Return market breadth dict; returns empty metrics on any failure."""
    try:
        resp = requests.get(_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Finviz fetch failed: %s", exc)
        return _empty_result()

    soup = BeautifulSoup(resp.text, "lxml")
    stats_divs = soup.find_all("div", class_="market-stats")
    if not stats_divs:
        log.warning("market-stats divs not found on Finviz page")
        return _empty_result()

    # Map each div by its data-boxover-html content
    mapping = {}
    for div in stats_divs:
        label = div.get("data-boxover-html", "")
        left_div = div.find("div", class_="market-stats_labels_left")
        right_div = div.find("div", class_="market-stats_labels_right")
        if not left_div or not right_div:
            continue
        left_text = left_div.get_text(" ", strip=True)
        right_text = right_div.get_text(" ", strip=True)
        left_pct, left_cnt = _parse_left(left_text)
        right_cnt, right_pct = _parse_right(right_text)

        if "Advancing" in label or "Advancing" in left_text:
            mapping["adv_dec"] = (left_pct, left_cnt, right_cnt, right_pct)
        elif "High" in label or "New High" in left_text:
            mapping["hl"] = (left_pct, left_cnt, right_cnt, right_pct)
        elif "SMA50" in label:
            mapping["sma50"] = (left_pct, left_cnt, right_cnt, right_pct)
        elif "SMA200" in label:
            mapping["sma200"] = (left_pct, left_cnt, right_cnt, right_pct)

    result = _empty_result()
    result["fetched_at"] = datetime.now(timezone.utc).isoformat()

    if "adv_dec" in mapping:
        ap, ac, dc, dp = mapping["adv_dec"]
        result["advancing"] = {"pct": ap, "count": ac}
        result["declining"] = {"pct": dp, "count": dc}

    if "hl" in mapping:
        hp, hc, lc, lp = mapping["hl"]
        result["new_high"] = {"pct": hp, "count": hc}
        result["new_low"] = {"pct": lp, "count": lc}

    if "sma50" in mapping:
        ap, ac, bc, bp = mapping["sma50"]
        result["above_sma50"] = {"pct": ap, "count": ac}
        result["below_sma50"] = {"pct": bp, "count": bc}

    if "sma200" in mapping:
        ap, ac, bc, bp = mapping["sma200"]
        result["above_sma200"] = {"pct": ap, "count": ac}
        result["below_sma200"] = {"pct": bp, "count": bc}

    log.info(
        "Finviz breadth: Adv %s%% / Dec %s%% | NH %s%% | SMA50 Abv %s%% | SMA200 Abv %s%%",
        result["advancing"]["pct"], result["declining"]["pct"],
        result["new_high"]["pct"], result["above_sma50"]["pct"], result["above_sma200"]["pct"],
    )
    return result
