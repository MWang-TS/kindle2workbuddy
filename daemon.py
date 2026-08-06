# -*- coding: utf-8 -*-
"""Kindle Dashboard 后台守护进程
每 REFRESH_SECONDS 秒跑一次 refresh.py，无窗口静默运行。
"""
import time
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).parent
INTERVAL = 30  # 秒
LOG_FILE = BASE / "output" / "daemon.log"


def log(msg):
    ts = dt_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def dt_now():
    import datetime as dt
    return dt.datetime.now()


def main():
    log(f"Daemon started, refresh every {INTERVAL}s")
    while True:
        try:
            r = subprocess.run(
                [sys.executable, str(BASE / "refresh.py")],
                cwd=str(BASE),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                log(f"refresh.py exited with {r.returncode}")
                if r.stderr:
                    # 完整记录stderr（不截断），多行错误用换行分隔
                    for line in r.stderr.strip().split('\n'):
                        log(f"  {line}")
        except subprocess.TimeoutExpired:
            log("refresh.py timeout (120s)")
        except Exception as e:
            log(f"error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()