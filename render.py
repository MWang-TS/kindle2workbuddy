# -*- coding: utf-8 -*-
"""kindle-dashboard 渲染引擎
用 Pillow 生成 600x800 灰度 PNG，针对 Kindle 8代 e-ink 屏优化。
布局：顶部状态栏 / 自动化任务 / 多项目进度 / 今日待办 / 底部刷新栏
"""
__version__ = "0.1.0"

import os
import sys
import json
import time
import sqlite3
import platform
import subprocess
import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Windows 隐藏子进程窗口标志（防止 ssh/tasklist 弹窗）
NO_WINDOW = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

# ── 常量 ──────────────────────────────────────────────
W, H = 600, 800          # Kindle 8代分辨率
BG = 255                 # 白底
FG = 0                   # 黑字
GRAY = 170               # 灰色（进度条/次要，兼容旧调用）
LIGHT_GRAY = 210         # 浅灰（分割线，兼容旧调用）
DARK_GRAY = 80           # 深灰（强调）

# 视觉系统 v1.3：统一卡片 / 圆角 / 网格
RADIUS = 12              # 卡片圆角
RADIUS_SM = 8            # 小圆角（chip/pill）
CARD_BG = 248            # 卡片浅底（几乎白，增加层次不糊字）
CARD_BORDER = 195        # 卡片描边
TRACK_GRAY = 224         # 进度条/环形图背景轨道
MARGIN = 20              # 页面左右边距
GRID = 8                 # 基础网格单位

# 垂直间距系统 v1.4：主标题段前距加大，段间/行间更宽松
HEADER_TO_SECTION = 20   # 顶部分割线 → 第一个主标题（原8px，加大）
SECTION_TO_SECTION = 22  # 上一区块内容结束 → 下一主标题（段前距，原约16-20px不等，统一加大）
TITLE_TO_CONTENT = 38    # 主标题 → 首行内容（原32-36px不等，统一加大）
ROW_SPACING = 36         # 简单label/value行间距（原32px，加大更透气）

FONT_DIR = "C:/Windows/Fonts"
FONT_REGULAR = os.path.join(FONT_DIR, "msyh.ttc")    # 微软雅黑
FONT_BOLD = os.path.join(FONT_DIR, "simhei.ttf")     # 黑体（粗）
FONT_LIGHT = os.path.join(FONT_DIR, "Deng.ttf")      # 等线

# 从 settings.py 读取配置（带默认值）
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from settings import *
except ImportError:
    pass

# 注意：getattr(globals(), ...) 是错误写法，globals()返回dict没有该属性，
# 会导致fallback永远生效。正确做法用 globals().get(name, fallback)。
DB_PATH = os.path.expanduser(globals().get('DB_PATH', "~/.workbuddy/workbuddy.db"))

# WorkBuddy 运行数据目录（任务对话记录、缓存等）
WORKBUDDY_DIR = str(Path(DB_PATH).parent)

# 项目目录
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_PNG = OUTPUT_DIR / "dashboard.png"


# ── 字体加载 ───────────────────────────────────────────
def font(size, bold=False):
    """加载字体，bold 用黑体，否则微软雅黑"""
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(FONT_LIGHT, size)


# ── 数据采集 ───────────────────────────────────────────
def get_automations():
    """从 workbuddy.db 读取自动化任务列表，按时间排序
    rrule 格式: 'FREQ=DAILY;BYHOUR=8;BYMINUTE=30'
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, status, schedule_type, rrule FROM automations "
            "WHERE status='ACTIVE' AND deleted_at IS NULL"
        ).fetchall()
        conn.close()

        def time_key(r):
            rr = r["rrule"] or ""
            hour = minute = 99
            for p in rr.split(";"):
                if p.startswith("BYHOUR="):
                    try:
                        hour = int(p.split("=")[1])
                    except ValueError:
                        pass
                elif p.startswith("BYMINUTE="):
                    try:
                        minute = int(p.split("=")[1])
                    except ValueError:
                        pass
            return hour * 60 + minute

        rows.sort(key=time_key)

        tasks = []
        now = dt.datetime.now()
        for r in rows:
            rrule = r["rrule"] or ""
            hour = minute = None
            for part in rrule.split(";"):
                if part.startswith("BYHOUR="):
                    hour = part.split("=")[1]
                elif part.startswith("BYMINUTE="):
                    minute = part.split("=")[1]
            time_str = f"{hour}:{minute.zfill(2)}" if hour else "--:--"
            task_hour = int(hour) if hour else 0
            task_min = int(minute) if minute else 0
            task_time = now.replace(hour=task_hour, minute=task_min, second=0)
            if now >= task_time:
                state = "done"
            else:
                state = "pending"
            tasks.append({
                "name": r["name"],
                "time": time_str,
                "state": state,
            })
        return tasks
    except Exception as e:
        return [{"name": "读取失败", "time": "--:--", "state": "error"}]


WEATHER_CACHE = BASE_DIR / "output" / ".weather_cache.json"
WEATHER_TTL = 600  # 缓存10分钟


def get_weather():
    """从 wttr.in 获取天气（城市见 settings.py 的 WEATHER_CITY），失败则使用缓存"""
    # 先尝试读缓存
    try:
        if WEATHER_CACHE.exists():
            data = json.loads(WEATHER_CACHE.read_text(encoding="utf-8"))
            if dt.datetime.now().timestamp() - data.get("ts", 0) < WEATHER_TTL:
                return data.get("text", "天气 --")
    except Exception:
        pass

    # 网络请求
    try:
        import requests
        r = requests.get(
            "https://wttr.in/" + WEATHER_CITY + "?format=%C+%t",
            timeout=5,
            headers={"User-Agent": "curl/8.0"},
        )
        if r.status_code == 200:
            text = r.text.strip().replace("+", "")
            parts = text.split()
            temp = ""
            cond = ""
            for p in parts:
                if "°" in p:
                    temp = p
                else:
                    cond = (cond + " " + p).strip()
            cond_cn = {
                "Clear": "晴", "Sunny": "晴", "Partly cloudy": "多云",
                "Cloudy": "阴", "Overcast": "阴", "Light rain": "小雨",
                "Rain": "雨", "Mist": "雾", "Fog": "雾",
            }.get(cond, cond[:4] if cond else "")
            result = f"{cond_cn} {temp}"
            # 写缓存
            try:
                WEATHER_CACHE.write_text(
                    json.dumps({"ts": dt.datetime.now().timestamp(), "text": result}),
                    encoding="utf-8",
                )
            except Exception:
                pass
            return result
    except Exception:
        pass

    # 兜底：缓存里的旧值（即使过期）
    try:
        if WEATHER_CACHE.exists():
            data = json.loads(WEATHER_CACHE.read_text(encoding="utf-8"))
            return data.get("text", "天气 --")
    except Exception:
        pass
    return "天气 --"


def get_system_info():
    """获取磁盘空间等系统信息"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(DISK_PATH)
        pct = used / total * 100
        return f"E:{pct:.0f}%"
    except Exception:
        return "E:--"


