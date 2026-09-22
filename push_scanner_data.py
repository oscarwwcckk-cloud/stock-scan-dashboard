# -*- coding: utf-8 -*-
"""push_scanner_data.py ── 把兩個 scanner 的 xlsx 同步進此 repo 並 push。

每次 scanner 跑完(由各自的 daily bat 在結尾 chain 呼叫)就執行:
  copy kq + sepa 的 xlsx 進 data/ → 寫 scan_info.json → git commit + push。
push 觸發 Streamlit Cloud 重部署,雲端讀到新 xlsx。

仿 futu-dashboard/refresh_agent.py 的 commit_and_push(fetch+rebase 重試)
+ NO_WINDOW(避免 pythonw 常駐時 git 黑窗彈出)。

用法:
    python push_scanner_data.py            # 同步並 push
    python push_scanner_data.py --check    # 只顯示將會做什麼,不 commit
"""
import os
import sys
import json
import shutil
import subprocess
import datetime as dt

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_DIR, "data")
MAIN_BRANCH = "main"

SRC_KQ = r"C:\Users\kd122\kq-scanner\results\kq_scan_results.xlsx"
SRC_SEPA = r"C:\Users\kd122\stock-scanner\results\sepa_scan_results.xlsx"
DST_KQ = os.path.join(DATA_DIR, "kq_scan_results.xlsx")
DST_SEPA = os.path.join(DATA_DIR, "sepa_scan_results.xlsx")

SCAN_INFO = os.path.join(DATA_DIR, "scan_info.json")
STATUS_FILE = os.path.join(REPO_DIR, "refresh_status.json")
LOG_FILE = os.path.join(REPO_DIR, "sync_agent.log")

# Windows:若由 pythonw 或排程呼叫,git.exe(console 程式)會彈黑窗;加此旗標靜默。
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg: str):
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def git(*args, check=True):
    """跑 git,回 CompletedProcess。帶 NO_WINDOW + cwd=REPO_DIR。"""
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True,
        encoding="utf-8", creationflags=NO_WINDOW,
        check=check,
    )


def scan_date_of(path: str):
    """讀 xlsx 的 Scan Info sheet(header=None)取掃描日期;取不到回 None。"""
    try:
        import pandas as pd
        si = pd.read_excel(path, sheet_name="Scan Info", header=None)
        return str(si.iloc[0, 1])
    except Exception:
        return None


def row_counts(path: str):
    """回 {sheet: row_count}。"""
    try:
        import pandas as pd
        d = pd.read_excel(path, sheet_name=None)
        return {k: len(v) for k, v in d.items()}
    except Exception:
        return {}


def write_status(ok: bool, message: str, kq_date=None, sepa_date=None):
    status = {
        "ok": ok,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "kq_scan_date": kq_date,
        "sepa_scan_date": sepa_date,
        "message": message,
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def main(check_only=False):
    log("=== 開始同步 scanner 資料 ===")

    # 1) copy xlsx(來源不存在就略過該檔,但至少要有其一)
    copied = []
    kq_date, sepa_date = None, None
    for name, src, dst in [("kq", SRC_KQ, DST_KQ), ("sepa", SRC_SEPA, DST_SEPA)]:
        if not os.path.isfile(src):
            log(f"  來源不存在,略過 {name}: {src}")
            continue
        shutil.copy2(src, dst)
        copied.append(dst)
        log(f"  copied {name} → {dst} ({os.path.getsize(dst)} bytes)")
        if name == "kq":
            kq_date = scan_date_of(dst)
        else:
            sepa_date = scan_date_of(dst)

    if not copied:
        log("  無任何來源 xlsx 可同步,結束")
        write_status(False, "no source xlsx found", kq_date, sepa_date)
        return 1

    # 2) 寫 scan_info.json
    info = {
        "synced_at": dt.datetime.now().isoformat(timespec="seconds"),
        "kq_scan_date": kq_date,
        "sepa_scan_date": sepa_date,
        "kq_rows": row_counts(DST_KQ) if os.path.isfile(DST_KQ) else {},
        "sepa_rows": row_counts(DST_SEPA) if os.path.isfile(DST_SEPA) else {},
    }
    with open(SCAN_INFO, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    log(f"  寫 scan_info.json(kq={kq_date}, sepa={sepa_date})")

    if check_only:
        log("  --check 模式,不 commit/push")
        return 0

    # 3) commit + push(帶 rebase 重試)
    try:
        git("add", "data/kq_scan_results.xlsx", "data/sepa_scan_results.xlsx",
            "data/scan_info.json", "refresh_status.json", check=True)
        st = git("status", "--porcelain", check=True)
        if not st.stdout.strip():
            log("  無變更,略過 commit/push")
            write_status(True, "no change", kq_date, sepa_date)
            return 0
        msg = f"data: scanner sync {dt.datetime.now():%Y-%m-%d %H:%M}"
        git("commit", "-m", msg, check=True)
        try:
            git("push", "origin", MAIN_BRANCH, check=True)
        except subprocess.CalledProcessError:
            log("  push 被拒,fetch+rebase 後重試")
            git("fetch", "origin", MAIN_BRANCH, check=True)
            git("rebase", f"origin/{MAIN_BRANCH}", check=True)
            git("push", "origin", MAIN_BRANCH, check=True)
        log("  push 完成 ✅")
        write_status(True, "sync ok", kq_date, sepa_date)
        return 0
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e))[:300]
        log(f"  [錯誤] commit/push 失敗:{err}")
        write_status(False, f"git error: {err}", kq_date, sepa_date)
        # 仍試著把失敗 status commit push 上去(讓雲端看到原因)
        try:
            git("add", "refresh_status.json", check=True)
            git("commit", "-m", "data: sync status (failed)", check=False)
            git("push", "origin", MAIN_BRANCH, check=False)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    check = "--check" in sys.argv
    sys.exit(main(check_only=check))
