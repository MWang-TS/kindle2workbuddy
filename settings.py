# Kindle Dashboard 配置
# 复用时修改这个文件即可，不需要改其他代码

# ── Kindle SSH 连接 ──────────────────────────────────
KINDLE_HOST    = "192.168.8.24"       # Kindle WiFi IP（在 Kindle 搜索框输入 ;711 查看）
KINDLE_PORT    = 22
KINDLE_USER    = "root"
SSH_KEY        = "~/.ssh/id_kindle"   # SSH 密钥路径
EIPS_PATH      = "/usr/sbin/eips"     # Kindle 上 eips 命令路径
KINDLE_REMOTE  = "/mnt/us/dashboard.png"  # Kindle 上图片存放路径

# ── 数据源 ──────────────────────────────────────────
DB_PATH        = "~/.workbuddy/workbuddy.db"  # WorkBuddy 数据库路径
DISK_PATH      = "E:/"                      # 监控的磁盘

# ── 天气 ────────────────────────────────────────────
WEATHER_CITY   = "Shanghai"   # wttr.in 城市名
WEATHER_CITY_CN = "上海"       # 显示用中文名

# ── 刷新间隔 ────────────────────────────────────────
REFRESH_SECONDS = 30  # 推送间隔（秒）
PAGE_DURATION   = 120 # 每页停留时间（秒），4 页循环 = 8 分钟一轮
PAGES = 4             # 轮播页数
