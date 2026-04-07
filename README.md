# vps-manager

A terminal-based VPS project manager for Linux servers. Manage Django, FastAPI, aiogram, Node.js, and React projects from a single interactive CLI — no manual systemctl editing, no hand-written Nginx configs.

```bash
sudo python3 run.py
```

## Features

- **Interactive TUI** — arrow keys to navigate, Enter to confirm, Esc to go back, no mouse required
- **Project registry** — add, edit, and remove projects stored in config.json
- **systemd integration** — auto-generates .service unit files; start / stop / restart / status from the menu
- **Nginx automation** — generates server blocks from config, writes them to /etc/nginx/sites-available/, and reloads Nginx in one step
- **Error pages** — custom dark-themed 502 / 503 / 504 HTML pages per project written to /var/www/vps-manager-errors/<name>/
- **Error dashboard** — on startup, failed services surface in a red banner; press e to inspect, Enter for full logs, Esc to close
- **Virtual environment support** — per-project venv_path and custom run commands
- **Non-interactive scripts** — scripts/deploy.py, scripts/start_service.py, scripts/stop_service.py for use in CI or cron

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.8+ | stdlib only — no pip installs needed |
| Linux with systemd | Ubuntu 20.04 / 22.04 / Debian 11+ recommended |
| Nginx | apt install nginx |
| Root or sudo | Required for systemctl and Nginx operations |

## Installation

```bash
git clone https://github.com/akhmedcodes/vps-manager.git
cd vps-manager
sudo python3 run.py
```

## Usage

### Launch the TUI

```bash
sudo python3 run.py
```

### Keyboard Reference

| Key | Action |
|---|---|
| ↑ / ↓ | Move selection up / down |
| ← / → | Switch columns / panels |
| Enter | Confirm / open |
| Space | Toggle selection (multi-select screens) |
| Esc | Go back / cancel |
| h / H | For get help |
| e | Open error viewer (from dashboard) |
| q | Quit |

### Main Menu Actions

- **Add project** — fill in name, type, port, route, venv path, and run command via a guided form
- **Start / Stop / Restart** — select a project and choose the action
- **Apply Nginx config** — regenerate and reload Nginx for all registered projects
- **View logs** — scroll through logs/vps-manager.log in the built-in pager

## config.json

Auto-managed by run.py. You can also edit it directly.

```json
{
  "projects": [
    {
      "name": "my_django",
      "type": "django",
      "port": 9900,
      "route": "/",
      "venv_path": "/root/my_django/venv/bin/python3",
      "runcommand": "/root/my_django/manage.py runserver 0.0.0.0:9900"
    },
    {
      "name": "my_fastapi",
      "type": "fastapi",
      "port": 8000,
      "route": "/api/",
      "venv_path": "/root/my_fastapi/venv/bin/python3",
      "runfile": "/root/my_fastapi/run.py",
      "runcommand": "gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 /root/my_fastapi/run:app"
    },
    {
      "name": "my_aiogram_bot",
      "type": "aiogram",
      "venv_path": "/root/my_aiogram/venv/bin/python3",
      "runfile": "/root/my_aiogram/bot.py",
      "runcommand": "/root/my_aiogram/venv/bin/python3 /root/my_aiogram/bot.py"
    }
  ]
}
```

**Field reference**

| Field | Required | Description |
|---|---|---|
| name | Yes | Unique project identifier, used as the systemd service name |
| type | Yes | django, fastapi, aiogram, node, react |
| port | For web projects | Port the app listens on |
| route | For web projects | Nginx location block prefix, e.g. / or /api/ |
| venv_path | No | Path to venv Python binary |
| runfile | No | Main entry file (informational) |
| runcommand | Yes | Exact command used in the systemd ExecStart |

## Before Using vps-manager

### 1. System Requirements

- Ubuntu 20.04 / 22.04 (recommended)
- Root access or sudo user
- Internet connection

### 2. Required APT Packages

Run:
```bash
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  nginx git curl \
  certbot python3-certbot-nginx \
  build-essential
pip3 install aiogram==2.25.1
```

### 3. Python & Libraries

- Python 3.10+ required
- If you use adminbot, install: `pip install aiogram==2.25.1`

⚠️ **Important:**
- Use SAME python as systemd
- Prefer: `python3 -m pip install ...`

### 4. Virtual Environment ( Dont use, its for new version! )

```bash
python3 -m venv venv
source venv/bin/activate
pip install aiogram==2.25.1
```

### 5. Network & Ports

Open required ports:
- 22 → SSH
- 80 → HTTP
- 443 → HTTPS

Check open ports:
```bash
sudo ss -tulnp
```

### 6. Nginx Setup

- Used for reverse proxy
- Auto-configured by vps-manager
- Test config: `sudo nginx -t`

### 7. SSL (HTTPS)

- Uses Let's Encrypt (certbot)
- Check installation: `certbot --version`
- Renew manually: `sudo certbot renew`

⚠️ If error: `sudo apt install certbot`

### 8. systemd Services

Used to run projects in background.

Commands:
```bash
sudo systemctl status <name>
sudo systemctl restart <name>
```

### 9. Project Requirements

Each project should have:
- runcommand (python, node, etc.)
- port (for web projects)
- working directory

### 10. Common Errors

- aiogram not installed → `pip install aiogram==2.25.1`
- certbot not found → `apt install certbot`
- port in use → change port
- permission denied → use `sudo`

## Nginx Integration

When you select **Apply Nginx config** from the menu, vps-manager:

1. Generates a server block for each project that has a port and route
2. Writes it to `/etc/nginx/sites-available/vps-manager-<name>.conf`
3. Creates a symlink in `sites-enabled/`
4. Writes custom error pages to `/var/www/vps-manager-errors/<name>/`
5. Runs `nginx -t` to validate, then `systemctl reload nginx`

Example generated block:

```nginx
server {
    listen 80;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        error_page 502 /502.html;
        error_page 503 /503.html;
        error_page 504 /504.html;

        location /vps-errors/my_fastapi/ {
            root /var/www/vps-manager-errors/my_fastapi;
            internal;
        }
    }
}
```

## Error Dashboard

Every time the TUI redraws, it polls `systemctl is-failed` for all registered services. If any are in a failed state:

- A banner appears at the top of the dashboard showing the count
- Press `e` to open the error list
- Highlight a project and press Enter to read the full systemctl status output plus the last 30 journal lines in the built-in pager
- Press Esc to close the pager and return

## Non-Interactive Scripts

Useful for deployment pipelines, cron jobs, or remote execution.

```bash
# Deploy (generate unit + nginx + start) a project by name
sudo python3 scripts/deploy.py my_fastapi

# Start / stop by name
sudo python3 scripts/start_service.py my_django
sudo python3 scripts/stop_service.py my_django
```

## Supported Project Types

| Type | Default run pattern |
|---|---|
| django | python3 manage.py runserver 0.0.0.0:<port> |
| fastapi | gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:<port> run:app |
| aiogram | python3 bot.py |
| node | node index.js |
| react | serve -s build -l <port> |

All defaults are overridable via the `runcommand` field in config.json or the add-project form.

## Logging

All operations are appended to `logs/vps-manager.log`:

```
2026-04-07 14:22:01 INFO  Started service my_fastapi
2026-04-07 14:22:05 ERROR nginx -t failed: missing semicolon at line 12
```
---

> Built by [@akhmedcodes](https://github.com/akhmedcodes)