"""
Canonical sector classification.
Explicit constituent lists override yfinance sector/industry fields.
Tech-group sectors benchmark vs QQQ; traditional-group vs SPY.
"""

SECTOR_MAP: dict[str, dict] = {
    # ── AI / Tech (benchmark: QQQ) ───────────────────────────────────────────
    "ai_semiconductors": {
        "name": "AI Semiconductors",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "NVDA", "AMD", "AVGO", "MRVL", "QCOM", "TSM",
            "AMAT", "LRCX", "KLAC", "ASML", "ONTO", "WOLF",
            "CRUS", "MPWR", "SIMO", "CRDO", "SMCI",
        ],
    },
    "ai_data_centers": {
        "name": "AI Data Centers & Infrastructure",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "EQIX", "DLR", "IRM", "VRT", "ETN", "DELL",
            "HPE", "STX", "WDC", "NTAP",
        ],
    },
    "ai_software": {
        "name": "AI Software & Platforms",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "PLTR", "AI", "SNOW", "GTLB", "MDB", "DDOG",
            "BBAI", "SOUN", "IREN", "PATH",
        ],
    },
    "cloud_computing": {
        "name": "Cloud Computing",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "AMZN", "MSFT", "GOOG", "GOOGL", "ORCL",
            "IBM", "RCLOUD", "NET", "FSLY",
        ],
    },
    "ai_networking": {
        "name": "AI Networking",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "ANET", "CSCO", "JNPR", "LITE", "VIAV", "CIEN",
            "INFN", "CALX", "COMM",
        ],
    },
    "cybersecurity": {
        "name": "Cybersecurity",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "CRWD", "PANW", "ZS", "S", "FTNT", "OKTA",
            "CYBR", "RPD", "QLYS", "TENB", "VRNS",
        ],
    },
    "enterprise_software": {
        "name": "Enterprise Software",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "CRM", "NOW", "SAP", "ADBE", "WDAY", "INTU",
            "TEAM", "HCP", "HUBS", "VEEV", "DOCU",
        ],
    },
    "fintech": {
        "name": "Fintech",
        "benchmark": "QQQ",
        "group": "tech",
        "constituents": [
            "SQ", "PYPL", "AFRM", "COIN", "HOOD", "SOFI",
            "UPST", "LC", "FLYW", "SMAR",
        ],
    },
    # ── Traditional (benchmark: SPY) ─────────────────────────────────────────
    "healthcare": {
        "name": "Healthcare & Biotech",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Healthcare"],
    },
    "financials": {
        "name": "Financials",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Financial Services"],
    },
    "energy": {
        "name": "Energy",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Energy"],
    },
    "industrials": {
        "name": "Industrials",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Industrials"],
    },
    "consumer_discretionary": {
        "name": "Consumer Discretionary",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Consumer Cyclical"],
    },
    "consumer_staples": {
        "name": "Consumer Staples",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Consumer Defensive"],
    },
    "materials": {
        "name": "Materials & Mining",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Basic Materials"],
    },
    "real_estate": {
        "name": "Real Estate",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Real Estate"],
    },
    "utilities": {
        "name": "Utilities",
        "benchmark": "SPY",
        "group": "traditional",
        "yfinance_sectors": ["Utilities"],
    },
    "communication": {
        "name": "Communication Services",
        "benchmark": "SPY",
        "group": "traditional",
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
