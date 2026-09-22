"""內容指紋快取鍵,破解 Streamlit Cloud 的 mtime 陷阱。

Streamlit Cloud 對 data-only commit(只更新檔案內容)常把新檔熱同步進
同一個活著的行程再 rerun,而非冷重啟 —— 此時檔案 mtime 不一定變,
若用 mtime 當快取鍵,@st.cache_data 不會失效,就一直吐舊資料。
改用「檔案大小 + sha1」當快取鍵,只要內容一變必失效。移植自 futu-dashboard。
"""
import hashlib


def _sig(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read()
        return f"{len(data)}-{hashlib.sha1(data).hexdigest()}"
    except OSError:
        return "missing"
