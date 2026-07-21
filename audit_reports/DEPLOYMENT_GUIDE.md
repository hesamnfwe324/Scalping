# DEPLOYMENT GUIDE
## GoldScalperPro v4 — Production Deployment
**Date:** 2026-07-19
**Scope:** Render.com, VPS/Linux (systemd), Docker Compose

---

## PRE-DEPLOYMENT CHECKLIST

Complete ALL items before deploying with real capital.

### Mandatory
- [ ] 5-day paper trading run on MetaAPI demo account completed (no crashes, no double entries)
- [ ] `PANEL_ENCRYPTION_KEY` generated: `python -m telegram_panel.main --generate-key`
- [ ] All env vars reviewed and set (do NOT use defaults blindly for risk settings)
- [ ] Engineering tests pass: `python -m pytest tests/ -v`
- [ ] Dependencies installed from pinned requirements on a clean environment

### Guardian Threshold Review
Before live deployment, explicitly decide on these values (do not use defaults without consideration):

| Variable | Default | Your decision |
|----------|---------|---------------|
| `DAILY_LOSS_LIMIT_PCT` | 3.0% | _______ |
| `MAX_DRAWDOWN_PCT` | 8.0% | _______ |
| `SLIPPAGE_POINTS` | 30 | _______ |
| `RISK_PERCENT` | 1.0% | _______ |

---

## OPTION 1 — Render.com Deployment (Two-Service)

### Architecture on Render

```
Render Project
├── goldscalper-v4-robot   (Background Worker)
│   └── /data/             (Persistent Disk — mount here)
│       ├── robot_state.json
│       ├── robot_mt5_snapshot.json
│       ├── robot_commands.json
│       └── robot.log
└── goldscalper-v4-panel   (Background Worker)
    └── /data/             (Same Persistent Disk — both services share it)
        └── panel.db
```

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "GoldScalperPro v4 Stable"
git remote add origin https://github.com/your-org/goldscalper-v4.git
git push -u origin main
```

### Step 2 — Create Render Project

1. Go to [render.com](https://render.com) → New → Blueprint
2. Connect your GitHub repository
3. Render auto-detects `render.yaml` and creates two services

### Step 3 — Attach Persistent Disk

**Critical:** Without a persistent disk, all state files and the panel database are lost on every restart.

1. In Render dashboard → `goldscalper-v4-robot` service → Disks
2. Add disk: Name `goldscalper-data`, Size `1 GB`, Mount path `/data`
3. In Render dashboard → `goldscalper-v4-panel` service → Disks
4. Attach the SAME disk at `/data` (both services must share the same disk)

### Step 4 — Override File Paths

After attaching the persistent disk, set these env vars on BOTH services in the Render dashboard:

```
STATE_FILE=/data/robot_state.json
MT5_SNAPSHOT=/data/robot_mt5_snapshot.json
COMMANDS_FILE=/data/robot_commands.json
LOG_FILE=/data/robot.log
PANEL_DB_PATH=/data/panel.db
ROBOT_STATE_PATH=/data/robot_state.json
ROBOT_LOG_PATH=/data/robot.log
PANEL_LOG_PATH=/data/panel.log
```

### Step 5 — Set Secrets

In Render dashboard → each service → Environment:

**Robot service:**
- `METAAPI_TOKEN` — from https://app.metaapi.cloud → API
- `METAAPI_ACCOUNT_ID` — from https://app.metaapi.cloud → Accounts

**Panel service:**
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_OWNER_ID` — your Telegram numeric user ID
- `PANEL_ENCRYPTION_KEY` — from `python -m telegram_panel.main --generate-key`

### Step 6 — Deploy and Verify

1. Click Deploy
2. Watch robot service logs for: `✅ MetaAPI connected and synchronized`
3. Send `/start` to your Telegram bot
4. Verify bot responds with dashboard

---

## OPTION 2 — VPS / Linux (systemd)

### Prerequisites

```bash
# Python 3.11
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### Installation

```bash
# 1. Clone or copy project
cd /opt
git clone https://github.com/your-org/goldscalper-v4.git
cd goldscalper-v4

# 2. Create virtual environments
python3.11 -m venv venv_robot
python3.11 -m venv venv_panel

# 3. Install dependencies
./venv_robot/bin/pip install -r live_trading/requirements.txt
./venv_panel/bin/pip install -r telegram_panel/requirements.txt

