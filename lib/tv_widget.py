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
    """產生 TradingView Advanced Chart widget HTML(交給 components.html iframe 渲染)。

    symbol 需 "EXCHANGE:TICKER";未含冒號者 TV 會自行解析。
    interval: D=日、W=週、M=月、60=1小時…;style "1"=蠟燭。

    必須用 st.components.v1.html() 渲染(真 iframe):TV 官方 embed 是
    <script src=...>{JSON 設定}</script> 模式(script 讀自身 textContent),
    只有在真 iframe 文件裡才會執行 —— st.html(dangerouslySetInnerHTML)插入的
    script 按 HTML 規格不執行,widget 會空白消失。
    caller 給 iframe 固定高(components.html(height=…)),#tv-wrap 用 100vh 填滿,
    widget autosize 貼合,無需 JS 量高。
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
    # #tv-wrap 100vh 填滿 iframe(caller 以 components.html(height=…) 定高)。
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#131722; height:100%; }}
  #tv-wrap {{ position:relative; width:100%; height:100vh; min-height:480px;
              background:#131722; overflow:hidden; }}
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
</body></html>"""


