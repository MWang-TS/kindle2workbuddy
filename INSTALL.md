# Kindle USBNetwork 安装指引

> 用途：让 Kindle 支持 SSH 访问，本机推送 dashboard 图片后通过 `eips` 命令直接刷新 e-ink 屏。
> 目标设备：Kindle 8 (入门版 2016)，固件 5.13.6，已越狱，已安装 KUAL + MRPI。

---

## 第 1 步：确认 Kindle 状态

在 Kindle 上操作（屏幕解锁后）：

- 按 **Menu 键** → 应能看到 **KUAL**（KUAL 已装的标志）
- 进入 KUAL → 应能看到 **MR Installer**（MRPI 已装的标志）
- 记下 Kindle 系统信息：主页 → 顶部菜单（三横线）→ 设置 → 设备选项 → 设备信息
  - 设备型号：例如 KT2 (Kindle 8)
  - 固件版本：5.13.6.x.x

如果 KUAL 或 MR Installer 没看到，说明前面步骤缺一个，需要先补装。

---

## 第 2 步：下载对应的 USBNetwork 包

到 **MobileRead 论坛** 下载 USBNetwork hack（kindle-usbnet-0.41N）：

**MobileRead 论坛帖（官方主帖）：**
https://www.mobileread.com/forums/showthread.php?t=225030

下载最新版（K5+ 触屏设备专用，覆盖 Kindle 8 代）：

- **文件名**：`kindle-usbnet-0.22.N-r19297.tar.xz`
- **OVH 云存储直链**（帖子主帖里给的下载地址）：
  `https://storage.gra.cloud.ovh.net/v1/AUTH_2ac4bfee353948ec8ea7fd1710574097/mr-public/Touch/kindle-usbnet-0.22.N-r19297.tar.xz`
- **书伴备份**（百度网盘，提取码 `9tgy`）：
  `https://pan.baidu.com/s/1qAgVhwfLXY2Z6VyHh5PCEw`

> 注意区分两个版本：
> - 触屏设备（Kindle Touch/PW/Voyage/Oasis/Kindle 7/8/10/11）→ `kindle-usbnet-0.22.N`（简称 usbnet）
> - 老设备（Kindle 2/DX/3/4 非触屏）→ `kindle-usbnetwork-0.57.N`（全名 usbnetwork，**不要下这个**）
> 你的 Kindle 8 代属于触屏设备，用 0.22.N 版本。

**关键：包内会有多个 .bin 文件**，Kindle 8 代用 `Update_usbnet_0.22.N_install_pw2_and_up.bin`（`pw2_and_up` = PaperWhite 2 及以上，覆盖 Kindle 8 代）。

---

## 第 3 步：解压并复制到 Kindle

把 `kindle-usbnet-0.22.N-r19297.tar.xz` **解压**后（.tar.xz 用 7-Zip 解压），会看到类似：

```
Update_usbnet_0.22.N_install_pw2_and_up.bin   ← Kindle 8 代用这个
Update_usbnet_0.22.N_install_k5.bin           ← 其他型号
README.md
...
```

**操作步骤**（在电脑上）：

1. Kindle 通过 USB 连接到电脑（屏幕解锁状态下插线）
2. Kindle 会作为一个 USB 存储盘符出现在电脑中
3. 打开 Kindle 盘，创建目录 `mrpackages`（如果已有就跳过）
4. 把 `Update_usbnet_0.22.N_install_pw2_and_up.bin` **这一个文件**复制到 `mrpackages/` 目录
   - 复制后的样子：`mrpackages/Update_usbnet_0.22.N_install_pw2_and_up.bin`
   - 注意：只复制这一个 `.bin` 文件，不要复制其他型号的 bin

> 之前已经检查过你的 `mrpackages/` 目录是空的，可以直接复制。

---

## 第 4 步：在 Kindle 上安装

操作回到 Kindle 端：

1. **弹出 Kindle**（从电脑弹出 USB 设备）
2. Kindle 屏幕应该会自动刷新，回到主页
3. 按 **Menu 键** → 进入 **KUAL**
4. 在 KUAL 菜单里点击 **MR Installer**
5. MR Installer 会自动扫描 `mrpackages/` 目录里的所有 `.bin` 文件
6. 应该看到 USBNetwork 包，点击 **"Install"** 或 **"Update"** 按钮
7. 安装过程中屏幕会闪白几次，正常现象
8. 安装完成后，MR Installer 会显示已装的 hack 列表

---

## 第 5 步：重启 Kindle