# 4. Create data directory
mkdir -p /data/goldscalper
chmod 700 /data/goldscalper
```

### Environment File

```bash
# /etc/goldscalper/robot.env
METAAPI_TOKEN=your_token
METAAPI_ACCOUNT_ID=your_account_id
SYMBOL=XAUUSD
RISK_PERCENT=1.0
MIN_CONFIRMATIONS=3
DAILY_LOSS_LIMIT_PCT=3.0
MAX_DRAWDOWN_PCT=8.0
SLIPPAGE_POINTS=30
STATE_FILE=/data/goldscalper/robot_state.json
MT5_SNAPSHOT=/data/goldscalper/robot_mt5_snapshot.json
COMMANDS_FILE=/data/goldscalper/robot_commands.json
LOG_FILE=/data/goldscalper/robot.log
```

```bash
# /etc/goldscalper/panel.env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_OWNER_ID=123456789
PANEL_ENCRYPTION_KEY=your_fernet_key
PANEL_DB_PATH=/data/goldscalper/panel.db
ROBOT_STATE_PATH=/data/goldscalper/robot_state.json
ROBOT_LOG_PATH=/data/goldscalper/robot.log
PANEL_LOG_PATH=/data/goldscalper/panel.log
```

```bash
chmod 600 /etc/goldscalper/robot.env
chmod 600 /etc/goldscalper/panel.env
```

### Systemd Service Files

```ini
# /etc/systemd/system/goldscalper-robot.service
[Unit]
Description=GoldScalperPro v4 Live Trading Robot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=goldscalper
Group=goldscalper
WorkingDirectory=/opt/goldscalper-v4
EnvironmentFile=/etc/goldscalper/robot.env
ExecStart=/opt/goldscalper-v4/venv_robot/bin/python -m live_trading.main
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
# Auto-restart on non-zero exit (e.g. MetaAPI auth failure)
# Render equivalent of this is handled by Render's restart policy

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/goldscalper-panel.service
[Unit]
Description=GoldScalperPro v4 Telegram Control Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=goldscalper
Group=goldscalper
WorkingDirectory=/opt/goldscalper-v4
EnvironmentFile=/etc/goldscalper/panel.env
ExecStart=/opt/goldscalper-v4/venv_panel/bin/python -m telegram_panel.main
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable goldscalper-robot goldscalper-panel
sudo systemctl start goldscalper-robot
sudo systemctl start goldscalper-panel

# Verify
sudo systemctl status goldscalper-robot
sudo journalctl -u goldscalper-robot -f
```

---

## OPTION 3 — Docker Compose

```yaml
# docker-compose.yml
version: "3.9"

services:
  robot:
    image: python:3.11-slim
    working_dir: /app
    volumes:
      - .:/app
      - goldscalper_data:/data
    env_file:
      - .env.robot
    command: >
      sh -c "pip install -r live_trading/requirements.txt &&
             python -m live_trading.main"
    restart: on-failure:5

  panel:
    image: python:3.11-slim
    working_dir: /app
    volumes:
      - .:/app
      - goldscalper_data:/data
    env_file:
      - .env.panel
    command: >
      sh -c "pip install -r telegram_panel/requirements.txt &&
             python -m telegram_panel.main"
    restart: on-failure:5

volumes:
  goldscalper_data:
    driver: local
```

```bash
# Run
docker-compose up -d

# Logs
docker-compose logs -f robot
docker-compose logs -f panel
```

---

## PERSISTENT STORAGE — PLATFORM LIMITATIONS

**Critical finding from audit:** Render uses an ephemeral filesystem. Without a persistent disk, the following data is lost on EVERY container restart:

| Data | Impact of Loss |
|------|---------------|
| `robot_state.json` | Trade history lost; Guardian reinitializes from current balance (safe) |
| `robot_commands.json` | Pending stop commands lost; robot continues running |
| `robot_mt5_snapshot.json` | Panel shows stale data until next bar |
| `panel.db` | ALL accounts, users, sessions, audit logs permanently lost |
| `robot.log` | Historical logs lost |

**This is a PLATFORM LIMITATION — it cannot be fixed in code.** The solution is a persistent disk (Render), a persistent volume (Docker), or a persistent data directory on a VPS.

---

## INSTALLATION VERIFICATION

After deploying, verify these are working before enabling live capital:

```bash
# 1. Robot is connected
# Look for this in robot logs:
✅ MetaAPI connected and synchronized

# 2. Guardian is initialized
# Look for:
Guardian initialized: balance=XXXX equity=XXXX

# 3. Robot is scanning bars
# Look for (every 5 minutes):
─── Bar #N at 2024-01-15T10:00:00+00:00 ───

# 4. Panel responds
# Send /status to your Telegram bot — should show robot status

# 5. State file exists and is written
cat /data/goldscalper/robot_state.json | python -m json.tool
```

---

## UPGRADE PROCEDURE

```bash
# 1. Stop both services
sudo systemctl stop goldscalper-robot goldscalper-panel
# or: Render dashboard → Suspend services

# 2. Backup current state
cp -r /data/goldscalper /data/goldscalper_backup_$(date +%Y%m%d)

# 3. Pull new code
cd /opt/goldscalper-v4
git pull origin main

# 4. Re-install dependencies (new versions may be pinned)
./venv_robot/bin/pip install -r live_trading/requirements.txt
./venv_panel/bin/pip install -r telegram_panel/requirements.txt

# 5. Run engineering tests
./venv_robot/bin/python -m pytest tests/ -v

# 6. Start services
sudo systemctl start goldscalper-robot goldscalper-panel

# 7. Verify
sudo journalctl -u goldscalper-robot -n 50
```
