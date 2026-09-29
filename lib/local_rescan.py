# -*- coding: utf-8 -*-
"""lib/local_rescan.py ── Scan 頁「本機重掃」refresh 的引擎。

為何存在:Scan 頁讀的是 committed xlsx(data/*.xlsx),舊的 refresh 只清
@st.cache_data 記憶體快取、但讀回同一個舊檔,畫面不會變。本機要真的更新,
得重跑 ~/kq-scanner/main.py --now 產出新 xlsx,再 copy 進 data/ 才會讀到。

本機 vs 雲端:本機 = ~/kq-scanner 這個目錄存在(雲端容器沒有,因為 repo 是
stock-scan-dashboard 本身,kq-scanner 是另一個未進 repo 的本機專案)。
OpenD 連通另外偵測 —— 本機環境下 OpenD 沒開也要明確報錯(而非默默降級清快取),
因為那會讓使用者誤以為「按了沒反應」。

本機重掃成功後:auto push 上雲(push_scanner_data.py),讓雲端 dashboard 也讀到
新貨 —— 否則本機畫面變了、雲端還是舊的,使用者又得到本機點 push。
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

# push_scanner_data.py:本機重掃後呼叫它把 xlsx 上雲。
PUSH_SCRIPT = os.path.join(_REPO, "push_scanner_data.py")

# OpenD host/port(同 kq-scanner/config.py:167-168;硬編碼以免 import 該專案的 config
# 污染 dashboard 行程的模組路徑)。
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

# main.py --now 可能要幾分鐘(snapshot 全 universe + 寫 xlsx);給足夠上限。
SCAN_TIMEOUT = 600

# Windows:由 pythonw/排程跑 git/subprocess 避免黑窗;scanner subprocess 同理。
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_local() -> bool:
    """本機環境 = ~/kq-scanner 目錄存在。

    用目錄存在(而非 OpenD 連通)判別環境:OpenD 開沒開是「能不能掃」的前置,
    與「這台機器是不是本機」無關。雲端容器沒有 ~/kq-scanner → False。
    """
    return os.path.isfile(KQ_MAIN)


def opend_up() -> bool:
    """Futu OpenD 在 localhost 連得上嗎。本機環境下這是重掃前置。"""
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
    OpenD 未啟動時 main.py 會自行中止(exit 1)—— 但這裡不預檢,讓 scanner 自己報,
    訊息更完整;caller 在按下前可先 opend_up() 給使用者前置提示。
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


def push_to_cloud() -> tuple[bool, str]:
    """呼叫 push_scanner_data.py 把 data/ 的 xlsx commit+push 上雲。回 (ok, msg)。

    只在 REPO 是 git 且 push 腳本存在時跑;失敗不擋本機畫面刷新(本機已讀新 xlsx),
    只把失敗訊息回給使用者。push 成功 → 雲端重部署後讀到新貨。
    """
    if not os.path.isfile(PUSH_SCRIPT):
        return False, f"找不到 push 腳本:{PUSH_SCRIPT}"
    try:
        proc = subprocess.run(
            [_python_exe(), PUSH_SCRIPT],
            cwd=_REPO,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=180,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "push 超時(180s),git push 可能卡住"
    except Exception as e:
        return False, f"啟動 push 失敗:{repr(e)[:200]}"
    tail = (proc.stdout or proc.stderr or "")[-400:]
    if proc.returncode not in (0,):  # push 在「無變更」時也回 0
        return False, f"push 回傳碼 {proc.returncode}。尾端:\n{tail}"
    return True, tail.strip().splitlines()[-1] if tail.strip() else "push 完成 ✅"


def rescan_and_push() -> tuple[bool, str]:
    """本機重掃 → copy → push 上雲 的統一入口(給 page_scan 一鍵呼叫)。

    回 (overall_ok, message)。任一步失敗即止並回錯;但 copy 成功後 push 失敗
    仍算「本機已刷新」,只是雲端沒同步 —— message 會說清楚。
    """
    ok, msg = run_scan()
    if not ok:
        return False, msg
    copy_results()
    pok, pmsg = push_to_cloud()
    if not pok:
        return True, f"本機已刷新,但上雲失敗:{pmsg}"
    return True, f"掃描完成並已上雲 ✅"