1. 长按 Kindle 电源键 **7 秒** → 强制重启
2. 等待 Kindle 重新启动完成（首页出现）

---

## 第 6 步：验证 USBNetwork 工作

1. 重新 USB 连接 Kindle 到电脑
2. Kindle 屏幕解锁
3. **首次连接**：USBNetwork 默认 USB 模式不自动启动，需要手动触发：
   - 在 Kindle 主页，按 **Menu 键** → **KUAL** → 应能看到 **"USBNetwork"** 选项
   - 点击 **USBNetwork** → 进入子菜单
   - 选择 **"USB Network"** 或 **"Enable"** → 启动 USB 网络模式
4. Kindle 屏幕会出现连线和树莓派图标，表示网络模式启动
5. **电脑端**验证：
   - 等 10 秒
   - 在 Git Bash / PowerShell / CMD 中执行：
     ```bash
     ssh root@<KINDLE_USB_IP>
     ```
   - 默认密码通常是 `mario`（USBNetwork 旧版默认密码）
   - `<KINDLE_USB_IP>` 通常是 `192.168.15.244`（USBNetwork 默认 USB 模式 IP）

> 如果连不上，确认 Windows 防火墙没拦截，或检查网络适配器是否有新 USB RNDIS 连接。

---

## 第 7 步：配置 SSH 免密登录（关键！）

每次推送都要输入密码太麻烦，做一次免密：

**电脑端**（Git Bash）：

```bash
# 1. 生成 SSH 密钥（已经有就跳过）
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# 2. 推送公钥到 Kindle
# 首次需要密码（默认 mario）
ssh root@<KINDLE_USB_IP> "mkdir -p /mnt/us/usbnet/etc"
scp ~/.ssh/id_ed25519.pub root@<KINDLE_USB_IP>:/mnt/us/usbnet/etc/authorized_keys

# 3. Kindle 端 sshd 重启使其生效（直接 Kindle 屏幕操作）
# KUAL → USBNetwork → "Restart sshd"
```

之后就能免密登录：

```bash
ssh root@<KINDLE_USB_IP> "echo ok"
```

---

## 第 8 步：WiFi 模式（可选，强烈推荐）

每次插 USB 不方便，更推荐 WiFi 模式：

1. Kindle 连上家里 WiFi（主页 → 顶部菜单 → WiFi 设置）
2. KUAL → USBNetwork → **"Enable WiFi"**
3. Kindle 屏幕上应显示获得的 IP（如 `192.168.1.x`）
4. 电脑端测试：
   ```bash
   ssh root@<KINDLE_WIFI_IP>
   ```
5. 把这个 IP 改到 `settings.py` 里的 `KINDLE_HOST` 变量

---

## 第 9 步：测试 dashboard 推送

回到电脑，进入项目目录：

```bash
cd /path/to/kindle-dashboard
python refresh.py
```

如果一切正常，Kindle 屏幕会立刻刷新显示 dashboard！

---

## 第 10 步：设置定时刷新

### 方案 A：Windows 任务计划程序（推荐）

1. 打开 `taskschd.msc`（Win+R 输入 taskschd.msc）
2. 创建任务 → 名称 "Kindle Dashboard Refresh"
3. 触发器：每 3 分钟触发一次（用户登录时）
4. 操作：启动程序
   - 程序：你的 Python 解释器路径（如 `C:\Python3x\python.exe`，或虚拟环境内的 `python.exe`）
   - 参数：`/path/to/kindle-dashboard/refresh.py`
5. 条件：取消"只在交流电时启动"
6. 保存

### 方案 B：Kindle 端 cron（需 USB 模式下）

```bash
ssh root@<KINDLE_USB_IP>
echo "*/3 * * * * /mnt/us/refresh_screen.sh" >> /etc/crontab/root
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| KUAL 看不到 USBNetwork | 安装步骤漏了 | 重新复制到 mrpackages 重装 |
| SSH 连不上 | USB 模式没启动 | KUAL → USBNetwork → Enable |
| 提示密码错误 | 默认密码不对 | 试 `mario` 或 `password` |
| eips 命令找不到 | 系统路径不同 | `which eips` 或 `/usr/sbin/eips` |
| 屏幕闪屏严重 | eips 刷新模式 | 改用 `eips -g -f` 强制刷新 |
| 屏幕一直亮着 | preventScreenSaver 没设 | 脚本里已加 `lipc-set-prop` |

---

## 📞 求助时告诉我

安装过程中遇到任何问题，直接告诉我：
- 卡在哪一步
- 屏幕/KUAL 看到了什么
- 电脑端的报错信息

我帮你排查。
