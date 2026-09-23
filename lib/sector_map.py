"""
Canonical sector classification.
Explicit constituent lists override yfinance sector/industry fields.
Tech-group sectors benchmark vs QQQ; traditional-group vs SPY.
"""

SECTOR_MAP: dict[str, dict] = {
    # ── AI / Tech (benchmark: QQQ) ───────────────────────────────────────────
    "ai_semiconductors": {
        "name": "AI 半導體",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "NVDA", "AMD", "AVGO", "MRVL", "QCOM", "TSM",
            "AMAT", "LRCX", "KLAC", "ASML", "ONTO", "WOLF",
            "CRUS", "MPWR", "SIMO", "CRDO", "SMCI",
        ],
    },
    "ai_data_centers": {
        "name": "AI 資料中心與基礎設施",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "EQIX", "DLR", "IRM", "VRT", "ETN", "DELL",
            "HPE", "STX", "WDC", "NTAP",
        ],
    },
    "ai_software": {
        "name": "AI 軟體與平台",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "PLTR", "AI", "SNOW", "GTLB", "MDB", "DDOG",
            "BBAI", "SOUN", "IREN", "PATH",
        ],
    },
    "cloud_computing": {
        "name": "雲端運算",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "AMZN", "MSFT", "GOOG", "GOOGL", "ORCL",
            "IBM", "NET", "FSLY",
        ],
    },
    "ai_networking": {
        "name": "AI 網通",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "ANET", "CSCO", "LITE", "VIAV", "CIEN",
            "CALX",
        ],
    },
    "cybersecurity": {
        "name": "網路安全",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "CRWD", "PANW", "ZS", "S", "FTNT", "OKTA",
            "RPD", "QLYS", "TENB", "VRNS",
        ],
    },
    "enterprise_software": {
        "name": "企業軟體",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "CRM", "NOW", "SAP", "ADBE", "WDAY", "INTU",
            "TEAM", "HUBS", "VEEV", "DOCU",
        ],
    },
    "fintech": {
        "name": "金融科技",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "XYZ", "PYPL", "AFRM", "COIN", "HOOD", "SOFI",
            "UPST", "HAPN", "FLYW",
        ],
    },
    # ── Traditional (benchmark: SPY) ─────────────────────────────────────────
    # 成分股來自 SPDR 板塊 ETF 每日持倉(holdings_fetcher 動態抓),永遠新鮮。
    # etf 欄 = 該板塊對應的 SPDR 板塊 ETF ticker。
    "healthcare": {
        "name": "醫療與生技",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLV",
        "yfinance_sectors": ["Healthcare"],
    },
    "financials": {
        "name": "金融",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLF",
        "yfinance_sectors": ["Financial Services"],
    },
    "energy": {
        "name": "能源",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLE",
        "yfinance_sectors": ["Energy"],
    },
    "industrials": {
        "name": "工業",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLI",
        "yfinance_sectors": ["Industrials"],
    },
    "consumer_discretionary": {
        "name": "非必需消費",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLY",
        "yfinance_sectors": ["Consumer Cyclical"],
    },
    "consumer_staples": {
        "name": "必需消費",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLP",
        "yfinance_sectors": ["Consumer Defensive"],
    },
    "materials": {
        "name": "原物料與礦業",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLB",
        "yfinance_sectors": ["Basic Materials"],
    },
    "real_estate": {
        "name": "不動產",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLRE",
        "yfinance_sectors": ["Real Estate"],
    },
    "utilities": {
        "name": "公用事業",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLU",
        "yfinance_sectors": ["Utilities"],
    },
    "communication": {
        "name": "通信服務",
        "benchmark": "SPY",
        "group": "traditional",
        "etf": "XLC",
        "yfinance_sectors": ["Communication Services"],
    },
}

# Reverse lookup: ticker → sector_key (explicit entries win over yfinance)
EXPLICIT_TICKER_MAP: dict[str, str] = {
    ticker: sector_key
    for sector_key, info in SECTOR_MAP.items()
    for ticker in info.get("constituents", [])
}

# yfinance sector string → sector_key (for fallback classification)
_YFINANCE_SECTOR_LOOKUP: dict[str, str] = {
    yf_sector: sector_key
    for sector_key, info in SECTOR_MAP.items()
    for yf_sector in info.get("yfinance_sectors", [])
}

BENCHMARK_TICKERS = ["QQQ", "SPY"]
INDEX_TICKERS = {"^GSPC": "SPX", "^NDX": "NDX", "^DJI": "DJI"}


def assign_sector(ticker: str, yf_sector: str = "", yf_industry: str = "") -> tuple[str, str]:
    """
    Returns (sector_key, benchmark) for a ticker.
    Priority: explicit constituent list > yfinance sector field > fallback 'other'.
    """
    if ticker in EXPLICIT_TICKER_MAP:
        key = EXPLICIT_TICKER_MAP[ticker]
        return key, SECTOR_MAP[key]["benchmark"]

    if yf_sector in _YFINANCE_SECTOR_LOOKUP:
        key = _YFINANCE_SECTOR_LOOKUP[yf_sector]
        return key, SECTOR_MAP[key]["benchmark"]

    # Tech-sounding industry names go to enterprise_software as best-effort
    if "Software" in yf_industry or "Technology" in yf_sector:
        return "enterprise_software", "QQQ"

    return "other", "SPY"


def get_all_sector_keys() -> list[str]:
    return list(SECTOR_MAP.keys())


def get_sector_info(sector_key: str) -> dict | None:
    return SECTOR_MAP.get(sector_key)
