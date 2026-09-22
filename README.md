# Stock Scan Dashboard

美股掃描 + 市場狀況 Streamlit 儀表板。深色飛書風格(仿 futu-dashboard)。

## 兩大功能

- **Stock Scanning** — 展示 `kq-scanner`(8 種 setup)與 `stock-scanner`(SEPA)的掃描結果,前端 slider 即時再篩選。
- **Market Situation** — 大盤指數健康度(SPX/NDX/DJI)+ 產業類股輪動 + 市場廣度/情緒。資料源 yfinance + Finviz。

## 資料來源

兩個 scanner 各自跑自己的排程寫出 xlsx,本機 `push_scanner_data.py` 把 xlsx commit 進此 repo 觸發 Streamlit Cloud 重部署。雲端不依賴 OpenD。

- `data/kq_scan_results.xlsx` ← `~/kq-scanner/results/`(每日 20:45 HKT 掃)
- `data/sepa_scan_results.xlsx` ← `~/stock-scanner/results/`

市場資料(指數/類股/廣度)雲端即時抓 yfinance + Finviz,`@st.cache_data(ttl=3600)`。

## 本機執行

```bash
pip install -r requirements.txt
python -m streamlit run dashboard.py --server.port 8501 --server.headless true
```

## 同步最新掃描結果到雲端

```bash
cd C:\Users\kd122\stock-scan-dashboard
python push_scanner_data.py   # copy 兩 xlsx 進 data/ + git commit + push
```

通常 chain 在各 scanner 的 daily bat 結尾自動跑。

## 部署

Streamlit Community Cloud,main file = `dashboard.py`,repo PRIVATE。
