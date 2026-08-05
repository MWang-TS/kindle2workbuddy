---
name: kindle-dashboard
description: 将越狱后的Kindle改造成WorkBuddy专属Dashboard显示屏。通过WiFi SSH推送PNG图片到Kindle，用eips刷新e-ink屏幕，展示自动化任务、会话总览、系统状态、日历等信息。4页轮播，30秒一页。
version: 0.1.0
---

# Kindle Dashboard

将越狱Kindle改造成WorkBuddy专属dashboard显示屏，通过WiFi SSH + eips刷新e-ink屏幕。

## 功能说明

**4页轮播**（30秒/页，2分钟一轮）：

1. **主Dashboard** - 时间天气 / 自动化任务 / 会话总览 / 系统占用
2. **系统详情** - 电脑磁盘环形图 / Kindle状态 / 下次运行倒计时  
3. **日历视图** - 超大时钟+天气+农历 / 本月日历（今天高亮，周末浅底）
4. **会话信息** - 正在执行的会话详情 / 最近结束的会话列表

## 前置条件

**Kindle侧**（仅首次配置）：
- 已越狱的Kindle设备（支持Kindle 8代等老机型）
- 已安装KUAL + MRPI插件
- 已安装USBNetwork插件并配置WiFi SSH

**电脑侧**：
- Python 3.8+ 环境
- Pillow库（图像渲染）
- paramiko库（SSH连接）
- WorkBuddy应用运行中（提供数据源）

## 配置文件

**settings.py** - 核心配置
```python
KINDLE_HOST = "192.168.8.24"     # Kindle WiFi IP（Kindle搜索框输入 ;711 查看）
KINDLE_PORT = 22
KINDLE_USER = "root"
SSH_KEY = "~/.ssh/id_kindle"     # SSH密钥路径
EIPS_PATH = "/usr/sbin/eips"     # Kindle上eips命令路径
KINDLE_REMOTE = "/mnt/us/dashboard.png"

DB_PATH = "~/.workbuddy/workbuddy.db"  # WorkBuddy数据库路径
DISK_PATH = "E:/"                       # 监控的磁盘

WEATHER_CITY = "Shanghai"               # wttr.in城市名
WEATHER_CITY_CN = "上海"                 # 显示用中文名

REFRESH_SECONDS = 30   # 推送间隔（秒）
PAGE_DURATION = 30     # 每页停留时间（秒）
PAGES = 4              # 轮播页数
```

**config.py** - 自动化任务简称映射
```python
SHORT_NAME = {
    "World Cup 2026 Daily Brief": "WC简报",
    "AI HOT 晨报": "AI HOT晨报",
    # ... 按需添加
}
```

## 核心命令

### 手动刷新单次
```bash
cd /path/to/kindle-dashboard
python refresh.py
```

### 创建Windows定时任务（管理员PowerShell）
```powershell
powershell -ExecutionPolicy Bypass -File setup_cron.ps1
```

自动创建"WorkBuddy Kindle Dashboard Refresh"计划任务：
- 触发器：登录时启动 + 每30秒重复
- 任务级别：最高权限
- **电脑重启后会自动恢复推送**

### 停止定时任务
```powershell
Unregister-ScheduledTask -TaskName "WorkBuddy Kindle Dashboard Refresh" -Confirm:$false
```

### 查看任务状态
```powershell
Get-ScheduledTask -TaskName "WorkBuddy Kindle Dashboard Refresh"
```

## 工作原理

1. **render.py** 从 `~/.workbuddy/workbuddy.db` 读取数据（会话、自动化任务等）
2. 用Pillow渲染600×800灰度PNG（针对e-ink优化）
3. **refresh.py** 通过SCP推送到Kindle `/mnt/us/dashboard.png`
4. SSH执行 `eips -c && eips -g /mnt/us/dashboard.png` 清屏并刷新
5. Windows任务计划程序每30秒自动调用一次refresh.py

## 数据源说明

- **自动化任务** - 读取 `~/.workbuddy/workbuddy.db` 的 `automations` 表
- **会话信息** - 读取 `sessions` 表（今日会话、正在执行、最近完成）
- **系统占用** - 读取 `.workbuddy` 目录大小（递归累加）
- **天气** - 调用 wttr.in API（10分钟缓存）
- **电脑磁盘** - psutil.disk_usage
- **Kindle状态** - SSH执行 `gasgauge-info` 和 `uptime`

**重要**：WorkBuddy应用关闭后，自动化任务/会话数据会冻结在关闭前的最后状态（不会报错，但也不会更新新会话）。天气、磁盘、日历等独立数据源不受影响。

## 故障排查

### Kindle屏幕不刷新
```bash
# 检查SSH连通性
ssh -i ~/.ssh/id_kindle root@<KINDLE_IP>

# 手动测试eips命令
ssh root@<KINDLE_IP> "/usr/sbin/eips -c"
```

### 天气数据空白
- 检查网络是否能访问 wttr.in
- 确认 `WEATHER_CITY` 配置正确（英文城市名）

### WorkBuddy数据不更新
- 确认WorkBuddy应用正在运行
- 检查 `~/.workbuddy/workbuddy.db` 是否存在且可读

### 找不到Kindle IP
- Kindle搜索框输入 `;711`，查看"4-Interface"下的IP地址
- 确认Kindle WiFi已开启，且与电脑在同一局域网

## 文件结构

```
kindle-dashboard/
├── settings.py          # 核心配置（IP、SSH key、数据源）
├── config.py            # 自动化任务简称映射
├── render.py            # 渲染引擎（4页轮播，v0.1.0）
├── refresh.py           # 推送脚本（SCP + SSH eips）
├── daemon.py            # 后台守护进程（30秒循环）
├── manual_refresh.bat   # 手动刷新快捷方式
├── run_refresh.bat      # Windows任务计划程序调用入口
├── setup_cron.ps1       # 创建Windows定时任务脚本
├── INSTALL.md           # Kindle越狱+插件安装详细指引
├── README.md            # 完整文档
└── output/              # 生成的PNG和日志（.gitignore）
```

## 使用限制

- **仅支持已越狱Kindle**（K8、KT2、KPW3等老机型，需对应固件版本）
- SSH密钥需提前配置（Kindle USBNetwork默认无密码，需手工设置）
- e-ink刷新有残影，不适合高频变化内容
- 依赖 WorkBuddy 本地数据库（离线可用，但数据需WorkBuddy应用写入）

## 更新日志

### v0.1.0 (2026-08-05)
- 视觉系统v1.3：统一圆角卡片、几何图标、环形进度条
- 字号整体放大：提升e-ink可读性
- 间距系统v1.4：主标题段前距加大，段间/行间更宽松
- 修复页2电脑状态卡片溢出问题（磁盘数据超出背景边界）
- 页3新增天气显示（时钟下方居中）
- 删除历史遗留死代码（PROJECTS/TODOS/USB RNDIS相关文件）

## 参考资源

- [BookFere Kindle越狱教程](https://bookfere.com/post/970.html)
- [BookFere KUAL+MRPI指引](https://bookfere.com/post/311.html)  
- [BookFere USBNetwork指引](https://bookfere.com/post/59.html)
- [kindle-dash by pascalw](https://github.com/pascalw/kindle-dash) (灵感来源)
- [wttr.in 天气API](https://wttr.in)

## License

MIT
