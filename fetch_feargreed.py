# -*- coding: utf-8 -*-
"""fetch_feargreed.py ── 本機用 playwright 抓 CNN Fear & Greed,存進 data/feargreed.json。

CNN F&G 即時值要 JS render,Streamlit Cloud 沒 JS engine → 本機抓完存 JSON,
push_scanner_data.py chain 進來 commit+push,雲端 dashboard 讀 JSON。

CNN gauge 沒有純文字當前值,從兩處推導:
  - market-fng-gauge__hand 的 SVG transform: rotate(Xdeg) → 角度反推 0-100
    (半圓:0 Extreme Fear 左,-90deg ↔ 100 Extreme Greed 右,+90deg)
    value = round((X + 90) / 180 * 100)
  - "Fear/Greed is driving the US market" 句 → rating 分類

執行(本機,需 playwright + chromium):
    python fetch_feargreed.py
"""
import json
import re
import datetime as dt
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "feargreed.json")
CNN_URL = "https://edition.cnn.com/markets/fear-and-greed"

# 抓頁面所有可見文字中跟 F&G rating 有關的訊息 —— 多重 fallback,任一命中即可
EVAL_JS = """() => {
  const out = {};
  // 1) 指針旋轉角度:試多組 hand 選擇器
  const handSelectors = [
    '[class*=market-fng-gauge__hand] svg',
    '[class*=gauge__hand] svg',
    '[class*=fng-gauge__hand] svg',
    '[class*=FearGreedGauge] [class*=hand] svg',
    '[class*=gauge] [class*=hand]',
    'svg [class*=hand]',
  ];
  for (const sel of handSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const s = el.getAttribute('style') || '';
      const m = s.match(/rotate\\((-?\\d+\\.?\\d*)\\s*deg\\)/);
      if (m) { out.hand_rotate = parseFloat(m[1]); break; }
      // 有些版本 transform 在子元素或 transform 屬性
      const ta = el.getAttribute('transform') || '';
      const m2 = ta.match(/rotate\\((-?\\d+(?:\\.\\d+)?)\\)/);
      if (m2) { out.hand_rotate = parseFloat(m2[1]); break; }
    }
  }
  // 2) "X is driving the market" 句 + 任何含 fear/greed/neutral 的可見文字
  const seen = new Set();
  const texts = [];
  document.querySelectorAll('div, span, p, h1, h2, h3').forEach(el => {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 200 || seen.has(t)) return;
    if (/driving|fear|greed|neutral|extreme/i.test(t)) {
      seen.add(t);
      texts.push(t);
    }
  });
  out.candidate_texts = texts.slice(0, 20);
  // 3) data-index-label(fear/greed/neutral...)——試多組 meter 選擇器
  const meterSelectors = [
    '[class*=market-fng-gauge__meter]',
    '[class*=gauge__meter]',
    '[class*=FearGreedGauge] [class*=meter]',
    '[data-index-label]',
  ];
  for (const sel of meterSelectors) {
    const el = document.querySelector(sel);
    if (el && el.getAttribute('data-index-label')) {
      out.index_label = el.getAttribute('data-index-label');
      break;
    }
  }
  // 4) gauge 區 rating 文字
  const catSelectors = ['[class*=gauge__category]', '[class*=gauge__rating]', '[class*=FearGreedGauge] [class*=category]'];
  for (const sel of catSelectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim()) { out.rating_text = el.innerText.trim(); break; }
  }
  return out;
}"""


def _rating_from_driving(text):
    """CNN 句型固定:'[Rating] is driving the US market'。
    抓 'is driving' 前一個 token,而不是整句(整句含 'Fear & Greed Index' 會誤判)。
    實測頁面 DOM 把空白吃掉成 'Fearis driving',故用正則容忍。"""
    if not text:
        return "?"
    t = text.lower()
    # 抓 "...XXXis driving..." 或 "...XXX is driving..." 前綴
    m = re.search(r'([a-z][a-z\s]*?)\s*is\s+driving', t)
    tail = m.group(1).strip() if m else ""
    if "extreme greed" in tail:
        return "Extreme Greed"
    if "extreme fear" in tail:
        return "Extreme Fear"
    if "greed" in tail:
        return "Greed"
    if "fear" in tail:
        return "Fear"
    if "neutral" in tail:
        return "Neutral"
    return "?"


def _rating_from_label(label):
    """index_label=fear/greed/neutral/extreme-fear/extreme-greed 直推。"""
    t = (label or "").lower()
    if "extreme greed" in t or "extreme-greed" in t:
        return "Extreme Greed"
    if "extreme fear" in t or "extreme-fear" in t:
        return "Extreme Fear"
    if "greed" in t:
        return "Greed"
    if "fear" in t:
        return "Fear"
    if "neutral" in t:
        return "Neutral"
    return "?"


def fetch() -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(CNN_URL, timeout=60000, wait_until="domcontentloaded")
        pg.wait_for_timeout(12000)  # 等 JS render gauge 指針
        data = pg.evaluate(EVAL_JS)
        b.close()

    # 從指針角度反推 0-100
    angle = data.get("hand_rotate")
    value = None
    if angle is not None:
        value = round((angle + 90) / 180 * 100)
        value = max(0, min(100, value))

    # rating:精準源優先 —— driving 句裡 "is driving" 前綴 > index_label
    texts = data.get("candidate_texts") or []
    driving = next((t for t in texts if "driving" in t.lower()), None)
    rating = "?"
    if driving:
        rating = _rating_from_driving(driving)
    if rating == "?" and data.get("index_label"):
        rating = _rating_from_label(data["index_label"])
    if rating == "?" and data.get("rating_text"):
        rating = _rating_from_label(data["rating_text"])

    # value 若沒抓到角度,試從 rating 反推中點
    if value is None and rating != "?":
        value = {"Extreme Fear": 10, "Fear": 30, "Neutral": 50,
                 "Greed": 70, "Extreme Greed": 90}.get(rating)

    return {
        "value": value,
        "rating": rating,
        "driving_text": driving,
        "index_label": data.get("index_label"),
        "rating_text": data.get("rating_text"),
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "CNN Fear & Greed (playwright)",
    }


def main():
    try:
        result = fetch()
    except Exception as e:
        result = {
            "value": None, "rating": None, "error": repr(e)[:300],
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
