# -*- coding: utf-8 -*-
"""TradingView Advanced Chart widget embed helper。

透過 st.components.v1.html() 嵌入官方 widget(真 TV 介面:K 線/指標/繪圖/時間軸可切),
資料與介面由 TradingView 在瀏覽器端載入,伺服器(本機/雲端)無需 egress。

widget 的 symbol 需 "EXCHANGE:TICKER" 格式(EX:NASDAQ:NVDA)。本模組用 yfinance
.info['exchange'] 對映 TV 前綴;失敗/未知回純 ticker(TV 會自行解析)。
"""
from __future__ import annotations

import json

import streamlit as st
import yfinance as yf

# yfinance .info['exchange'] 代碼 → TradingView exchange 前綴
# (美股主要交易所 + 常見 ETF 上市地)
EXCHANGE_TV: dict[str, str] = {
    # NASDAQ 系(全美證券自動報價,含全球市場)
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    # NYSE 系
    "NYQ": "NYSE", "NYS": "NYSE",
    # NYSE American(原 AMEX)
    "ASE": "AMEX", "PCX": "AMEX", "ARCX": "AMEX",
}

# 常見 ticker 直接指定 TV 前綴(繞過 .info 抓取,省限流 + 對未上市 ADR 更準)
_TICKER_TV: dict[str, str] = {
    "TSM": "NYSE",
}


@st.cache_data(ttl=86400, show_spinner=False)
def tv_symbol(ticker: str) -> str:
    """回傳 TradingView widget 用的 "EXCHANGE:TICKER" 格式 symbol。

    1. 直接對照表命中 → 用之。
    2. 否則拉 yfinance .info['exchange'] 對映 EXCHANGE_TV。
    3. 失敗/未知 → 回純 ticker(TV 自行解析)。
    """
    if not ticker:
        return ""
    t = ticker.strip().upper()
    if t in _TICKER_TV:
        return f"{_TICKER_TV[t]}:{t}"
    try:
        exch = yf.Ticker(t).info.get("exchange", "")
    except Exception:
        exch = ""
    tv = EXCHANGE_TV.get((exch or "").strip().upper())
    return f"{tv}:{t}" if tv else t


def embed_html(symbol: str, interval: str = "D",
               theme: str = "dark", locale: str = "zh_TW") -> str:
    """產生 TradingView Advanced Chart widget HTML(交給 st.iframe(height="content") 渲染)。

    symbol 需 "EXCHANGE:TICKER";未含冒號者 TV 會自行解析。
    interval: D=日、W=週、M=月、60=1小時…;style "1"=蠟燭。

    用 st.iframe(height="content") iframe:內部 <script src> 會正常執行
    (st.html 的 dangerouslySetInnerHTML 不跑 script,故改 iframe),
    Streamlit 自動量 widget 載入後的容器高度讓 iframe 貼合。容器靠內嵌 JS
    把高度鎖成 = 自身寬度(正方形),widget autosize 填滿。
    """
    config = {
        "autosize": True,
        "symbol": symbol,
        "interval": interval,
        "timezone": "Asia/Hong_Kong",
        "theme": theme,
        "style": "1",            # 蠟燭圖
        "locale": locale,
        "hide_side_toolbar": False,
        "allow_symbol_change": False,
        "withdateranges": True,
        "support_host": "https://www.tradingview.com",
    }
    config_json = json.dumps(config, ensure_ascii=False)
    # #tv-wrap 高度由 JS 設為其寬度(正方形,至少 480px),widget autosize 填滿。
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#131722; }}
  #tv-wrap {{ position:relative; width:100%; min-height:480px; background:#131722;
              overflow:hidden; }}
  #tv-wrap .tradingview-widget-container,
  #tv-wrap .tradingview-widget-container__widget {{ height:100% !important; width:100% !important; }}
  #tv-wrap .tradingview-widget-copyright {{ position:absolute; bottom:4px; right:8px;
              font-size:10px; opacity:.55; }}
  #tv-wrap .tradingview-widget-copyright a {{ color:#2962ff; text-decoration:none; }}
</style></head>
<body>
<div id="tv-wrap">
  <div class="tradingview-widget-container">
    <div class="tradingview-widget-container__widget"></div>
  </div>
  <div class="tradingview-widget-copyright">
    <a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank">
      <span class="blue-text">圖表由 TradingView 提供</span>
    </a>
  </div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
    {config_json}
  </script>
</div>
<script>
  // 把容器高度鎖成 = 寬度(正方形,至少 480);widget 載入/縮放後重算。
  (function() {{
    var wrap = document.getElementById('tv-wrap');
    function square() {{
      var w = wrap.clientWidth || 480;
      wrap.style.height = Math.max(w, 480) + 'px';
    }}
    square();
    window.addEventListener('load', square);
    window.addEventListener('resize', square);
    // TV widget 非同步載入後也要重算一次,容器才會被撐開後量到
    setTimeout(square, 800);
    setTimeout(square, 2000);
  }})();
</script>
</body></html>"""


