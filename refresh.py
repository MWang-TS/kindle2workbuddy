# -*- coding: utf-8 -*-
"""kindle-dashboard 推送脚本
生成 dashboard.png 后，通过 SCP 推送到 Kindle，再用 SSH 执行 eips 刷新。
WiFi 模式：Kindle IP 见 settings.py 的 KINDLE_HOST，SSH 免密（id_kindle 密钥）。
"""
import os
import re
import sys
import json
import time
import socket
import subprocess
import platform
import datetime as dt
import concurrent.futures
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
from render import render, get_page_for_time

PAGE_STATE_FILE = BASE_DIR / "output" / "page_state.json"
FORCE_REFRESH_SECONDS = 600  # 页码长时间未变时强制刷新（10分钟）

# ── Kindle SSH 配置（从 settings.py 读取）──────────────
try:
    from settings import *
except ImportError:
    pass

# 注意：getattr(globals(), ...) 是错误写法（globals()返回dict，没有属性可读，
# 会导致fallback永远生效，settings.py里的配置永远不会被真正读取）。
# 正确做法：globals().get(name, fallback) 读取dict的key。
KINDLE_HOST    = globals().get('KINDLE_HOST', "192.168.x.x")
KINDLE_PORT    = globals().get('KINDLE_PORT', 22)
KINDLE_USER    = globals().get('KINDLE_USER', "root")
KINDLE_REMOTE  = globals().get('KINDLE_REMOTE', "/mnt/us/dashboard.png")
SSH_KEY        = os.path.expanduser(globals().get('SSH_KEY', "~/.ssh/id_kindle"))
EIPS_PATH      = globals().get('EIPS_PATH', "/usr/sbin/eips")
# DHCP自动重新发现：IP失联时自动扫描局域网找回Kindle（默认开启，settings.py里可关闭）
AUTO_DISCOVER_IP = globals().get('AUTO_DISCOVER_IP', True)
SETTINGS_FILE  = BASE_DIR / "settings.py"

OUTPUT_PNG = BASE_DIR / "output" / "dashboard.png"
LOG_FILE   = BASE_DIR / "output" / "refresh.log"

# Windows 隐藏子进程窗口标志（防止 ssh/scp 弹窗）
NO_WINDOW = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

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
            subprocess.run([c, "-V"], capture_output=True, timeout=5, creationflags=NO_WINDOW)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return name  # 兜底


