# kindle2workbuddy

Turn a jailbroken Kindle into a dedicated WorkBuddy dashboard display via WiFi SSH + eips e-ink refresh.

![Dashboard Preview](output/dashboard.png)

## What It Does

Renders a 600×800 grayscale dashboard PNG on your PC, pushes it to the Kindle via SCP, and refreshes the e-ink screen using `eips`. The Kindle becomes a always-on, battery-efficient status display for your WorkBuddy automations, project progress, todos, calendar, and system metrics.

**4-page carousel** (rotates every 3 minutes, 12-min full cycle):

| Page | Content |
|------|---------|
| 1 | Main dashboard: clock + weather + automation tasks + project progress + todos |
| 2 | System details: PC disk/processes + Kindle battery/uptime + next task countdown |
| 3 | Calendar view: current month, today highlighted |
| 4 | Feishu schedule (placeholder, auto-fills when connector is online) |

## Requirements

### Hardware
- Jailbroken Kindle (tested on Kindle 8th gen / KT2, firmware 5.13.6)
- 600×800 e-ink display, 167ppi (Kindle Basic 2016)
- WiFi connection (same network as your PC)

### Kindle-side
- **KUAL** + **MRPI** installed
- **USBNetwork hack** installed (v0.22.N+ for touch devices)
- WiFi SSH enabled (`USE_WIFI="true"`, `USE_WIFI_SSHD_ONLY="true"` in `usbnet/etc/config`)
- SSH key-based auth configured

### PC-side
- Python 3.9+ with Pillow
- OpenSSH client (Windows 10+ built-in)
- Windows Task Scheduler (for auto-refresh)

## Quick Start

### 1. Install USBNetwork on Kindle

Follow the [USBNetwork install guide](INSTALL.md). Key steps:
1. Download `kindle-usbnet-0.22.N-r19297.tar.xz` from [MobileRead thread t=225030](https://www.mobileread.com/forums/showthread.php?t=225030)
2. Copy `Update_usbnet_0.22.N_install_pw2_and_up.bin` to Kindle `mrpackages/`
3. KUAL → MR Installer → Install
4. Rename `usbnet/DISABLED_auto` → `usbnet/auto`
5. Edit `usbnet/etc/config`: set `USE_WIFI="true"` and `USE_WIFI_SSHD_ONLY="true"`
6. Copy your SSH public key to `usbnet/etc/authorized_keys`
7. Restart Kindle

### 2. Configure

Edit `settings.py`:
```python
KINDLE_HOST = "192.168.x.x"  # Your Kindle's WiFi IP (find via ;711 on Kindle)
SSH_KEY = "~/.ssh/id_kindle"  # Path to your SSH key
```

Edit `config.py` to customize your projects and todos.

### 3. Install Python deps

```bash
pip install Pillow requests
```

### 4. Test

```bash
python refresh.py
```

Your Kindle screen should refresh and show the dashboard.

### 5. Set up auto-refresh

**Windows** (Admin PowerShell):
```powershell
schtasks /create /tn "KindleDashboard" /tr "E:\path\to\kindle-dashboard\run_refresh.bat" /sc minute /mo 3 /rl highest /f
```

**Linux/macOS** (crontab):
```bash
*/3 * * * * cd /path/to/kindle-dashboard && python refresh.py >> output/refresh.log 2>&1
```

## How It Works

```
┌─────────────┐    render.py     ┌──────────────┐    scp      ┌──────────┐
│  WorkBuddy   │ ──────────────→ │ dashboard.png │ ────────→  │  Kindle  │
│  DB + APIs   │   Pillow 600×800 │   (grayscale) │   SSH+eips │ e-ink    │
└─────────────┘                  └──────────────┘            └──────────┘
      ↑                                                        │
      │                   refresh.py                           │
      └────────────────── (every 3 min) ←──────────────────────┘
```

1. **render.py**: Collects data (automations from WorkBuddy DB, weather from wttr.in, system metrics) and renders a 600×800 grayscale PNG using Pillow
2. **refresh.py**: SCPs the PNG to Kindle, then SSH-executes `eips -g` to refresh the e-ink display
3. **Framework stop**: Each refresh also stops the Kindle UI framework (`/etc/init.d/framework stop`) to prevent touch input from interfering
4. **Screen saver disable**: `lipc-set-prop com.lab126.powerd preventScreenSaver 1` keeps Kindle awake

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

## Customization

### Add your projects

Edit `config.py`:
```python
PROJECTS = [
    {"name": "My Project", "detail": "description", "status": "active", "progress": 50},
    # ...
]
```

### Change weather city

Edit `settings.py`:
```python
WEATHER_CITY = "Tokyo"
WEATHER_CITY_CN = "东京"
```

### Change refresh interval

Edit `settings.py`:
```python
REFRESH_MINUTES = 5  # Every 5 minutes instead of 3
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Kindle screen doesn't update | Check SSH: `ssh -i ~/.ssh/id_kindle root@<IP>` |
| Kindle goes to sleep | refresh.py auto-disables screen saver; if it sleeps, press power button once |
| Touch jumps to home page | refresh.py auto-stops framework; if it restarts, run refresh.py again |
| Weather shows `--` | wttr.in may be blocked; check network or use a proxy |
| Can't find Kindle IP | On Kindle, type `;711` in search bar, look at "4-Interface" |
| SSH connection refused | Ensure Kindle WiFi is on and `usbnet/auto` file exists |

## Recovering Kindle

To restore Kindle to normal reading mode:
```bash
ssh root@<KINDLE_IP> "/etc/init.d/framework start"
```

Or long-press power button for 7 seconds to restart.

## Tested Hardware

- Kindle 8th gen (KT2, Basic 2016) — 600×800, 167ppi, no backlight
- Firmware 5.13.6
- Should work on any Kindle Touch/PaperWhite/Voyage/Oasis with USBNetwork

## Credits

- [NiLuJe's USBNetwork hack](https://www.mobileread.com/forums/showthread.php?t=225030)
- [BookFere USBNetwork guide](https://bookfere.com/post/59.html)
- [kindle-dash by pascalw](https://github.com/pascalw/kindle-dash) (inspiration)
- Weather data by [wttr.in](https://wttr.in)

## License

MIT
