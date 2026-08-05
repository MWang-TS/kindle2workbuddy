# kindle2workbuddy

**当前版本：v0.1.0**

把吃灰的 Kindle 改造成 WorkBuddy 专属 dashboard 显示屏——通过 WiFi SSH + eips 刷新 e-ink 屏幕，省电、无闪烁、阳光下可读。

![Dashboard Preview](output/dashboard.png)

Turn a jailbroken Kindle into a dedicated WorkBuddy dashboard display via WiFi SSH + eips e-ink refresh.

---

## 目录 / Table of Contents

- [中文说明](#中文说明)
- [English](#english)

---

# 中文说明

## 它能做什么

在电脑端用 Pillow 渲染 600×800 灰度 dashboard 图片，通过 SCP 推送到 Kindle，再用 `eips` 命令刷新 e-ink 屏幕显示。Kindle 变成一个常亮、省电的状态显示屏，展示你的 WorkBuddy 自动化任务、会话状态、系统指标和日历。

**4 页轮播**（每 30 秒换一页，2 分钟一轮）：

| 页码 | 内容 |
|------|------|
| 1 | 主 dashboard：时间天气 + 自动化任务 + 会话总览 + 系统占用 |
| 2 | 系统详情：电脑磁盘环形图 + Kindle 状态 + 下次运行倒计时 |
| 3 | 日历视图：超大时钟+天气+农历 + 本月日历（今天高亮，周末浅底区分） |
| 4 | 当前会话信息：正在执行的对话会话详情 + 最近结束的会话列表 |

---

## ⚠️ 前序准备（重要！）

本项目**需要已越狱的 Kindle**，不支持未越狱设备。请按顺序完成以下准备：

### 1. 检查你的 Kindle 型号和固件版本

**先确认你的 Kindle 能否越狱**——不同型号和固件版本支持的越狱方法不同。

- Kindle 主页 → 顶部菜单 → 设置 → 设备选项 → 设备信息
- 记下**设备型号**（如 KT2、KPW3 等）和**固件版本**（如 5.13.6）
- 到 [书伴·Kindle 越狱支持一览](https://bookfere.com/post/970.html) 查看你的设备+固件组合是否支持越狱

> 本项目测试设备：Kindle 8 代（KT2，入门版 2016），固件 5.13.6。其他触屏 Kindle（Touch/PaperWhite/Voyage/Oasis）理论上也可用。

### 2. 越狱 Kindle

按照书伴的越狱教程完成越狱：**[Kindle 越狱教程](https://bookfere.com/post/970.html)**

主要步骤：
1. 下载对应型号的越狱包
2. 复制 `.bin` 文件到 Kindle 根目录
3. Kindle 上：设置 → 菜单 → 更新你的 Kindle
4. 重启后确认越狱成功（出现 "You are JailBroken" 书籍或 KUAL 入口）

### 3. 安装必要插件

越狱后需要安装两个核心插件：**[KUAL + MRPI 安装教程](https://bookfere.com/post/311.html)**

- **MRPI**（MR Package Installer）：用于安装后续的 USBNetwork 等 hack 包
- **KUAL**（Kindle Unified Application Launcher）：用于在 Kindle 上启动各种 hack 和工具

主要步骤：
1. 下载 MRPI 包，解压后复制 `extensions/` 文件夹到 Kindle 根目录
2. 下载 KUAL 包，复制 `KUAL-KUAL-*.zip` 内的 `extensions/` 内容到 Kindle
3. 重启 Kindle
4. 主页应出现 KUAL 入口

### 4. 安装 USBNetwork

这是本项目的核心依赖——让 Kindle 支持 SSH 访问。详见 [INSTALL.md](INSTALL.md)。

---

## 快速开始

前提：Kindle 已越狱 + 已装 KUAL/MRPI + 已装 USBNetwork（WiFi 模式）。

### 1. 配置

编辑 `settings.py`：
```python
KINDLE_HOST = "192.168.x.x"  # Kindle 的 WiFi IP（Kindle 搜索框输入 ;711 查看）
SSH_KEY = "~/.ssh/id_kindle"  # SSH 密钥路径
```

编辑 `config.py` 自定义你的项目和待办。

### 2. 安装 Python 依赖

```bash
pip install Pillow requests
```

### 3. 测试

```bash
python refresh.py
```

Kindle 屏幕应刷新并显示 dashboard。

### 4. 设置自动刷新

**Windows**（管理员 PowerShell）：
```powershell
schtasks /create /tn "KindleDashboard" /tr "E:\path\to\kindle-dashboard\run_refresh.bat" /sc minute /mo 3 /rl highest /f
```

**Linux/macOS**（crontab）：
```bash
*/3 * * * * cd /path/to/kindle-dashboard && python refresh.py >> output/refresh.log 2>&1
```

---

## 工作原理

```
┌─────────────┐    render.py     ┌──────────────┐    scp      ┌──────────┐
│  WorkBuddy   │ ──────────────→ │ dashboard.png │ ────────→  │  Kindle  │
│  DB + APIs   │   Pillow 600×800 │   (灰度 PNG)   │   SSH+eips │ e-ink 屏  │
└─────────────┘                  └──────────────┘            └──────────┘
      ↑                                                        │
      │                   refresh.py                           │
      └────────────────── (每 3 分钟) ←─────────────────────────┘
```

1. **render.py**：采集数据（WorkBuddy DB 自动化任务、wttr.in 天气、系统指标），用 Pillow 渲染 600×800 灰度 PNG
2. **refresh.py**：SCP 推送 PNG 到 Kindle，SSH 执行 `eips -g` 刷新 e-ink 屏
3. **停止 framework**：每次刷新时执行 `/etc/init.d/framework stop`，防止触摸屏跳回主页
4. **防睡眠**：`lipc-set-prop com.lab126.powerd preventScreenSaver 1` 保持 Kindle 常亮

---

## 文件结构

```
kindle2workbuddy/
├── settings.py          # 配置文件（Kindle IP、SSH key、数据源等）
├── config.py            # 自动化任务简称映射
├── render.py            # 渲染引擎（4 页轮播）
├── refresh.py           # 推送脚本（SCP + SSH eips 刷新）
├── daemon.py            # 后台守护进程（30秒循环调用refresh.py）
├── run_refresh.bat      # Windows 任务计划程序调用入口
├── manual_refresh.bat   # 手动刷新快捷方式
├── setup_cron.ps1       # Windows 定时任务创建脚本
├── INSTALL.md           # USBNetwork 安装指引
├── SKILL.md             # WorkBuddy Skill 文档
└── output/              # 生成的 dashboard.png 和日志（已 gitignore）
```

---

## 自定义

### 修改配置

编辑 `settings.py`：
```python
KINDLE_HOST = "192.168.x.x"       # Kindle WiFi IP
WEATHER_CITY = "Beijing"          # 天气城市（改成你所在城市）
WEATHER_CITY_CN = "北京"            # 中文显示名
REFRESH_SECONDS = 30               # 推送间隔
PAGE_DURATION = 30                 # 每页停留时间
```

### 自动化任务简称

编辑 `config.py`：
```python
SHORT_NAME = {
    "World Cup 2026 Daily Brief": "WC简报",
    "AI HOT 晨报": "AI HOT晨报",
    # 添加你的自动化任务简称映射
}
```

### 修改天气城市

编辑 `settings.py`：
```python
WEATHER_CITY = "Tokyo"
WEATHER_CITY_CN = "东京"
```

### 修改刷新间隔

编辑 `settings.py`：
```python
REFRESH_MINUTES = 5  # 每 5 分钟刷新一次
```

---

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| Kindle 屏幕不更新 | 检查 SSH：`ssh -i ~/.ssh/id_kindle root@<IP>` |
| Kindle 自动睡眠 | refresh.py 会自动禁用屏幕保护；如果睡了，短按电源键唤醒 |
| 触摸跳回主页 | refresh.py 会自动停止 framework；如果恢复了，再跑一次 refresh.py |
| 天气显示 `--` | wttr.in 可能被墙；检查网络或用代理 |
| 找不到 Kindle IP | Kindle 搜索框输入 `;711`，看 "4-Interface" 那栏 |
| SSH 连接被拒 | 确认 Kindle WiFi 已开、`usbnet/auto` 文件存在 |

---

## 恢复 Kindle 正常使用

```bash
ssh root@<KINDLE_IP> "/etc/init.d/framework start"
```

或长按电源键 7 秒重启。

---

## 致谢

- [书伴·Kindle 越狱教程](https://bookfere.com/post/970.html)
- [书伴·KUAL + MRPI 安装](https://bookfere.com/post/311.html)
- [书伴·USBNetwork 安装教程](https://bookfere.com/post/59.html)
- [NiLuJe's USBNetwork hack](https://www.mobileread.com/forums/showthread.php?t=225030)
- [kindle-dash by pascalw](https://github.com/pascalw/kindle-dash)（灵感来源）
- 天气数据由 [wttr.in](https://wttr.in) 提供

## License

MIT

---

# English

## What It Does

Renders a 600×800 grayscale dashboard PNG on your PC, pushes it to the Kindle via SCP, and refreshes the e-ink screen using `eips`. The Kindle becomes an always-on, battery-efficient status display for your WorkBuddy automations, project progress, todos, calendar, and system metrics.

**4-page carousel** (rotates every 3 minutes, 12-min full cycle):

| Page | Content |
|------|---------|
| 1 | Main dashboard: clock + weather + automation tasks + project progress + todos |
| 2 | System details: PC disk/processes + Kindle battery/uptime + next task countdown |
| 3 | Calendar view: current month, today highlighted |
| 4 | Feishu schedule (placeholder, auto-fills when connector is online) |

---

## ⚠️ Prerequisites (Important!)

This project requires a **jailbroken Kindle**. Complete these steps in order:

### 1. Check Your Kindle Model & Firmware

- Kindle Home → Menu → Settings → Device Options → Device Info
- Note your **model** (e.g., KT2, KPW3) and **firmware version** (e.g., 5.13.6)
- Check if your device+firmware combo supports jailbreak at [bookfere.com](https://bookfere.com/post/970.html)

> Tested on: Kindle 8th gen (KT2, Basic 2016), firmware 5.13.6. Other touch Kindles should work too.

### 2. Jailbreak Your Kindle

Follow the jailbreak guide: **[Kindle Jailbreak Tutorial](https://bookfere.com/post/970.html)**

Key steps: download jailbreak package → copy `.bin` to Kindle → Update Your Kindle → restart → verify.

### 3. Install Required Plugins

After jailbreak, install two core plugins: **[KUAL + MRPI Guide](https://bookfere.com/post/311.html)**

- **MRPI** (MR Package Installer): for installing USBNetwork and other hacks
- **KUAL** (Kindle Unified Application Launcher): for launching hacks on Kindle

### 4. Install USBNetwork

Core dependency for SSH access. See [INSTALL.md](INSTALL.md).

---

## Quick Start

Prerequisite: Kindle jailbroken + KUAL/MRPI installed + USBNetwork (WiFi mode).

### 1. Configure

Edit `settings.py`:
```python
KINDLE_HOST = "192.168.x.x"  # Kindle WiFi IP (find via ;711 on Kindle)
SSH_KEY = "~/.ssh/id_kindle"  # SSH key path
```

Edit `config.py` to customize your projects and todos.

### 2. Install Python deps

```bash
pip install Pillow requests
```

### 3. Test

```bash
python refresh.py
```

### 4. Set up auto-refresh

**Windows** (Admin PowerShell):
```powershell
schtasks /create /tn "KindleDashboard" /tr "E:\path\to\kindle-dashboard\run_refresh.bat" /sc minute /mo 3 /rl highest /f
```

**Linux/macOS** (crontab):
```bash
*/3 * * * * cd /path/to/kindle-dashboard && python refresh.py >> output/refresh.log 2>&1
```

---

## How It Works

1. **render.py**: Collects data (WorkBuddy DB, wttr.in weather, system metrics) → renders 600×800 grayscale PNG
2. **refresh.py**: SCPs PNG to Kindle → SSH-executes `eips -g` to refresh e-ink
3. **Framework stop**: Stops Kindle UI framework to prevent touch interference
4. **Screen saver disable**: Keeps Kindle awake via `lipc-set-prop`

---

## File Structure

```
kindle2workbuddy/
├── settings.py          # Configuration (Kindle IP, SSH key, etc.)
├── config.py            # Project data (projects, todos, name mappings)
├── render.py            # Rendering engine (4-page carousel)
├── refresh.py           # Push script (SCP + SSH eips refresh)
├── run_refresh.bat      # Windows wrapper for Task Scheduler
├── manual_refresh.bat   # Manual refresh shortcut
├── setup_cron.ps1       # Windows Task Scheduler setup
├── kindle_rndis.inf     # RNDIS driver (for USB mode, optional)
├── INSTALL.md           # USBNetwork installation guide
└── output/              # Generated dashboard.png and logs (gitignored)
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Kindle screen doesn't update | Check SSH: `ssh -i ~/.ssh/id_kindle root@<IP>` |
| Kindle goes to sleep | refresh.py auto-disables screen saver; if it sleeps, press power button once |
| Touch jumps to home page | refresh.py auto-stops framework; if it restarts, run refresh.py again |
| Weather shows `--` | wttr.in may be blocked; check network or use a proxy |
| Can't find Kindle IP | On Kindle, type `;711` in search bar, look at "4-Interface" |
| SSH connection refused | Ensure Kindle WiFi is on and `usbnet/auto` file exists |

---

## Recovering Kindle

```bash
ssh root@<KINDLE_IP> "/etc/init.d/framework start"
```

Or long-press power button for 7 seconds to restart.

---

## Credits

- [BookFere Kindle Jailbreak](https://bookfere.com/post/970.html)
- [BookFere KUAL + MRPI Guide](https://bookfere.com/post/311.html)
- [BookFere USBNetwork Guide](https://bookfere.com/post/59.html)
- [NiLuJe's USBNetwork hack](https://www.mobileread.com/forums/showthread.php?t=225030)
- [kindle-dash by pascalw](https://github.com/pascalw/kindle-dash) (inspiration)
- Weather data by [wttr.in](https://wttr.in)

## License

MIT
