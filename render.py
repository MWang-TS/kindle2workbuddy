# -*- coding: utf-8 -*-
"""kindle-dashboard 渲染引擎
用 Pillow 生成 600x800 灰度 PNG，针对 Kindle 8代 e-ink 屏优化。
布局：顶部状态栏 / 自动化任务 / 多项目进度 / 今日待办 / 底部刷新栏
"""
import os
import sys
import json
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
GRAY = 170               # 灰色（进度条/次要）
LIGHT_GRAY = 210         # 浅灰（分割线）
DARK_GRAY = 80           # 深灰（强调）

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

DB_PATH = os.path.expanduser(getattr(globals(), 'DB_PATH', "~/.workbuddy/workbuddy.db"))

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
    """从 wttr.in 获取上海天气，失败则使用缓存"""
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


def get_kindle_status():
    """通过 SSH 获取 Kindle 电量和 WiFi 信号"""
    import subprocess
    try:
        ssh_cmd = [
            "ssh",
            "-i", os.path.expanduser(SSH_KEY),
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
def draw_progress_bar(draw, x, y, w, h, pct, fill_gray=GRAY):
    """绘制进度条"""
    draw.rectangle([x, y, x + w, y + h], outline=FG, width=1)
    fill_w = int(w * pct / 100)
    if fill_w > 1:
        draw.rectangle([x + 1, y + 1, x + fill_w, y + h - 1], fill=fill_gray)


def draw_donut(draw, cx, cy, r, pct, width=13, show_pct=True):
    """绘制环形图（donut）：从12点方向顺时针显示 pct%
    pct: 0-100；中心显示百分比数字
    """
    bbox = [cx - r, cy - r, cx + r, cy + r]
    # 背景环（浅灰）
    draw.arc(bbox, start=0, end=360, fill=LIGHT_GRAY, width=width)
    # 前景弧（黑，从12点270°顺时针）
    if pct > 1:
        end_angle = (270 + 360 * pct / 100) % 360
        draw.arc(bbox, start=270, end=end_angle, fill=FG, width=width)
    # 中心百分比
    if show_pct:
        f_num = font(18, bold=True)
        text = f"{pct:.0f}%"
        tb = draw.textbbox((0, 0), text, font=f_num)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((cx - tw / 2, cy - th / 2), text, font=f_num, fill=FG)


def draw_section_title(draw, text, y, fnt):
    """区块标题"""
    draw.text((20, y), text, font=fnt, fill=FG)
    draw.line([(20, y + 24), (W - 20, y + 24)], fill=LIGHT_GRAY, width=1)


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
    """主 dashboard：时间天气/自动化任务/多项目进度/今日待办"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    automations = get_automations()
    weather = get_weather()
    sys_info = get_system_info()

    sys.path.insert(0, str(BASE_DIR))
    from config import PROJECTS, TODOS, STATUS_MARK, SHORT_NAME

    f_section = font(22, bold=True)
    f_body = font(17)
    f_small = font(15)
    f_tiny = font(13)
    f_clock = font(34, bold=True)

    # 顶部
    draw.text((16, 10), now["date"], font=f_section, fill=FG)
    draw.text((16, 30), now["time"], font=f_clock, fill=FG)
    draw.text((W - 130, 14), weather, font=f_body, fill=DARK_GRAY)
    draw.text((W - 130, 42), WEATHER_CITY_CN, font=f_small, fill=DARK_GRAY)
    draw.text((W - 16, 10), "1/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 80), (W, 80)], fill=FG, width=2)

    # 自动化任务 4 卡片
    draw_section_title(draw, "自动化任务", 88, f_section)
    if not automations:
        automations = [{"name": "无活跃任务", "time": "--:--", "state": "idle"}]
    card_x = 16
    card_w = 138
    card_h = 76
    card_y = 120
    for i, task in enumerate(automations[:4]):
        cx = card_x + i * (card_w + 8)
        cy = card_y
        draw.rectangle([cx, cy, cx + card_w, cy + card_h], outline=GRAY, width=1)
        name = SHORT_NAME.get(task["name"], task["name"])
        if len(name) > 8:
            name = name[:7] + "…"
        draw.text((cx + 8, cy + 8), name, font=f_body, fill=FG)
        draw.text((cx + 8, cy + 32), "计划 " + task["time"], font=f_small, fill=DARK_GRAY)
        if task["state"] == "done":
            mark, color = "已执行", FG
        elif task["state"] == "pending":
            mark, color = "待执行", DARK_GRAY
        else:
            mark, color = "异常", FG
        draw.text((cx + 8, cy + 55), mark, font=f_small, fill=color)

    # 多项目进度
    sec2_y = 205
    draw_section_title(draw, "多项目进度看板", sec2_y + 5, f_section)
    proj_y = sec2_y + 36
    row_h = 40
    for i, p in enumerate(PROJECTS[:8]):
        ry = proj_y + i * row_h
        mark = STATUS_MARK.get(p["status"], "[ ]")
        draw.text((16, ry), mark, font=f_body, fill=FG)
        draw.text((52, ry), p["name"], font=f_body, fill=FG)
        draw.text((52, ry + 20), p["detail"], font=f_small, fill=DARK_GRAY)
        draw_progress_bar(draw, 360, ry + 4, 220, 14, p["progress"])

    # 底部
    draw_footer(draw, now, sys_info)

    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页2: 系统详情 ──────────────────────────────────────
def render_page2():
    """系统详情：电脑/Kindle/下次任务"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()
    kindle_status = get_kindle_status()

    f_section = font(22, bold=True)
    f_body = font(17)
    f_small = font(15)
    f_tiny = font(13)
    f_clock = font(34, bold=True)

    # 顶部
    draw.text((16, 10), "系统状态", font=f_section, fill=FG)
    draw.text((16, 30), now["time"], font=f_clock, fill=FG)
    draw.text((W - 130, 14), sys_info, font=f_body, fill=DARK_GRAY)
    draw.text((W - 130, 42), "电脑", font=f_small, fill=DARK_GRAY)
    draw.text((W - 16, 10), "2/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 80), (W, 80)], fill=FG, width=2)

    # 电脑状态（环形图）
    draw_section_title(draw, "电脑状态", 88, f_section)
    pc_info = get_pc_detail()
    donut_positions = [(110, 170), (290, 170), (470, 170)]  # 3个环形图中心
    for i, (label, pct, text) in enumerate(pc_info[:3]):
        cx, cy = donut_positions[i]
        if pct > 0:
            draw_donut(draw, cx, cy, 42, pct)
        else:
            draw.text((cx - 20, cy - 10), text, font=f_body, fill=FG)
        # 标签 + 说明
        draw.text((cx - 15, cy + 55), label, font=f_body, fill=FG)
        draw.text((cx - 25, cy + 80), text, font=f_tiny, fill=DARK_GRAY)

    # Kindle 状态（电量环形图 + 文字）
    sec_y = 300
    draw_section_title(draw, "Kindle 状态", sec_y, f_section)
    kindle_info = get_kindle_detail()
    y = sec_y + 36
    first = True
    for label, pct, text in kindle_info:
        if pct is not None and pct > 0:
            # 电量：环形图（行距大）
            draw_donut(draw, 110, y + 25, 28, pct)
            draw.text((160, y + 15), label, font=f_body, fill=FG)
            draw.text((160, y + 40), text, font=f_tiny, fill=DARK_GRAY)
            y += 58
        else:
            # 其余：纯文字（行距小）
            draw.text((20, y), label, font=f_body, fill=FG)
            draw.text((170, y), text, font=f_body, fill=DARK_GRAY)
            y += 34

    # 自动化任务下次运行
    sec_y = y + 15
    draw_section_title(draw, "下次运行倒计时", sec_y, f_section)
    automations = get_automations()
    y = sec_y + 36
    now_dt = dt.datetime.now()
    for task in automations[:4]:
        rrule_str = task.get("time", "--:--")
        try:
            h, m = rrule_str.split(":")
            task_time = now_dt.replace(hour=int(h), minute=int(m), second=0)
            if task_time <= now_dt:
                task_time += dt.timedelta(days=1)
                label = "明天"
            else:
                label = "今天"
            delta = task_time - now_dt
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            count = f"{hours}h{mins}m"
        except Exception:
            count = "--"
            label = "?"
        draw.text((20, y), task["name"][:10], font=f_body, fill=FG)
        draw.text((300, y), f"{label} {rrule_str}", font=f_body, fill=DARK_GRAY)
        draw.text((W - 80, y), count, font=f_body, fill=FG)
        y += 36

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页3: 日历视图 ──────────────────────────────────────
def render_page3():
    """日历视图：本月日历，今天高亮"""
    import calendar

    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()
    today = dt.datetime.now()

    f_section = font(22, bold=True)
    f_body = font(17)
    f_small = font(15)
    f_tiny = font(13)
    f_clock = font(34, bold=True)
    f_xxl = font(72, bold=True)   # 超大时钟
    f_day = font(20, bold=True)

    # ═══ 上 1/3：大数字时钟 + 日期 + 农历 ═══
    now_dt = dt.datetime.now()
    lunar_info = get_lunar(now_dt.year, now_dt.month, now_dt.day)
    gan = "甲乙丙丁戊己庚辛壬癸"[(lunar_info[0] - 4) % 10]
    zhi = "子丑寅卯辰巳午未申酉戌亥"[(lunar_info[0] - 4) % 12]
    lunar_str = f"农历{gan}{zhi}年 {('闰' if lunar_info[2] else '')}{LUNAR_MON_CN[lunar_info[1]]}月{LUNAR_DAY_CN[lunar_info[3]]}"

    # 超大时间居中
    time_str = now["time"]
    time_bbox = draw.textbbox((0, 0), time_str, font=f_xxl)
    time_w = time_bbox[2] - time_bbox[0]
    draw.text(((W - time_w) / 2, 30), time_str, font=f_xxl, fill=FG)
    # 日期 + 农历
    draw.text((16, 165), now["date"], font=f_section, fill=FG)
    draw.text((W - 130, 170), "3/4", font=f_tiny, fill=DARK_GRAY)
    draw.text((16, 205), lunar_str, font=f_section, fill=FG)
    draw.line([(0, 260), (W, 260)], fill=FG, width=2)

    # ═══ 下 2/3：紧凑日历（含农历）═══
    days_cn = ["一", "二", "三", "四", "五", "六", "日"]
    grid_x = 20
    grid_y = 278
    cell_w = (W - 40) // 7   # 80
    cell_h = 62
    for i, d in enumerate(days_cn):
        x = grid_x + i * cell_w
        draw.text((x + 30, grid_y), d, font=f_small, fill=DARK_GRAY)

    cal = calendar.Calendar(firstweekday=0)  # 周一开头
    month_days = cal.monthdayscalendar(today.year, today.month)
    cal_y = grid_y + 28
    for week_idx, week in enumerate(month_days):
        for day_idx, day in enumerate(week):
            if day == 0:
                continue
            x = grid_x + day_idx * cell_w
            y = cal_y + week_idx * cell_h
            lunar_txt = lunar_day_short(today.year, today.month, day)
            if day == today.day:
                # 今天反白
                draw.rectangle([x, y, x + cell_w - 3, y + cell_h - 6], fill=FG)
                draw.text((x + 24, y + 4), str(day), font=f_day, fill=BG)
                draw.text((x + 16, y + 30), lunar_txt[:4], font=f_tiny, fill=BG)
            else:
                if day_idx >= 5:  # 周末
                    col = DARK_GRAY
                else:
                    col = FG
                draw.text((x + 24, y + 4), str(day), font=f_day, fill=col)
                draw.text((x + 16, y + 30), lunar_txt[:4], font=f_tiny, fill=DARK_GRAY)

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页4: 任务执行状态 ────────────────────────────────
def render_page4():
    """任务执行状态：任务名称/模型/credit/结果"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()
    running, recent = get_task_status()

    f_section = font(22, bold=True)
    f_body = font(17)
    f_small = font(15)
    f_tiny = font(13)
    f_clock = font(34, bold=True)

    # 顶部
    draw.text((16, 10), "会话状态", font=f_section, fill=FG)
    draw.text((16, 30), now["time"], font=f_clock, fill=FG)
    draw.text((W - 16, 10), "4/4", font=f_tiny, fill=DARK_GRAY)
    draw.line([(0, 80), (W, 80)], fill=FG, width=2)

    # 区块1: 正在执行（大字体，内容多）
    draw_section_title(draw, "正在执行", 88, f_section)
    if running:
        y = 132
        task = running[0]
        name = task["name"]
        if len(name) > 18:
            name = name[:17] + "…"
        draw.text((20, y), name, font=f_section, fill=FG)
        draw.text((20, y + 32), "⏳ 执行中", font=f_body, fill=FG)
        draw.text((150, y + 32), "模型 " + task["model"], font=f_body, fill=FG)
        run_mins = int((dt.datetime.now() - task["start"]).total_seconds() / 60)
        draw.text((20, y + 60), "开始 %s · 已运行 %d 分钟" % (task["start"].strftime("%H:%M"), run_mins),
                  font=f_body, fill=FG)
        draw.text((20, y + 88), "消耗 " + fmt_credit(task["credit"]), font=f_body, fill=FG)
        cwd = task["cwd"]
        if cwd:
            if len(cwd) > 32:
                cwd = "…" + cwd[-30:]
            draw.text((20, y + 116), cwd, font=f_small, fill=DARK_GRAY)
    else:
        draw.text((20, 140), "当前无执行中的会话", font=f_body, fill=FG)

    # 区块2: 刚刚结束的会话
    sec_r = 295 if running else 210
    draw_section_title(draw, "最近会话", sec_r, f_section)
    if recent:
        y = sec_r + 40
        for item in recent[:4]:
            # 第一行：时间 + 完整名称（黑字）
            draw.text((16, y), fmt_time(item["time"]), font=f_small, fill=DARK_GRAY)
            name = item["name"]
            if len(name) > 24:
                name = name[:23] + "…"
            draw.text((90, y), name, font=f_body, fill=FG)
            # 第二行：模型（黑字，左半）+ 消耗（右半）+ 结果
            model_text = "模型 " + item["model"]
            if len(model_text) > 14:
                model_text = model_text[:13] + "…"
            draw.text((90, y + 28), model_text, font=f_body, fill=FG)
            credit_text = "消耗 " + fmt_credit(item["credit"])
            draw.text((350, y + 28), credit_text, font=f_body, fill=FG)
            if item["result"] == 1:
                mark = "✅"
            else:
                mark = "❌"
            draw.text((W - 36, y + 28), mark, font=f_body, fill=FG)
            y += 56
    else:
        draw.text((20, sec_r + 40), "暂无已结束的会话", font=f_body, fill=DARK_GRAY)

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
                "credit": sum_credit(s["credit_json"]) or s["used"] or None,
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
                "credit": sum_credit(s["credit_json"]) or s["used"] or None,
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


def fmt_credit(v):
    """格式化用量：52129 → 52.1K"""
    if v is None:
        return "--"
    try:
        v = float(v)
        if v >= 1000000:
            return f"{v/1000000:.1f}M"
        if v >= 1000:
            return f"{v/1000:.1f}K"
        return f"{v:.0f}"
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
    draw.text((16, 775), "WorkBuddy Kindle Dashboard v1.2", font=f_tiny, fill=DARK_GRAY)


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
    info.append(("IP 地址", None, "192.168.8.24"))
    return info


if __name__ == "__main__":
    page = get_page_for_time()
    out = render_page(page)
    print(f"Dashboard 已生成 (页 {page}/4): {out}")
