# -*- coding: utf-8 -*-
"""kindle-dashboard 渲染引擎
用 Pillow 生成 600x800 灰度 PNG，针对 Kindle 8代 e-ink 屏优化。
布局：顶部状态栏 / 自动化任务 / 多项目进度 / 今日待办 / 底部刷新栏
"""
import os
import sys
import json
import sqlite3
import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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
            "WHERE status='ACTIVE'"
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
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
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
    """下次刷新时间（3分钟后）"""
    n = dt.datetime.now() + dt.timedelta(minutes=3)
    return n.strftime("%H:%M")


# ── 页码路由 ───────────────────────────────────────────
def get_page_for_time():
    """根据当前时间分钟数决定页码（每3分钟换一页，4页循环）"""
    minute = dt.datetime.now().minute
    return (minute // 3) % 4 + 1  # 1-4


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

    f_section = font(16, bold=True)
    f_body = font(14)
    f_small = font(12)
    f_tiny = font(11)
    f_clock = font(26, bold=True)

    # 顶部
    draw.text((16, 10), now["date"], font=f_section, fill=FG)
    draw.text((16, 34), now["time"], font=f_clock, fill=FG)
    draw.text((W - 130, 14), weather, font=f_body, fill=DARK_GRAY)
    draw.text((W - 130, 38), WEATHER_CITY_CN, font=f_small, fill=GRAY)
    draw.text((W - 16, 10), "1/4", font=f_tiny, fill=GRAY)
    draw.line([(0, 65), (W, 65)], fill=FG, width=2)

    # 自动化任务 4 卡片
    draw_section_title(draw, "自动化任务", 72, f_section)
    if not automations:
        automations = [{"name": "无活跃任务", "time": "--:--", "state": "idle"}]
    card_x = 16
    card_w = 138
    card_h = 70
    card_y = 108
    for i, task in enumerate(automations[:4]):
        cx = card_x + i * (card_w + 8)
        cy = card_y
        draw.rectangle([cx, cy, cx + card_w, cy + card_h], outline=GRAY, width=1)
        name = SHORT_NAME.get(task["name"], task["name"])
        if len(name) > 8:
            name = name[:7] + "…"
        draw.text((cx + 8, cy + 8), name, font=f_body, fill=FG)
        draw.text((cx + 8, cy + 28), "计划 " + task["time"], font=f_small, fill=GRAY)
        if task["state"] == "done":
            mark, color = "已执行", FG
        elif task["state"] == "pending":
            mark, color = "待执行", DARK_GRAY
        else:
            mark, color = "异常", FG
        draw.text((cx + 8, cy + 48), mark, font=f_small, fill=color)

    # 多项目进度
    sec2_y = 200
    draw_section_title(draw, "多项目进度看板", sec2_y + 5, f_section)
    proj_y = sec2_y + 36
    row_h = 32
    for i, p in enumerate(PROJECTS[:8]):
        ry = proj_y + i * row_h
        mark = STATUS_MARK.get(p["status"], "[ ]")
        draw.text((16, ry), mark, font=f_body, fill=FG)
        draw.text((52, ry), p["name"], font=f_body, fill=FG)
        draw.text((52, ry + 16), p["detail"], font=f_small, fill=GRAY)
        draw_progress_bar(draw, 360, ry + 4, 220, 12, p["progress"])

    # 今日待办
    sec3_y = 495
    draw_section_title(draw, "今日待办", sec3_y + 5, f_section)
    todo_y = sec3_y + 36
    for i, todo in enumerate(TODOS[:6]):
        ty = todo_y + i * 28
        draw.text((16, ty), "[ ]", font=f_body, fill=FG)
        draw.text((52, ty), todo, font=f_body, fill=FG)

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

    f_section = font(16, bold=True)
    f_body = font(14)
    f_small = font(12)
    f_tiny = font(11)
    f_clock = font(26, bold=True)

    # 顶部
    draw.text((16, 10), "系统状态", font=f_section, fill=FG)
    draw.text((16, 34), now["time"], font=f_clock, fill=FG)
    draw.text((W - 130, 14), sys_info, font=f_body, fill=DARK_GRAY)
    draw.text((W - 130, 38), "电脑", font=f_small, fill=GRAY)
    draw.text((W - 16, 10), "2/4", font=f_tiny, fill=GRAY)
    draw.line([(0, 65), (W, 65)], fill=FG, width=2)

    # 电脑详情
    draw_section_title(draw, "电脑状态", 72, f_section)
    pc_info = get_pc_detail()
    y = 110
    for k, v in pc_info:
        draw.text((20, y), k, font=f_body, fill=FG)
        draw.text((300, y), v, font=f_body, fill=DARK_GRAY)
        y += 26

    # Kindle 状态
    sec_y = 250
    draw_section_title(draw, "Kindle 状态", sec_y, f_section)
    kindle_info = get_kindle_detail()
    y = sec_y + 36
    for k, v in kindle_info:
        draw.text((20, y), k, font=f_body, fill=FG)
        draw.text((300, y), v, font=f_body, fill=DARK_GRAY)
        y += 26

    # 自动化任务下次运行
    sec_y = 430
    draw_section_title(draw, "下次运行倒计时", sec_y, f_section)
    automations = get_automations()
    y = sec_y + 36
    now_dt = dt.datetime.now()
    for task in automations[:5]:
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
        y += 26

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

    f_section = font(16, bold=True)
    f_body = font(14)
    f_small = font(12)
    f_tiny = font(11)
    f_clock = font(26, bold=True)
    f_day = font(20, bold=True)

    # 顶部
    draw.text((16, 10), "日历", font=f_section, fill=FG)
    draw.text((16, 34), f"{today.year}年{today.month}月", font=f_clock, fill=FG)
    draw.text((W - 16, 10), "3/4", font=f_tiny, fill=GRAY)
    draw.line([(0, 65), (W, 65)], fill=FG, width=2)

    # 星期表头
    days_cn = ["一", "二", "三", "四", "五", "六", "日"]
    grid_x = 30
    grid_y = 100
    cell_w = 76
    cell_h = 90
    for i, d in enumerate(days_cn):
        x = grid_x + i * cell_w
        draw.text((x + 30, grid_y), d, font=f_body, fill=GRAY)

    # 日历网格
    cal = calendar.Calendar(firstweekday=0)  # 周一开头
    month_days = cal.monthdayscalendar(today.year, today.month)
    for week_idx, week in enumerate(month_days):
        for day_idx, day in enumerate(week):
            if day == 0:
                continue
            x = grid_x + day_idx * cell_w
            y = grid_y + 40 + week_idx * cell_h
            # 今天是高亮（反白显示）
            if day == today.day:
                draw.rectangle([x, y, x + cell_w - 4, y + cell_h - 20], fill=FG)
                draw.text((x + 28, y + 8), str(day), font=f_day, fill=BG)
            else:
                # 周末用浅灰
                if day_idx >= 5:
                    draw.text((x + 28, y + 8), str(day), font=f_day, fill=GRAY)
                else:
                    draw.text((x + 28, y + 8), str(day), font=f_day, fill=FG)

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 页4: 飞书日程（占位）──────────────────────────────
def render_page4():
    """飞书日程（占位）：等待连接器接入"""
    img = Image.new("L", (W, H), BG)
    draw = ImageDraw.Draw(img)

    now = get_now_str()
    sys_info = get_system_info()

    f_section = font(16, bold=True)
    f_body = font(14)
    f_small = font(12)
    f_tiny = font(11)
    f_clock = font(26, bold=True)
    f_big = font(28, bold=True)

    # 顶部
    draw.text((16, 10), "飞书日程", font=f_section, fill=FG)
    draw.text((16, 34), now["time"], font=f_clock, fill=FG)
    draw.text((W - 16, 10), "4/4", font=f_tiny, fill=GRAY)
    draw.line([(0, 65), (W, 65)], fill=FG, width=2)

    # 飞书连接器状态
    draw_section_title(draw, "飞书连接", 72, f_section)

    # 大字提示
    draw.text((40, 200), "飞书连接器离线", font=f_big, fill=DARK_GRAY)
    draw.text((40, 240), "当前无法拉取日程和待办", font=f_body, fill=GRAY)
    draw.text((40, 280), "等连接器重新接入后自动填充", font=f_small, fill=GRAY)

    # 手动同步占位
    sec_y = 400
    draw_section_title(draw, "今日待办（手动）", sec_y, f_section)
    sys.path.insert(0, str(BASE_DIR))
    from config import TODOS
    y = sec_y + 36
    for todo in TODOS[:5]:
        draw.text((20, y), "[ ]", font=f_body, fill=FG)
        draw.text((52, y), todo, font=f_body, fill=FG)
        y += 28

    draw_footer(draw, now, sys_info)
    img.save(OUTPUT_PNG, "PNG")
    return OUTPUT_PNG


# ── 辅助函数 ───────────────────────────────────────────
def draw_footer(draw, now, sys_info):
    """底部状态栏（所有页通用）"""
    import subprocess as sp
    kindle_status = get_kindle_status()
    f_tiny = font(11)
    draw.line([(0, 720), (W, 720)], fill=FG, width=2)
    draw.text((16, 730), f"更新 {now['time']} | 下次 {next_refresh()}", font=f_tiny, fill=GRAY)
    draw.text((16, 752), f"{kindle_status} | {sys_info}", font=f_tiny, fill=GRAY)
    draw.text((16, 775), "WorkBuddy Kindle Dashboard v1.2", font=f_tiny, fill=LIGHT_GRAY)


def get_pc_detail():
    """电脑详细状态"""
    info = []
    try:
        import shutil
        for label, path in [("C盘", "C:/"), ("D盘", "D:/"), ("E盘", "E:/")]:
            try:
                t, u, f = shutil.disk_usage(path)
                pct = u / t * 100
                info.append((label, f"{pct:.0f}% ({u//(1024**3)}G / {t//(1024**3)}G)"))
            except Exception:
                pass
    except Exception:
        info.append(("磁盘", "读取失败"))
    # 进程数
    try:
        import subprocess as sp
        r = sp.run(["tasklist", "/fo", "csv"], capture_output=True, text=True, timeout=5)
        n = r.stdout.count("\n") - 1
        info.append(("进程数", f"{n}"))
    except Exception:
        pass
    return info


def get_kindle_detail():
    """Kindle 详细状态（通过 SSH）"""
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
        r = sp.run(ssh_cmd, capture_output=True, text=True, timeout=10)
        for line in r.stdout.split("\n"):
            if line.startswith("BATT="):
                val = line.split("=")[1].strip()
                info.append(("电量", f"{val}%" if val.isdigit() else val))
            elif line.startswith("TIME="):
                info.append(("Kindle 时间", line.split("=")[1].strip()))
            elif line.startswith("UPTIME="):
                info.append(("运行时间", line.split("=")[1].strip()[:24]))
    except Exception:
        info.append(("SSH", "连接失败"))
    info.append(("IP 地址", "192.168.8.24"))
    return info


if __name__ == "__main__":
    page = get_page_for_time()
    out = render_page(page)
    print(f"Dashboard 已生成 (页 {page}/4): {out}")
