# Kindle Dashboard 配置模板
# 复制这个文件为 settings.py，然后填入你自己的真实配置。
# settings.py 已加入 .gitignore，不会被提交，你的真实IP/城市名不会泄露到公开仓库。

# ── Kindle SSH 连接 ──────────────────────────────────
KINDLE_HOST    = "192.168.x.x"       # Kindle WiFi IP（在 Kindle 搜索框输入 ;711 查看）
KINDLE_PORT    = 22
KINDLE_USER    = "root"
SSH_KEY        = "~/.ssh/id_kindle"   # SSH 密钥路径
EIPS_PATH      = "/usr/sbin/eips"     # Kindle 上 eips 命令路径
KINDLE_REMOTE  = "/mnt/us/dashboard.png"  # Kindle 上图片存放路径

# ── 数据源 ──────────────────────────────────────────
DB_PATH        = "~/.workbuddy/workbuddy.db"  # WorkBuddy 数据库路径
DISK_PATH      = "E:/"                      # 监控的磁盘

# ── 天气 ────────────────────────────────────────────
WEATHER_CITY   = "Beijing"   # wttr.in 城市名（改成你所在城市的英文名）
WEATHER_CITY_CN = "北京"       # 显示用中文名

# ── 刷新间隔 ────────────────────────────────────────
REFRESH_SECONDS = 30  # 推送间隔（秒）
PAGE_DURATION   = 30  # 每页停留时间（秒），4 页循环 = 2 分钟一轮
PAGES = 4             # 轮播页数