# WorkBuddy 目录大小缓存（遍历 2.8GB 目录较慢，10 分钟缓存一次）
_wb_usage_cache = {"ts": 0, "size": 0}


def get_workbuddy_usage(cache_seconds=600):
    """统计 WorkBuddy 运行目录占用 + 所在磁盘（C盘）用量

    返回: {size, size_gb, pct, disk_total, disk_used, disk_free}
    """
    global _wb_usage_cache
    import shutil
    now = time.time()
    # 目录大小带缓存
    if now - _wb_usage_cache["ts"] > cache_seconds or _wb_usage_cache["size"] == 0:
        total = 0
        for dirpath, dirnames, filenames in os.walk(WORKBUDDY_DIR):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        _wb_usage_cache = {"ts": now, "size": total}
    size = _wb_usage_cache["size"]
    # 磁盘：workbuddy 所在盘
    disk_root = os.path.splitdrive(WORKBUDDY_DIR)[0] + os.sep
    try:
        dt_total, dt_used, dt_free = shutil.disk_usage(disk_root)
    except Exception:
        dt_total, dt_used, dt_free = 0, 0, 0
    return {
        "size": size,
        "size_gb": size / 1024**3,
        "pct": size / dt_total * 100 if dt_total else 0,
        "disk_total": dt_total,
        "disk_used": dt_used,
        "disk_free": dt_free,
    }


def get_kindle_status():
    """通过 SSH 获取 Kindle 电量和 WiFi 信号"""
    import subprocess
    try:
        ssh_cmd = [
            "ssh",
            "-i", os.path.expanduser(SSH_KEY),
            "-p", str(globals().get('KINDLE_PORT', 22)),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=5",
            "root@" + KINDLE_HOST,
            "echo BATT=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null); "
            "echo WIFI=$(lipc-get-prop com.lab126.wifid cmSignalStrength 2>/dev/null)"
        ]
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        batt = wifi = "--"
        for line in r.stdout.split("\n"):
            if line.startswith("BATT="):
                val = line.split("=")[1].strip()
                if val.isdigit():
                    batt = f"{val}%"
            elif line.startswith("WIFI="):
                val = line.split("=")[1].strip()
                if val and val != "N/A":
                    wifi = f"{val}dBm"
        return f"K:{batt} W:{wifi}"
    except Exception:
        return "K:-- W:--"


def get_now_str():
    now = dt.datetime.now()
    weekday_cn = "周" + "一二三四五六日"[now.weekday()]
    return {
        "date": f"{now.month}月{now.day}日 {weekday_cn}",
        "time": now.strftime("%H:%M"),
        "full": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 绘制工具 ───────────────────────────────────────────
def draw_card(draw, x, y, w, h, fill=CARD_BG, outline=CARD_BORDER, radius=RADIUS):
    """绘制圆角卡片（浅底+描边）"""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=outline, width=1)


def draw_progress_bar(draw, x, y, w, h, pct, fill_gray=GRAY):
    """绘制进度条（兼容旧版，新版用draw_progress_bar_v2）"""
    draw.rectangle([x, y, x + w, y + h], outline=FG, width=1)
    fill_w = int(w * pct / 100)
    if fill_w > 1:
        draw.rectangle([x + 1, y + 1, x + fill_w, y + h - 1], fill=fill_gray)


def draw_progress_bar_v2(draw, x, y, w, h, pct, radius=RADIUS_SM):
    """绘制圆角进度条（新版，轨道灰+黑填充）"""
    # 背景轨道
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=TRACK_GRAY)
    # 前景填充
    fill_w = int(w * pct / 100)
    if fill_w > radius * 2:  # 至少要能画出圆角
        draw.rounded_rectangle([x, y, x + fill_w, y + h], radius=radius, fill=FG)


def draw_status_icon(draw, x, y, state, size=16):
    """绘制状态图标（用几何形状代替emoji）
    state: 'done'完成 / 'pending'待处理 / 'running'进行中 / 'error'错误
    """
    cx, cy = x + size // 2, y + size // 2
    r = size // 2 - 2
    if state == 'done':
        # 实心圆●
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FG)
    elif state == 'pending':
        # 空心圆○
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=FG, width=2)
    elif state == 'running':
        # 实心菱形◆
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        draw.polygon(pts, fill=FG)
    elif state == 'error':
        # 叉号×
        draw.line([(cx - r, cy - r), (cx + r, cy + r)], fill=FG, width=3)
        draw.line([(cx - r, cy + r), (cx + r, cy - r)], fill=FG, width=3)


def draw_badge(draw, x, y, text, fnt, bg=DARK_GRAY, fg=BG):
    """绘制小徽章/pill（深底白字，圆角）"""
    tb = draw.textbbox((0, 0), text, font=fnt)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    pad = 6
    draw.rounded_rectangle(
        [x, y, x + tw + pad * 2, y + th + pad * 2],
        radius=RADIUS_SM,
        fill=bg
    )
    draw.text((x + pad, y + pad), text, font=fnt, fill=fg)