def ping_host(host, timeout_ms=2000, retries=1):
    """ping 测试，支持重试（局域网设备偶发丢包时避免误判为离线，
    Kindle WiFi信号不稳定场景下实测丢包率可达30%+）"""
    cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host] if platform.system() == "Windows" else \
          ["ping", "-c", "1", "-W", str(timeout_ms // 1000 or 1), host]
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout_ms / 1000 + 3, creationflags=NO_WINDOW)
            if r.returncode == 0:
                return True
        except Exception:
            pass
    return False


def get_local_subnet_prefix():
    """获取本机所在局域网子网前缀（如 '192.168.8'），用于扫描范围。
    用 UDP connect 到公共地址获取路由出口IP，不会真的发包。
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return ".".join(local_ip.split(".")[:3])
    except Exception:
        return None


def verify_is_kindle(host, ssh_bin, timeout=3, retries=1):
    """通过SSH执行Kindle特有命令验证该IP是否为目标Kindle设备。
    用 lipc-get-prop 查询电量（返回0-100的数字），只有真正的Kindle才会有这个命令。
    带重试：Kindle WiFi信号不稳定时单次SSH可能因丢包失败，重试避免误判漏检。
    """
    cmd = [
        ssh_bin, "-i", SSH_KEY,
        "-p", str(KINDLE_PORT),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "BatchMode=yes",  # 禁止交互式密码提示，避免扫描时卡住
        f"{KINDLE_USER}@{host}",
        "lipc-get-prop com.lab126.powerd battLevel",
    ]
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 2, creationflags=NO_WINDOW)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                return True
        except Exception:
            pass
    return False


def _scan_once(ssh_bin, exclude_host, max_workers):
    """单次完整扫描：ping找在线设备 + SSH验证身份，返回找到的IP或None"""
    subnet = get_local_subnet_prefix()
    if not subnet:
        log("⚠️ 无法获取本机子网信息，跳过自动发现")
        return None

    log(f"🔍 开始扫描子网 {subnet}.0/24 寻找 Kindle...")
    candidates = [f"{subnet}.{i}" for i in range(1, 255) if f"{subnet}.{i}" != exclude_host]

    # 第一轮：并行ping找出在线设备（带1次重试，容忍偶发丢包）
    online = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(ping_host, ip, 500, 1): ip for ip in candidates}
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                online.append(futures[future])
    log(f"🔍 子网内发现 {len(online)} 台在线设备，逐一验证身份...")

    if not online:
        return None

    # 第二轮：对在线设备并行SSH验证身份。
    # 注意：并发数不能太高——Windows OpenSSH客户端在高并发下(实测10个)会出现
    # 部分请求异常失败(非超时,是连接层面的资源竞争),返回False但不抛异常,容易漏判
    # 真实的Kindle。实测并发5可稳定识别，故限制为5。
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(online))) as executor:
        futures = {executor.submit(verify_is_kindle, ip, ssh_bin): ip for ip in online}
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                return futures[future]

    return None


def discover_kindle_ip(ssh_bin, exclude_host=None, max_workers=40):
    """DHCP自动重新发现：并行ping本机子网所有地址，对在线IP并行SSH验证身份，
    找到第一个匹配的Kindle即返回其IP。整个过程约20-40秒（子网内设备较多或
    Kindle WiFi信号不稳定时会略长）。

    只扫描一轮不做整体重试——daemon本身每30秒会自动重跑refresh.py，
    这次没找到，下一个周期会自然重试，不需要在单次调用内堆叠重试拖长耗时。

    返回: 找到的新IP字符串，或 None（未找到）
    """
    found_ip = _scan_once(ssh_bin, exclude_host, max_workers)
    if found_ip:
        log(f"✅ 找到 Kindle，新IP: {found_ip}")
        return found_ip

    log("❌ 扫描完成，未在局域网内找到匹配的 Kindle 设备（下个周期会自动重试）")
    return None


def update_settings_ip(new_ip):
    """把新发现的IP写回 settings.py，持久化配置（下次启动无需重新扫描）。
    只替换 KINDLE_HOST 那一行，保留文件其余内容和注释不变。
    """
    if not SETTINGS_FILE.exists():
        log("⚠️ settings.py 不存在，无法持久化新IP（本次推送仍会使用新IP，但下次重启后需重新扫描）")
        return False
    try:
        text = SETTINGS_FILE.read_text(encoding="utf-8")
        new_text, n = re.subn(
            r'^KINDLE_HOST\s*=\s*["\'][^"\']*["\']',
            f'KINDLE_HOST    = "{new_ip}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if n == 0:
            log("⚠️ settings.py 中未找到 KINDLE_HOST 行，无法自动更新")
            return False
        SETTINGS_FILE.write_text(new_text, encoding="utf-8")
        log(f"✅ 已将新IP写回 settings.py: {new_ip}")
        return True
    except Exception as e:
        log(f"⚠️ 写回 settings.py 失败: {e}")
        return False


def push_and_refresh(ssh_bin, scp_bin, host):
    """SCP 推送 + SSH eips 刷新"""
    # 1. 防睡眠 + 停止framework + 清屏 + 强制全屏刷新
    remote_cmd = (
        f"lipc-set-prop com.lab126.powerd preventScreenSaver 1; "
        f"/etc/init.d/framework stop 2>/dev/null; "
        f"sleep 1; "
        f"{EIPS_PATH} -c; "
        f"{EIPS_PATH} -f -g {KINDLE_REMOTE}"
    )

    # 2. SCP 传图（注意：scp 端口参数是大写 -P，与 ssh 的小写 -p 不同，之前漏加导致
    # 走 ~/.ssh/config 里的默认端口配置，若该IP在config中被其他设备占用会连接失败）
    log(f"SCP → root@{host}:{KINDLE_REMOTE}")
    scp_cmd = [scp_bin] + SSH_OPTS + ["-P", str(KINDLE_PORT), str(OUTPUT_PNG), f"{KINDLE_USER}@{host}:{KINDLE_REMOTE}"]
    r = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    if r.returncode != 0:
        log(f"❌ SCP 失败: {r.stderr.strip()[:200]}")
        return False
    log("✅ SCP 成功")

    # 3. SSH eips 刷新
    log(f"SSH eips 刷新...")
    ssh_cmd = [ssh_bin] + SSH_OPTS + ["-p", str(KINDLE_PORT), f"{KINDLE_USER}@{host}", remote_cmd]
    r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW)
    if r.returncode != 0:
        log(f"❌ eips 刷新失败: {r.stderr.strip()[:200]}")
        return False
    log("✅ eips 刷新成功")
    return True


def read_page_state():
    """读取上次推送的页码状态"""
    try:
        if PAGE_STATE_FILE.exists():
            data = json.loads(PAGE_STATE_FILE.read_text(encoding="utf-8"))
            return data.get("page"), data.get("ts", 0)
    except Exception:
        pass
    return None, 0


def write_page_state(page):
    """记录本次推送的页码"""
    try:
        PAGE_STATE_FILE.write_text(
            json.dumps({"page": page, "ts": time.time()}), encoding="utf-8"
        )
    except Exception:
        pass


def main():
    global KINDLE_HOST
    log("=" * 50)
    log("开始刷新 dashboard")

    # 1. 生成 PNG + 计算页码（每30秒换页）
    png = render()
    page = get_page_for_time()
    log(f"已生成: {png} (第{page}/4页)")

    # 2. 查找 ssh/scp
    ssh_bin = find_bin("ssh")
    scp_bin = find_bin("scp")
    log(f"SSH: {ssh_bin}  SCP: {scp_bin}")

    # 3. 检测 Kindle 是否在线（ping only，快速路径，正常情况下每30秒都会执行）
    host = KINDLE_HOST
    online = ping_host(host)
    if online:
        log(f"✅ Kindle 在线: {host}")

    # 4. 推送 + 刷新。若ping失败，或ping通过但推送失败（可能是ping误判/端口配置问题/
    # 真正的DHCP换IP），才触发慢速的身份验证+局域网扫描路径，避免每次正常推送都
    # 额外增加一次SSH身份验证的开销。
    success = online and push_and_refresh(ssh_bin, scp_bin, host)

    if not success:
        if online:
            log(f"❌ 推送失败，Kindle IP 可能已失效 ({host})")
        else:
            log(f"❌ Kindle 不在线 ({host})")

        if AUTO_DISCOVER_IP:
            log("⏳ 尝试自动发现 Kindle 新IP（DHCP可能已重新分配地址）...")
            new_ip = discover_kindle_ip(ssh_bin, exclude_host=host)
            if new_ip:
                update_settings_ip(new_ip)
                host = new_ip
                KINDLE_HOST = new_ip
                log(f"✅ 使用新IP重新推送: {host}")
                success = push_and_refresh(ssh_bin, scp_bin, host)
            else:
                log("请确认 Kindle 已唤醒且 WiFi 已连，或在 settings.py 中手动更新 KINDLE_HOST")
                return 1
        else:
            log("请确认 Kindle 已唤醒且 WiFi 已连（AUTO_DISCOVER_IP 已关闭，不会自动扫描）")
            return 1

    if success:
        write_page_state(page)
        log("✅ 全部完成")
        return 0
    else:
        log("❌ 推送过程中出错")
        return 1


if __name__ == "__main__":
    sys.exit(main())
