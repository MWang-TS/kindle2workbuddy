# -*- coding: utf-8 -*-
"""kindle-dashboard 推送脚本
生成 dashboard.png 后，通过 SCP 推送到 Kindle，再用 SSH 执行 eips 刷新。
WiFi 模式：Kindle IP 192.168.8.24，SSH 免密（id_kindle 密钥）。
"""
import os
import sys
import subprocess
import platform
import datetime as dt
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
from render import render

# ── Kindle SSH 配置（从 settings.py 读取）──────────────
try:
    from settings import *
except ImportError:
    pass

KINDLE_HOST    = getattr(globals(), 'KINDLE_HOST', "192.168.8.24")
KINDLE_PORT    = getattr(globals(), 'KINDLE_PORT', 22)
KINDLE_USER    = getattr(globals(), 'KINDLE_USER', "root")
KINDLE_REMOTE  = getattr(globals(), 'KINDLE_REMOTE', "/mnt/us/dashboard.png")
SSH_KEY        = os.path.expanduser(getattr(globals(), 'SSH_KEY', "~/.ssh/id_kindle"))
EIPS_PATH      = getattr(globals(), 'EIPS_PATH', "/usr/sbin/eips")

OUTPUT_PNG = BASE_DIR / "output" / "dashboard.png"
LOG_FILE   = BASE_DIR / "output" / "refresh.log"

# SSH 公共选项
SSH_OPTS = [
    "-i", SSH_KEY,
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "ConnectTimeout=10",
]


def log(msg):
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def find_bin(name):
    """查找 ssh 或 scp 可执行文件"""
    # Windows OpenSSH 优先
    candidates = [
        f"C:/Windows/System32/OpenSSH/{name}.exe",
        f"C:/Program Files/Git/usr/bin/{name}.exe",
        name,  # PATH 里的
    ]
    for c in candidates:
        try:
            subprocess.run([c, "-V"], capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return name  # 兜底


def ping_host(host):
    """ping 测试"""
    cmd = ["ping", "-n", "1", "-w", "2000", host] if platform.system() == "Windows" else ["ping", "-c", "1", "-W", "2", host]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def push_and_refresh(ssh_bin, scp_bin, host):
    """SCP 推送 + SSH eips 刷新"""
    # 1. 防睡眠 + 停止framework + 清屏 + 推送图片 + 刷新
    remote_cmd = (
        f"lipc-set-prop com.lab126.powerd preventScreenSaver 1; "
        f"/etc/init.d/framework stop 2>/dev/null; "
        f"sleep 1; "
        f"{EIPS_PATH} -c; "
        f"{EIPS_PATH} -g {KINDLE_REMOTE}"
    )

    # 2. SCP 传图
    log(f"SCP → root@{host}:{KINDLE_REMOTE}")
    scp_cmd = [scp_bin] + SSH_OPTS + [str(OUTPUT_PNG), f"{KINDLE_USER}@{host}:{KINDLE_REMOTE}"]
    r = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        log(f"❌ SCP 失败: {r.stderr.strip()[:200]}")
        return False
    log("✅ SCP 成功")

    # 3. SSH eips 刷新
    log(f"SSH eips 刷新...")
    ssh_cmd = [ssh_bin] + SSH_OPTS + ["-p", str(KINDLE_PORT), f"{KINDLE_USER}@{host}", remote_cmd]
    r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        log(f"❌ eips 刷新失败: {r.stderr.strip()[:200]}")
        return False
    log("✅ eips 刷新成功")
    return True


def main():
    log("=" * 50)
    log("开始刷新 dashboard")

    # 1. 生成 PNG
    png = render()
    log(f"已生成: {png}")

    # 2. 查找 ssh/scp
    ssh_bin = find_bin("ssh")
    scp_bin = find_bin("scp")
    log(f"SSH: {ssh_bin}  SCP: {scp_bin}")

    # 3. 检测 Kindle
    if not ping_host(KINDLE_HOST):
        log(f"❌ Kindle 不在线 ({KINDLE_HOST})，请确认 Kindle 已唤醒且 WiFi 已连")
        return 1
    log(f"✅ Kindle 在线: {KINDLE_HOST}")

    # 4. 推送 + 刷新
    if push_and_refresh(ssh_bin, scp_bin, KINDLE_HOST):
        log("✅ 全部完成")
        return 0
    else:
        log("❌ 推送过程中出错")
        return 1


if __name__ == "__main__":
    sys.exit(main())