def get_session_summary():
    """会话统计：今日会话数 / 正在执行数 / 今日消耗 credit"""
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        now_dt = dt.datetime.now()
        today_start_ms = int(dt.datetime(now_dt.year, now_dt.month, now_dt.day).timestamp() * 1000)

        today_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE is_playground=1 AND deleted_at IS NULL "
            "AND updated_at >= ?", (today_start_ms,)
        ).fetchone()[0]

        running_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE is_playground=1 AND deleted_at IS NULL "
            "AND status IN ('working','running','Pending','processing','queued')"
        ).fetchone()[0]

        total_credit = 0
        for r in conn.execute(
            "SELECT su.credit_json, su.used FROM sessions s "
            "LEFT JOIN session_usage su ON s.id = su.session_id "
            "WHERE s.is_playground=1 AND s.deleted_at IS NULL AND s.updated_at >= ?",
            (today_start_ms,),
        ):
            c = sum_credit(r["credit_json"]) or 0
            total_credit += c

        conn.close()
        return today_count, running_count, total_credit
    except Exception:
        return 0, 0, 0


def draw_donut(draw, cx, cy, r, pct, width=13, show_pct=True):
    """绘制环形图（donut）：从12点方向顺时针显示 pct%
    pct: 0-100；中心显示百分比数字
    """
    bbox = [cx - r, cy - r, cx + r, cy + r]
    # 背景环（浅灰轨道，与卡片/进度条统一视觉语言）
    draw.arc(bbox, start=0, end=360, fill=TRACK_GRAY, width=width)
    # 前景弧（黑，从12点270°顺时针）
    if pct > 1:
        end_angle = (270 + 360 * pct / 100) % 360
        draw.arc(bbox, start=270, end=end_angle, fill=FG, width=width)
    # 中心百分比（字号放大 19→22）
    if show_pct:
        f_num = font(22, bold=True)
        text = f"{pct:.0f}%"
        tb = draw.textbbox((0, 0), text, font=f_num)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((cx - tw / 2, cy - th / 2 - tb[1]), text, font=f_num, fill=FG)


def draw_section_title(draw, text, y, fnt, x=MARGIN, subtitle=None, f_sub=None):
    """区块标题：左侧竖线强调条 + 标题 + 细分割线（统一四页视觉语言）
    subtitle: 右对齐的补充说明文字（如"共4项"），可选
    保持与旧版一致的垂直节奏：分割线固定在 y+26（旧版为 y+24），
    不依赖字体实际高度，避免影响下游内容的固定偏移量。
    """
    # 左侧强调竖线（4px宽，18px高，视觉上贴合22px粗体标题）
    draw.rounded_rectangle([x, y + 3, x + 4, y + 21], radius=2, fill=FG)
    draw.text((x + 12, y), text, font=fnt, fill=FG)
    if subtitle and f_sub:
        stb = draw.textbbox((0, 0), subtitle, font=f_sub)
        sw = stb[2] - stb[0]
        draw.text((W - MARGIN - sw, y + 4), subtitle, font=f_sub, fill=DARK_GRAY)
    draw.line([(x, y + 26), (W - MARGIN, y + 26)], fill=LIGHT_GRAY, width=1)


# ── 主渲染入口（路由）──────────────────────────────────
def render():
    """主入口：根据当前时间选择页码（每3分钟换一页，4页循环）"""
    page = get_page_for_time()
    return render_page(page)


def next_refresh():
    """下次刷新时间（秒级）"""
    n = dt.datetime.now() + dt.timedelta(seconds=30)
    return n.strftime("%H:%M:%S")


