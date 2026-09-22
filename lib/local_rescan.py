# -*- coding: utf-8 -*-
"""lib/local_rescan.py ── Scan 頁「本機重掃」refresh 的引擎。

為何存在:Scan 頁讀的是 committed xlsx(data/*.xlsx),舊的 refresh 只清
@st.cache_data 記憶體快取、但讀回同一個舊檔,畫面不會變。本機要真的更新,
得重跑 ~/kq-scanner/main.py --now 產出新 xlsx,再 copy 進 data/ 才會讀到。

本機 vs 雲端:偵測 Futu OpenD(127.0.0.1:11111)連得上才視為本機環境。
雲端連不到 localhost OpenD —— 這同時是「雲端跑不了 scanner」的事實,所以
port 連通性既是環境判別也是前置檢查,一舉兩得。

只重掃 + copy,不 git commit、不 push —— 上雲是另一個明確動作(push_scanner_data.py)。
"""
import os
import shutil
import socket
import subprocess
import sys

# ~/kq-scanner 路徑:本檔在 ~/stock-scan-dashboard/lib/ 下,往上一層再到 kq-scanner。
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
KQ_SCANNER_DIR = os.path.join(os.path.dirname(_REPO), "kq-scanner")
KQ_MAIN = os.path.join(KQ_SCANNER_DIR, "main.py")

# scanner 產出 → dashboard 讀入(同 push_scanner_data.py 的來源/目的,只取 kq)。
SRC_KQ = os.path.join(KQ_SCANNER_DIR, "results", "kq_scan_results.xlsx")
DST_KQ = os.path.join(_REPO, "data", "kq_scan_results.xlsx")

# OpenD host/port(同 kq-scanner/config.py:167-168;硬編碼以免 import 該專案的 config
# 污染 dashboard 行程的模組路徑)。
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

# main.py --now 可能要幾分鐘(snapshot 全 universe + 寫 xlsx);給足夠上限。
SCAN_TIMEOUT = 600

# Windows:由 pythonw/排程跑 git/subprocess 避免黑窗;scanner subprocess 同理。
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_local() -> bool:
    """本機環境 = OpenD 在 localhost 連得上。雲端連不到 → False(降級成純清快取)。

    port 連通同時是重掃前置:連不上就連 scanner 本身也跑不了(main.py 會中止)。
    """
    try:
        with socket.create_connection((OPEND_HOST, OPEND_PORT), timeout=1.5):
            return True
    except OSError:
        return False


def _python_exe() -> str:
    """scanner 用的 Python(同 run_kq_scan.bat 的 PYEXE);fallback 用當前直譯器。"""
    fixed = r"C:\Users\kd122\AppData\Local\Programs\Python\Python312\python.exe"
    return fixed if os.path.isfile(fixed) else sys.executable


def run_scan() -> tuple[bool, str]:
    """本機重跑 kq-scanner。回 (ok, message)。

    成功條件:subprocess 回 0 且 SRC_KQ 存在。caller 拿到 ok 後再 copy+清快取。
    """
    if not os.path.isfile(KQ_MAIN):
        return False, f"找不到 scanner 入口:{KQ_MAIN}"

    try:
        proc = subprocess.run(
            [_python_exe(), KQ_MAIN, "--now", "--no-notify"],
            cwd=KQ_SCANNER_DIR,           # kq-scanner 用相對 import,必須在其根目錄跑
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=SCAN_TIMEOUT,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, f"掃描超時({SCAN_TIMEOUT}s),OpenD 可能卡住或 universe 過大"
    except Exception as e:
        return False, f"啟動 scanner 失敗:{repr(e)[:200]}"

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        return False, f"scanner 回傳碼 {proc.returncode}。尾端輸出:\n{tail}"

    if not os.path.isfile(SRC_KQ):
        return False, f"scanner 跑完但未產出 xlsx:{SRC_KQ}"

    return True, "掃描完成"


def copy_results() -> bool:
    """把 scanner 剛產出的 xlsx copy 進 data/。copy 後 caller 清快取+rerun 生效。"""
    if not os.path.isfile(SRC_KQ):
        return False
    os.makedirs(os.path.dirname(DST_KQ), exist_ok=True)
    shutil.copy2(SRC_KQ, DST_KQ)
    return True