# ── 页码路由 ───────────────────────────────────────────
def get_page_for_time():
    """根据当天秒数决定页码（每 PAGE_DURATION 秒换一页，4 页循环）

    PAGE_DURATION 默认 120 秒（2 分钟），4 页共 8 分钟一轮。
    推送间隔 30 秒，每页被推送 4 次。
    """
    now = dt.datetime.now()
    total_seconds = now.hour * 3600 + now.minute * 60 + now.second
    return (total_seconds // PAGE_DURATION) % 4 + 1  # 1-4


def render_page(page_num):
    """根据页码渲染对应页面"""
    if page_num == 1:
        return render_page1()
    elif page_num == 2:
        return render_page2()
    elif page_num == 3:
        return render_page3()
    else:
        return render_page4()


# ── 页1: 主 dashboard ──────────────────────────────────
def render_page1():
    """主 dashboard：时间天气/自动化任务/会话总览/系统占用"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    automations = get_automations()
    weather = get_weather()
    sys_info = get_system_info()

    sys.path.insert(0, str(BASE_DIR))
    from config import SHORT_NAME

    f_section = font(25, bold=True)  # 标题 22→25
    f_body = font(20)                 # 正文 17→20
    f_small = font(17)                # 次要 15→17
    f_tiny = font(15)                 # 辅助 13→15
    f_clock = font(40, bold=True)     # 大时钟 36→40

    # ═══ 顶部：时间 + 天气 ═══
    draw.text((MARGIN, 12), now["date"], font=font(23, bold=True), fill=FG)  # 20→23
    draw.text((MARGIN, 34), now["time"], font=f_clock, fill=FG)
    # 右侧天气卡片（加宽至144px容纳放大后的文字）
    wx, wy = W - 164, 12
    draw_card(draw, wx, wy, 144, 56, radius=RADIUS_SM)
    draw.text((wx + 12, wy + 8), weather, font=f_body, fill=FG)
    draw.text((wx + 12, wy + 32), WEATHER_CITY_CN, font=f_small, fill=DARK_GRAY)
    # 页码标记
    draw.text((W - MARGIN - 24, 12), "1/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 84), (W, 84)], fill=FG, width=2)

    # ═══ 自动化任务 4 卡片（圆角卡片 + 状态图标）═══
    y_sec1 = 84 + HEADER_TO_SECTION  # 原92，改用间距常量
    draw_section_title(draw, "自动化任务", y_sec1, f_section, subtitle=f"共{len(automations[:4])}项", f_sub=f_tiny)
    if not automations:
        automations = [{"name": "无活跃任务", "time": "--:--", "state": "idle"}]
    
    card_x = MARGIN
    card_w = 134
    card_h = 78  # 76→78，放大后文字略需更多高度
    card_y = y_sec1 + TITLE_TO_CONTENT  # 原36，改用间距常量
    gap = 8
    
    for i, task in enumerate(automations[:4]):
        cx = card_x + i * (card_w + gap)
        cy = card_y
        # 圆角卡片
        draw_card(draw, cx, cy, card_w, card_h)
        
        # 任务名称（字号放大 16→18）
        name = SHORT_NAME.get(task["name"], task["name"])
        if len(name) > 8:
            name = name[:7] + "…"
        draw.text((cx + 10, cy + 10), name, font=font(18, bold=True), fill=FG)
        
        # 计划时间
        draw.text((cx + 10, cy + 36), task["time"], font=f_small, fill=DARK_GRAY)
        
        # 状态图标 + 文字
        state_map = {"done": "done", "pending": "pending", "error": "error"}
        state = state_map.get(task["state"], "pending")
        draw_status_icon(draw, cx + 10, cy + 56, state, size=14)
        if state == "done":
            mark = "已执行"
        elif state == "pending":
            mark = "待执行"
        else:
            mark = "异常"
        draw.text((cx + 30, cy + 54), mark, font=f_small, fill=FG if state != "pending" else DARK_GRAY)

    # ═══ 会话总览（数字卡片）═══
    today_count, running_count, total_credit = get_session_summary()
    y_sec2 = card_y + card_h + SECTION_TO_SECTION  # 动态计算，原固定220
    draw_section_title(draw, "会话总览", y_sec2, f_section)
    y = y_sec2 + TITLE_TO_CONTENT  # 原36，改用间距常量
    
    items = [
        ("今日会话", f"{today_count}"),
        ("正在执行", f"{running_count}"),
        ("今日消耗", fmt_credit(total_credit)),
    ]
    for label, val in items:
        draw.text((MARGIN + 4, y), label, font=f_body, fill=DARK_GRAY)
        draw.text((160, y), val, font=font(23, bold=True), fill=FG)  # 20→23 数值加粗放大
        y += ROW_SPACING  # 原32，改用间距常量

    # ═══ WorkBuddy 系统占用 ═══
    y_sec3 = y + SECTION_TO_SECTION  # 动态计算，原固定350
    draw_section_title(draw, "系统占用", y_sec3, f_section)
    wb = get_workbuddy_usage()
    y = y_sec3 + TITLE_TO_CONTENT  # 原36，改用间距常量
    
    items = [
        (".workbuddy", f"{wb['size_gb']:.2f} GB"),
        ("占磁盘总空间", f"{wb['pct']:.2f}%"),
        ("磁盘已用", f"{wb['disk_used']/1024**3:.1f} GB"),
        ("磁盘可用", f"{wb['disk_free']/1024**3:.1f} GB"),
    ]
    for label, val in items:
        draw.text((MARGIN + 4, y), label, font=f_body, fill=DARK_GRAY)
        draw.text((240, y), val, font=f_body, fill=FG)
        y += ROW_SPACING  # 原32，改用间距常量
    
    # 磁盘使用率进度条（新版圆角）
    disk_pct = wb["disk_used"] / wb["disk_total"] * 100 if wb["disk_total"] else 0
    draw_progress_bar_v2(draw, MARGIN, y + 8, 400, 20, disk_pct)
    draw.text((440, y + 10), f"{disk_pct:.0f}%", font=f_small, fill=FG)

    # 底部
    draw_footer(draw, now, sys_info)

    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页2: 系统详情 ──────────────────────────────────────
def render_page2():
    """系统详情：电脑磁盘环形图 / Kindle状态 / 下次运行倒计时"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()

    f_section = font(25, bold=True)  # 22→25
    f_body = font(20)                 # 17→20
    f_small = font(17)                # 15→17
    f_tiny = font(15)                 # 13→15
    f_clock = font(40, bold=True)     # 36→40

    # ═══ 顶部 ═══
    draw.text((MARGIN, 12), "系统状态", font=font(23, bold=True), fill=FG)  # 20→23
    draw.text((MARGIN, 34), now["time"], font=f_clock, fill=FG)
    wx, wy = W - 164, 12
    draw_card(draw, wx, wy, 144, 56, radius=RADIUS_SM)
    draw.text((wx + 12, wy + 8), sys_info, font=f_body, fill=FG)
    draw.text((wx + 12, wy + 32), "电脑磁盘", font=f_small, fill=DARK_GRAY)
    draw.text((W - MARGIN - 24, 12), "2/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 84), (W, 84)], fill=FG, width=2)

    # ═══ 电脑状态（三环形图，卡片承载）═══
    y_sec1 = 84 + HEADER_TO_SECTION  # 原92，改用间距常量
    draw_section_title(draw, "电脑状态", y_sec1, f_section)
    pc_info = get_pc_detail()
    card_top = y_sec1 + TITLE_TO_CONTENT  # 原36，改用间距常量
    card_h1 = 151  # 原138，放大字号后label+text溢出卡片，紧凑padding方案修正
    draw_card(draw, MARGIN, card_top, W - 2 * MARGIN, card_h1)
    # 三环形图中心位置，cy_offset=57.5确保顶部padding=12px，底部文字不溢出
    donut_positions = [(150, card_top + 58), (300, card_top + 58), (450, card_top + 58)]
    for i, (label, pct, text) in enumerate(pc_info[:3]):
        cx, cy = donut_positions[i]
        if pct > 0:
            draw_donut(draw, cx, cy, 40, pct, width=11)
        else:
            draw.text((cx - 20, cy - 10), text, font=f_body, fill=FG)
        draw.text((cx - 14, cy + 50), label, font=font(17, bold=True), fill=FG)  # 原cy+48，调整cy+50
        draw.text((cx - 28, cy + 68), text, font=f_tiny, fill=DARK_GRAY)  # 保持cy+68

    # ═══ Kindle 状态 ═══
    sec_y = card_top + card_h1 + SECTION_TO_SECTION  # 原+20，改用间距常量
    draw_section_title(draw, "Kindle 状态", sec_y, f_section)
    kindle_info = get_kindle_detail()
    card_top2 = sec_y + TITLE_TO_CONTENT  # 原36，改用间距常量
    # 动态计算卡片高度：电量行56px，其余每行30px，上下各留14px padding
    row_heights = [56 if (pct is not None and pct > 0) else 30 for _, pct, _ in kindle_info]
    card_h2 = sum(row_heights) + 28
    draw_card(draw, MARGIN, card_top2, W - 2 * MARGIN, card_h2)
    y = card_top2 + 14
    for label, pct, text in kindle_info:
        if pct is not None and pct > 0:
            draw_donut(draw, MARGIN + 44, y + 24, 30, pct, width=9)
            draw.text((MARGIN + 96, y + 12), label, font=font(18, bold=True), fill=FG)  # 16→18
            draw.text((MARGIN + 96, y + 36), text, font=f_tiny, fill=DARK_GRAY)
            y += 56
        else:
            draw.text((MARGIN + 12, y), label, font=f_body, fill=DARK_GRAY)
            draw.text((MARGIN + 150, y), text, font=f_body, fill=FG)
            y += 30

    # ═══ 自动化任务下次运行倒计时 ═══
    sec_y3 = card_top2 + card_h2 + SECTION_TO_SECTION  # 原+20，改用间距常量
    draw_section_title(draw, "下次运行倒计时", sec_y3, f_section)
    automations = get_automations()
    y = sec_y3 + TITLE_TO_CONTENT  # 原36，改用间距常量
    now_dt = dt.datetime.now()
    n_tasks = min(len(automations), 4) or 1
    # 动态压缩行高：footer分割线在y=720，预留10px安全边距，避免任务数增多时溢出
    available = 710 - y
    row_h = max(30, min(44, int(available / n_tasks))) if available > 0 else 30
    for task in automations[:4]:
        rrule_str = task.get("time", "--:--")
        try:
            h, m = rrule_str.split(":")
            task_time = now_dt.replace(hour=int(h), minute=int(m), second=0)
            if task_time <= now_dt:
                task_time += dt.timedelta(days=1)
                day_label = "明天"
            else:
                day_label = "今天"
            delta = task_time - now_dt
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            count = f"{hours}h{mins}m"
        except Exception:
            count = "--"
            day_label = "?"
        # 行卡片
        draw_card(draw, MARGIN, y, W - 2 * MARGIN, row_h - 8, radius=RADIUS_SM)
        name = task["name"]
        if len(name) > 12:
            name = name[:11] + "…"
        draw.text((MARGIN + 12, y + 12), name, font=f_body, fill=FG)
        draw.text((260, y + 13), f"{day_label} {rrule_str}", font=f_small, fill=DARK_GRAY)
        # 倒计时用徽章突出
        draw_badge(draw, W - MARGIN - 78, y + 6, count, f_small)
        y += row_h

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页3: 日历视图 ──────────────────────────────────────
def render_page3():
    """日历视图：超大时钟+农历 / 本月日历（今天高亮，周末浅底区分）"""
    import calendar

    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()
    today = dt.datetime.now()
    weather = get_weather()  # 页3也需要天气信息，在函数开头获取

    f_small = font(17)                # 15→17
    f_tiny = font(15)                 # 13→15
    f_body = font(20)                 # 页3新增f_body用于天气显示
    f_xxl = font(80, bold=True)       # 超大时钟 72→80
    f_day = font(21, bold=True)       # 日历日期 19→21
    f_lunar_day = font(21, bold=True)

    # ═══ 上 1/3：大数字时钟 + 日期 + 农历 ═══
    now_dt = dt.datetime.now()
    lunar_info = get_lunar(now_dt.year, now_dt.month, now_dt.day)
    gan = "甲乙丙丁戊己庚辛壬癸"[(lunar_info[0] - 4) % 10]
    zhi = "子丑寅卯辰巳午未申酉戌亥"[(lunar_info[0] - 4) % 12]
    lunar_str = f"{gan}{zhi}年 {('闰' if lunar_info[2] else '')}{LUNAR_MON_CN[lunar_info[1]]}月{LUNAR_DAY_CN[lunar_info[3]]}"

    # 页码
    draw.text((W - MARGIN - 24, 14), "3/4", font=f_tiny, fill=DARK_GRAY)

    # 超大时间居中
    time_str = now["time"]
    time_bbox = draw.textbbox((0, 0), time_str, font=f_xxl)
    time_w = time_bbox[2] - time_bbox[0]
    draw.text(((W - time_w) / 2, 26), time_str, font=f_xxl, fill=FG)

    # 天气信息（时钟下方居中显示）
    weather_text = f"{WEATHER_CITY_CN} · {weather}"
    tb_weather = draw.textbbox((0, 0), weather_text, font=f_body)
    weather_w = tb_weather[2] - tb_weather[0]
    draw.text(((W - weather_w) / 2, 112), weather_text, font=f_body, fill=DARK_GRAY)

    # 日期（左）+ 农历徽章（右），同一行，视觉更紧凑统一
    draw.text((MARGIN, 168), now["date"], font=font(21, bold=True), fill=FG)
    # 农历徽章动态计算宽度右对齐
    badge_text = "农历 " + lunar_str
    tb_badge = draw.textbbox((0, 0), badge_text, font=f_small)
    badge_w = tb_badge[2] - tb_badge[0] + 12  # 文字宽度+padding
    draw_badge(draw, W - MARGIN - badge_w, 166, badge_text, f_small, bg=FG, fg=BG)
    draw.line([(0, 214), (W, 214)], fill=FG, width=2)

    # ═══ 下 2/3：紧凑日历（含农历，卡片承载）═══
    grid_x = MARGIN
    grid_y = 214 + HEADER_TO_SECTION  # 原230(gap16)，改用间距常量(gap20)，与其它页头部留白统一
    cell_w = (W - 2 * MARGIN) // 7   # 80
    cell_h = 68
    days_cn = ["一", "二", "三", "四", "五", "六", "日"]

    # 星期头（周末用深灰突出区分）
    for i, d in enumerate(days_cn):
        col = DARK_GRAY if i >= 5 else FG
        tb = draw.textbbox((0, 0), d, font=f_small)
        tw = tb[2] - tb[0]
        draw.text((grid_x + i * cell_w + (cell_w - tw) / 2, grid_y), d, font=f_small, fill=col)

    cal = calendar.Calendar(firstweekday=0)  # 周一开头
    month_days = cal.monthdayscalendar(today.year, today.month)
    cal_y = grid_y + 34  # 原+30，加大星期头到首行日期的间距，更透气
    cell_gap = 4
    for week_idx, week in enumerate(month_days):
        for day_idx, day in enumerate(week):
            if day == 0:
                continue
            x = grid_x + day_idx * cell_w
            y = cal_y + week_idx * cell_h
            cw, ch = cell_w - cell_gap, cell_h - cell_gap
            lunar_txt = lunar_day_short(today.year, today.month, day)
            is_weekend = day_idx >= 5

            if day == today.day:
                # 今天：黑底圆角高亮
                draw.rounded_rectangle([x, y, x + cw, y + ch], radius=RADIUS_SM, fill=FG)
                day_col, lunar_col = BG, BG
            elif is_weekend:
                # 周末：浅灰圆角底，区别于工作日
                draw.rounded_rectangle([x, y, x + cw, y + ch], radius=RADIUS_SM, fill=CARD_BG, outline=CARD_BORDER, width=1)
                day_col, lunar_col = DARK_GRAY, DARK_GRAY
            else:
                day_col, lunar_col = FG, DARK_GRAY

            draw.text((x + 12, y + 6), str(day), font=f_day, fill=day_col)
            draw.text((x + 10, y + 32), lunar_txt[:4], font=f_tiny, fill=lunar_col)

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页4: 任务执行状态 ────────────────────────────────
def render_page4():
    """当前会话信息：正在执行的对话会话详情 / 最近结束的会话列表"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()
    running, recent = get_task_status()

    f_section = font(25, bold=True)  # 22→25
    f_body = font(20)                 # 17→20
    f_small = font(17)                # 15→17
    f_tiny = font(15)                 # 13→15
    f_clock = font(40, bold=True)     # 36→40

    # ═══ 顶部 ═══
    draw.text((MARGIN, 12), "当前会话信息", font=font(23, bold=True), fill=FG)  # 20→23
    draw.text((MARGIN, 34), now["time"], font=f_clock, fill=FG)
    draw.text((W - MARGIN - 24, 12), "4/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 84), (W, 84)], fill=FG, width=2)

    # ═══ 区块1: 正在执行（卡片承载，几何图标代替emoji）═══
    y_sec1 = 84 + HEADER_TO_SECTION  # 原92，改用间距常量
    draw_section_title(draw, "正在执行", y_sec1, f_section)
    card_top = y_sec1 + TITLE_TO_CONTENT  # 原36，改用间距常量
    if running:
        task = running[0]
        card_h1 = 158
        draw_card(draw, MARGIN, card_top, W - 2 * MARGIN, card_h1)

        name = task["name"]
        if len(name) > 17:
            name = name[:16] + "…"
        draw.text((MARGIN + 14, card_top + 14), name, font=font(23, bold=True), fill=FG)  # 20→23

        # 状态图标（菱形=运行中）+ 文字 + 模型徽章
        draw_status_icon(draw, MARGIN + 14, card_top + 48, "running", size=16)
        draw.text((MARGIN + 36, card_top + 46), "执行中", font=f_body, fill=FG)
        draw_badge(draw, MARGIN + 118, card_top + 42, task["model"], f_small)

        run_mins = int((dt.datetime.now() - task["start"]).total_seconds() / 60)
        draw.text((MARGIN + 14, card_top + 78),
                  "开始 %s   已运行 %d 分钟" % (task["start"].strftime("%H:%M"), run_mins),
                  font=f_body, fill=DARK_GRAY)

        # 消耗：自定义模型显示 Token（used），标准模型显示 Credit（credit_json 实际值）
        if task["is_custom"]:
            usage_text = "Token " + fmt_token(task["token"])
            if task["credit"] is not None:
                usage_text += "  ·  Credit " + fmt_credit(task["credit"])
        else:
            usage_text = "Credit " + fmt_credit(task["credit"])
        draw.text((MARGIN + 14, card_top + 106), usage_text, font=font(20, bold=True), fill=FG)  # 17→20

        cwd = task["cwd"]
        if cwd:
            if len(cwd) > 34:
                cwd = "…" + cwd[-32:]
            draw.text((MARGIN + 14, card_top + 134), cwd, font=f_tiny, fill=DARK_GRAY)
    else:
        card_h1 = 60
        draw_card(draw, MARGIN, card_top, W - 2 * MARGIN, card_h1)
        draw_status_icon(draw, MARGIN + 14, card_top + 20, "pending", size=16)
        draw.text((MARGIN + 38, card_top + 18), "当前无执行中的会话", font=f_body, fill=DARK_GRAY)

    # ═══ 区块2: 最近会话（每条一张圆角卡片，状态图标代替emoji）═══
    sec_r = card_top + card_h1 + SECTION_TO_SECTION  # 原+20，改用间距常量
    draw_section_title(draw, "最近会话", sec_r, f_section)
    y = sec_r + TITLE_TO_CONTENT  # 原36，改用间距常量
    if recent:
        items = recent[:3]
        # 动态压缩行高，避免超出footer(720)
        available = 710 - y
        row_h = max(64, min(84, int(available / len(items)))) if available > 0 else 64
        for item in items:
            draw_card(draw, MARGIN, y, W - 2 * MARGIN, row_h - 8, radius=RADIUS_SM)
            inner_y = y + 10

            # 状态图标（●完成 / ×失败）+ 时间
            state = "done" if item["result"] == 1 else "error"
            draw_status_icon(draw, MARGIN + 12, inner_y + 2, state, size=14)
            draw.text((MARGIN + 34, inner_y), fmt_time(item["time"]), font=f_tiny, fill=DARK_GRAY)

            # 会话名称（黑字，右对齐留出图标位）
            name = item["name"]
            if len(name) > 20:
                name = name[:19] + "…"
            draw.text((MARGIN + 100, inner_y), name, font=font(18, bold=True), fill=FG)  # 16→18

            # 第二行：模型徽章（左） + 用量（右对齐，避免模型名过长时重叠）
            draw_badge(draw, MARGIN + 12, inner_y + 24, item["model"], f_tiny, bg=CARD_BORDER, fg=FG)
            if item["is_custom"]:
                usage_text = "Token " + fmt_token(item["token"])
                if item["credit"] is not None:
                    usage_text += "  Credit " + fmt_credit(item["credit"])
            else:
                usage_text = "Credit " + fmt_credit(item["credit"])
            utb = draw.textbbox((0, 0), usage_text, font=f_small)
            uw = utb[2] - utb[0]
            draw.text((W - MARGIN - 12 - uw, inner_y + 26), usage_text, font=f_small, fill=DARK_GRAY)

            y += row_h
    else:
        draw_card(draw, MARGIN, y, W - 2 * MARGIN, 50, radius=RADIUS_SM)
        draw.text((MARGIN + 14, y + 14), "暂无已结束的会话", font=f_body, fill=DARK_GRAY)

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 辅助函数 ───────────────────────────────────────────
def get_task_status():
    """获取会话执行状态（仅对话会话，不含自动化任务）：
    - running: 正在执行的对话会话
    - recent:  刚刚结束的对话会话（防空状态）
    """
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 正在执行的对话会话
        running = []
        for s in conn.execute(
            "SELECT s.custom_title, s.title, s.model, s.status, s.updated_at, s.created_at, s.cwd, s.expert_id, su.credit_json, su.used "
            "FROM sessions s "
            "LEFT JOIN session_usage su ON s.id = su.session_id "
            "WHERE s.deleted_at IS NULL "
            "AND s.is_playground=1 "
            "AND (s.custom_title IS NOT NULL OR s.title IS NOT NULL) "
            "AND s.status IN ('working','running','Pending','processing','queued') "
            "ORDER BY s.updated_at DESC LIMIT 3"
        ):
            running.append({
                "name": s["custom_title"] or s["title"] or "未命名会话",
                "model": simplify_model(s["model"]),
                "is_custom": is_custom_model(s["model"]),
                "credit": sum_credit(s["credit_json"]),   # 真实 credit（credit_json 求和），无则 None
                "token": s["used"] or 0,                  # 用量/token（used 字段）
                "status": s["status"],
                "start": dt.datetime.fromtimestamp((s["created_at"] or 0) / 1000),
                "cwd": s["cwd"] or "",
                "expert": s["expert_id"] or "",
                "time": dt.datetime.fromtimestamp(s["updated_at"] / 1000),
            })

        # 刚刚结束的对话会话（防空状态）
        recent = []
        for s in conn.execute(
            "SELECT s.custom_title, s.title, s.model, s.status, s.updated_at, su.credit_json, su.used "
            "FROM sessions s "
            "LEFT JOIN session_usage su ON s.id = su.session_id "
            "WHERE s.deleted_at IS NULL "
            "AND s.is_playground=1 "
            "AND (s.custom_title IS NOT NULL OR s.title IS NOT NULL) "
            "AND s.status IN ('completed','failed') "
            "ORDER BY s.updated_at DESC LIMIT 5"
        ):
            recent.append({
                "name": s["custom_title"] or s["title"] or "未命名会话",
                "model": simplify_model(s["model"]),
                "is_custom": is_custom_model(s["model"]),
                "credit": sum_credit(s["credit_json"]),   # 真实 credit，无则 None
                "token": s["used"] or 0,                  # 用量/token
                "result": 1 if s["status"] == "completed" else 0,
                "time": dt.datetime.fromtimestamp(s["updated_at"] / 1000),
            })

        conn.close()
        return running, recent
    except Exception:
        return [], []


def simplify_model(m):
    """简化模型名：custom-local:deepseek-v4-flash → deepseek-v4-flash"""
    if not m:
        return "--"
    return m.split(":")[-1] if ":" in m else m


def is_custom_model(m):
    """是否为自定义/本地模型（custom-local 前缀）"""
    return bool(m and str(m).startswith("custom-local"))


def fmt_token(n):
    """格式化 token 用量：158404 → 158.4K"""
    if not n:
        return "--"
    try:
        n = float(n)
        if n >= 1000000:
            return f"{n/1000000:.1f}M"
        if n >= 1000:
            return f"{n/1000:.1f}K"
        return f"{n:.0f}"
    except (TypeError, ValueError):
        return "--"


def fmt_credit(v):
    """格式化真实 credit：2024.82 → 2024.8（保留实际数值，不用 K 缩写）"""
    if v is None:
        return "--"
    try:
        v = float(v)
        if v >= 1000000:
            return f"{v/1000000:.2f}M"
        if v >= 10000:
            return f"{v/1000:.1f}K"
        if v >= 100:
            return f"{v:.1f}"
        return f"{v:.2f}" if v != int(v) else f"{v:.0f}"
    except (TypeError, ValueError):
        return "--"


# ── 农历计算（1900-2100，内置算法）─────────────────────
LUNAR_DATA = [
0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,
0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,
0x06ca0,0x0b550,0x15355,0x04da0,0x0a5b0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0,
0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b6a0,0x195a6,
0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x05ac0,0x0ab60,0x096d5,0x092e0,
0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06b20,0x1a6c4,0x0aae0,
0x092e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,
0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,
0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,
0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a2d0,0x0d150,0x0f252,
0x0d520]

LUNAR_MON_CN = ['', '正', '二', '三', '四', '五', '六', '七', '八', '九', '十', '冬', '腊']
LUNAR_DAY_CN = ['', '初一', '初二', '初三', '初四', '初五', '初六', '初七', '初八', '初九', '初十',
                '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
                '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '三十']


def _lunar_leap_month(y):
    return LUNAR_DATA[y - 1900] & 0xF


def _lunar_leap_days(y):
    if _lunar_leap_month(y) == 0:
        return 0
    return 30 if (LUNAR_DATA[y - 1900] & 0x10000) else 29


def _lunar_month_days(y, m):
    return 29 + ((LUNAR_DATA[y - 1900] >> (16 - m)) & 1)


def _lunar_year_days(y):
    return sum(_lunar_month_days(y, m) for m in range(1, 13)) + _lunar_leap_days(y)


def get_lunar(y, m, d):
    """公历 y-m-d → 农历 (年份, 月份, 是否闰月, 日)"""
    offset = (dt.date(y, m, d) - dt.date(1900, 1, 31)).days
    ly = 1900
    while offset >= _lunar_year_days(ly):
        offset -= _lunar_year_days(ly)
        ly += 1
    mi = 1
    is_leap = False
    while mi <= 12:
        lm = _lunar_leap_month(ly)
        if lm > 0 and mi == lm + 1:
            if offset < _lunar_leap_days(ly):
                is_leap = True
                mi = lm
                break
            offset -= _lunar_leap_days(ly)
        if offset < _lunar_month_days(ly, mi):
            break
        offset -= _lunar_month_days(ly, mi)
        mi += 1
    return ly, mi, is_leap, offset + 1


def lunar_day_short(y, m, d):
    """返回农历简短表示：初一显示月份（如'六月'），其余显示日（如'廿三'）"""
    _, lm, is_leap, ld = get_lunar(y, m, d)
    if ld == 1:
        return ("闰" if is_leap else "") + LUNAR_MON_CN[lm] + "月"
    return LUNAR_DAY_CN[ld]


def sum_credit(credit_json_str):
    """从 credit_json 字符串求和总 credit 消耗"""
    if not credit_json_str:
        return None
    try:
        data = json.loads(credit_json_str)
        if isinstance(data, dict):
            return sum(float(v) for v in data.values())
        return None
    except Exception:
        return None


def fmt_time(t):
    """格式化时间为简洁显示：今天 HH:MM / 昨天 HH:MM / MM-DD"""
    now = dt.datetime.now()
    if t.date() == now.date():
        return t.strftime("%H:%M")
    if (now - t).days == 1:
        return "昨天 " + t.strftime("%H:%M")
    return t.strftime("%m-%d")


def draw_footer(draw, now, sys_info):
    """底部状态栏（所有页通用）"""
    import subprocess as sp
    kindle_status = get_kindle_status()
    f_tiny = font(13)
    draw.line([(0, 720), (W, 720)], fill=FG, width=2)
    draw.text((16, 730), f"更新 {now['time']} | 下次 {next_refresh()}", font=f_tiny, fill=DARK_GRAY)
    draw.text((16, 752), f"{kindle_status} | {sys_info}", font=f_tiny, fill=DARK_GRAY)
    draw.text((16, 775), f"WorkBuddy Kindle Dashboard v{__version__}", font=f_tiny, fill=DARK_GRAY)


def get_pc_detail():
    """电脑详细状态，返回 [(label, pct, text), ...]
    pct 用于环形图，text 为补充说明
    """
    info = []
    try:
        import shutil
        for label, path in [("C盘", "C:/"), ("D盘", "D:/"), ("E盘", "E:/")]:
            try:
                t, u, f = shutil.disk_usage(path)
                pct = u / t * 100
                info.append((label, pct, f"{u//(1024**3)}G/{t//(1024**3)}G"))
            except Exception:
                info.append((label, 0, "--"))
    except Exception:
        info.append(("磁盘", 0, "--"))
    # 进程数
    try:
        import subprocess as sp
        r = sp.run(["tasklist", "/fo", "csv"], capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW)
        n = r.stdout.count("\n") - 1
        info.append(("进程", 0, str(n)))
    except Exception:
        pass
    return info


def get_kindle_detail():
    """Kindle 详细状态（通过 SSH），返回 [(label, pct_or_None, text), ...]
    pct 用于环形图（电量），None 则纯文字显示
    """
    info = []
    try:
        import subprocess as sp
        ssh_cmd = [
            "ssh",
            "-i", os.path.expanduser(SSH_KEY),
            "-p", str(globals().get('KINDLE_PORT', 22)),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=5",
            "root@" + KINDLE_HOST,
            "echo BATT=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null); "
            "echo TIME=$(date +%H:%M); "
            "echo UPTIME=$(uptime 2>/dev/null | awk -F'up' '{print $2}' | cut -d, -f1-2)"
        ]
        r = sp.run(ssh_cmd, capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        for line in r.stdout.split("\n"):
            if line.startswith("BATT="):
                val = line.split("=")[1].strip()
                if val.isdigit():
                    info.append(("电量", int(val), f"{val}%"))
                else:
                    info.append(("电量", None, val))
            elif line.startswith("TIME="):
                info.append(("Kindle 时间", None, line.split("=")[1].strip()))
            elif line.startswith("UPTIME="):
                info.append(("运行时间", None, line.split("=")[1].strip()[:24]))
    except Exception:
        info.append(("SSH", None, "连接失败"))
    info.append(("IP 地址", None, KINDLE_HOST))
    return info


if __name__ == "__main__":
    page = get_page_for_time()
    out = render_page(page)
    print(f"Dashboard 已生成 (页 {page}/4): {out}")
