#!/usr/bin/env python3
"""
vps-manager/run.py  v3
─────────────────────────────────────────────────────────────────
VPS Manager — interactive terminal UI.

Keys:
  ↑/↓  navigate    Enter  confirm/open
  Esc  back         q     quit (main menu)
  n    new project  N     nginx   s  SSL
  m    monitor      t     bot     e  errors
"""

import curses
import os
import sys
import time
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils import config as cfg_mod
from utils import systemctl as svc_mod
from utils import nginx as nginx_mod
from utils import logger as log_mod
from utils import monitor as mon_mod
from utils import ssl as ssl_mod
from utils.tui import (
    init_colors, safe_addstr, draw_header, draw_footer, flash,
    menu, confirm, pager, form, FormField,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_ENTER, KEY_ESC, KEY_BACK, KEY_QUIT, KEY_SPACE, KEY_HELP,
    is_key,
    CP_SELECTED, CP_TITLE, CP_STATUS_OK, CP_STATUS_ERR,
    CP_STATUS_WAR, CP_DIM, CP_BORDER,
    status_attr, help_menu
)

PROJECT_TYPES = ["django", "fastapi", "flask", "nodejs", "react", "aiogram", "custom"]

DEFAULT_COMMANDS = {
    "django":  "{python} {project_path}/manage.py runserver 0.0.0.0:{port}",
    "fastapi": "gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:{port} run:app",
    "flask":   "gunicorn -w 4 -b 0.0.0.0:{port} app:app",
    "nodejs":  "node {project_path}/index.js",
    "react":   "node {project_path}/server.js",
    "aiogram": "{python} {project_path}/bot.py",
    "custom":  "{python} {project_path}/main.py",
}

DEFAULT_ROUTES = {
    "django":  "/",
    "fastapi": "/api/",
    "flask":   "/",
    "nodejs":  "/",
    "react":   "/",
    "aiogram": None,
    "custom":  None,
}

STARTUP_COMMANDS = [
    'sudo apt install certbot python3-certbot-nginx -y',
    'sudo apt install nginx -y',
    'python3 -m venv venv',
    'sudo apt install python3-pip'
]

# ── Detect the Python that is actually running this script ────────────────────
CURRENT_PYTHON = sys.executable   # e.g. /home/ako/Desktop/vps-manager/venv/bin/python3
CURRENT_VENV   = os.path.dirname(os.path.dirname(CURRENT_PYTHON)) \
                 if "bin" in CURRENT_PYTHON else ""

# Bot lives inside vps-manager/bot/
BOT_SCRIPT  = os.path.join(BASE_DIR, "bot", "admin_bot.py")
# Use the same python that runs run.py — no separate venv needed
BOT_PYTHON  = CURRENT_PYTHON
BOT_VENV    = CURRENT_VENV


# ─── Helpers ──────────────────────────────────────────────────────────────────

def collect_errors(config):
    errors = []
    for p in config.get("projects", []):
        name = p["name"]
        if not svc_mod.unit_file_exists(name):
            continue
        st = svc_mod.get_service_status(name)
        if st["state"] in ("failed", "error"):
            last_log = st["logs"].splitlines()[-1] if st["logs"] else ""
            errors.append({
                "name": name, "state": st["state"],
                "last_log": last_log,
                "status_text": st["status_text"],
                "logs": st["logs"],
            })
    return errors


def service_state_label(project_name):
    if not svc_mod.unit_file_exists(project_name):
        return "no-unit"
    return svc_mod.get_service_status(project_name)["state"]


def build_run_command(ptype, project_path, port, python):
    tmpl = DEFAULT_COMMANDS.get(ptype, DEFAULT_COMMANDS["custom"])
    return tmpl.format(
        python=python or "python3",
        project_path=project_path.rstrip("/"),
        port=port or "8000",
    )


def _sysbar():
    try:
        cpu = mon_mod.cpu_percent()
        mem = mon_mod.memory_info()
        up  = mon_mod.uptime_str()
        return (f"  CPU {cpu:4.1f}%  "
                f"MEM {mem['used_mb']:.0f}/{mem['total_mb']:.0f} MB  "
                f"up {up}")
    except Exception:
        return "  system metrics unavailable"


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

def screen_dashboard(stdscr):
    curses.curs_set(0)
    idx      = 0
    last_msg = ("", True)

    while True:
        config   = cfg_mod.load_config()
        projects = config.get("projects", [])
        errors   = collect_errors(config)

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        err_badge = f"  [{len(errors)} error(s)]" if errors else ""
        draw_header(stdscr, "Dashboard" + err_badge)
        draw_footer(stdscr, [
            ("↑↓", "nav"), ("Enter", "open"), ("n", "new"),
            ("N", "nginx"), ("s", "SSL"), ("m", "monitor"),
            ("t", "bot"), ("e", "errors"), ("q", "quit"), ("H", "help"),
        ])

        row = 1

        if errors:
            row += 1
            stdscr.attron(curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)
            stdscr.hline(row, 0, ' ', w)
            safe_addstr(stdscr, row, 0,
                f"  ! {len(errors)} service(s) in error state — press [e] to view",
                curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)
            stdscr.attroff(curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)

        if last_msg[0]:
            row += 1
            attr = (curses.color_pair(CP_STATUS_OK) if last_msg[1]
                    else curses.color_pair(CP_STATUS_ERR))
            safe_addstr(stdscr, row, 2, last_msg[0][:w - 4], attr)

        row += 1
        safe_addstr(stdscr, row, 0, _sysbar()[:w - 1], curses.color_pair(CP_DIM))

        row += 1
        name_w  = max(18, w // 4)
        type_w  = 10
        port_w  = 7
        route_w = 14
        hdr = (f"  {'':2}  {'Name':<{name_w}}  {'Type':<{type_w}}"
               f"  {'Port':<{port_w}}  {'Route':<{route_w}}  Status")
        safe_addstr(stdscr, row, 0, hdr[:w - 1], curses.color_pair(CP_DIM))
        stdscr.hline(row + 1, 0, curses.ACS_HLINE, w)
        list_start = row + 2

        if not projects:
            safe_addstr(stdscr, list_start + 1, 4,
                "No projects yet.  Press [n] to add one.",
                curses.color_pair(CP_DIM))
        else:
            idx = max(0, min(idx, len(projects) - 1))
            for i, p in enumerate(projects):
                r = list_start + i
                if r >= h - 1:
                    break
                is_sel = (i == idx)
                name   = p["name"]
                ptype  = p.get("type",  "?")
                port   = str(p.get("port", "—"))
                route  = p.get("route", "—") or "—"
                state  = service_state_label(name)
                prefix = " ▶ " if is_sel else "   "

                if is_sel:
                    stdscr.attron(curses.color_pair(CP_SELECTED) | curses.A_BOLD)
                    stdscr.hline(r, 0, ' ', w)

                base = (curses.color_pair(CP_SELECTED) | curses.A_BOLD) if is_sel else 0
                safe_addstr(stdscr, r, 0,
                    f"{prefix}{name:<{name_w}}  {ptype:<{type_w}}"
                    f"  {port:<{port_w}}  {route:<{route_w}} ", base)

                if is_sel:
                    stdscr.attroff(curses.color_pair(CP_SELECTED) | curses.A_BOLD)

                sx = 3 + name_w + 2 + type_w + 2 + port_w + 2 + route_w + 1
                safe_addstr(stdscr, r, sx, state, status_attr(state))

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_UP):
            idx = max(0, idx - 1)
        elif is_key(ch, KEY_DOWN):
            idx = min(max(0, len(projects) - 1), idx + 1)
        elif is_key(ch, KEY_ENTER) and projects:
            result = screen_project_menu(stdscr, projects[idx], config)
            if result:
                last_msg = result
        elif ch == ord('n'):
            result = screen_add_project(stdscr, config)
            if result:
                last_msg = result
        elif ch == ord('N'):
            result = screen_nginx_menu(stdscr, config)
            if result:
                last_msg = result
        elif ch == ord('s'):
            screen_ssl_menu(stdscr, config)
            last_msg = ("", True)
        elif ch == ord('m'):
            screen_monitor(stdscr, config)
            last_msg = ("", True)
        elif ch == ord('t'):
            result = screen_bot_menu(stdscr, config)
            if result:
                last_msg = result
        elif ch == ord('e'):
            screen_errors(stdscr, errors)
            last_msg = ("", True)
        elif is_key(ch, KEY_HELP):
            help_menu(stdscr)
        elif is_key(ch, KEY_QUIT):
            if confirm(stdscr, "Exit VPS Manager?", default=False):
                return


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Per-project menu
# ═══════════════════════════════════════════════════════════════════════════════

def screen_project_menu(stdscr, project, config):
    name     = project["name"]
    state    = service_state_label(name)
    has_unit = svc_mod.unit_file_exists(name)
    has_port = bool(project.get("port"))

    items = [
        "Start service",
        "Stop service",
        "Restart service",
        "--- Status & Logs",
        "View service status",
        "View logs (journal)",
        "--- Monitoring",
        "Live resource usage",
        "--- Configuration",
        "Edit project",
        "View nginx config",
        "Apply nginx config",
        "--- Danger",
        "Remove project",
    ]
    actions = [
        "start", "stop", "restart",
        None,
        "status", "logs",
        None,
        "resources",
        None,
        "edit", "nginx_preview", "nginx_apply",
        None,
        "remove",
    ]

    choice = menu(stdscr, f"Project: {name}", items,
                  subtitle=(f"type={project.get('type','?')}  "
                            f"port={project.get('port','—')}  "
                            f"state={state}"),
                  footer_hints=[("↑↓", "navigate"), ("Enter", "select"), ("Esc", "back")])
    if choice is None:
        return None

    action = actions[choice]
    if not action:
        return None

    if action == "start":
        if not has_unit:
            ok, msg = svc_mod.write_unit_file(project)
            if not ok:
                flash(stdscr, msg, ok=False)
                return (msg, False)
        ok, msg = svc_mod.start_service(name)
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"start {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    elif action == "stop":
        ok, msg = svc_mod.stop_service(name)
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"stop {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    elif action == "restart":
        ok, msg = svc_mod.restart_service(name)
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"restart {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    elif action == "status":
        if not has_unit:
            flash(stdscr, "No systemd unit file.", ok=False)
            return None
        st   = svc_mod.get_service_status(name)
        text = st["status_text"] + "\n\n─── Recent logs ───\n" + st["logs"]
        pager(stdscr, f"Status: {name}", text)
        return None

    elif action == "logs":
        if not has_unit:
            flash(stdscr, "No systemd unit file.", ok=False)
            return None
        st = svc_mod.get_service_status(name)
        pager(stdscr, f"Logs: {name}", st["logs"])
        return None

    elif action == "resources":
        screen_service_monitor(stdscr, name)
        return None

    elif action == "edit":
        return screen_edit_project(stdscr, project, config)

    elif action == "nginx_preview":
        if not has_port:
            flash(stdscr, "No port — no nginx block.", ok=False)
            return None
        pager(stdscr, f"Nginx: {name}", nginx_mod.nginx_config_preview(project, config))
        return None

    elif action == "nginx_apply":
        if not has_port:
            flash(stdscr, "No port — skip nginx.", ok=False)
            return None
        ok1, m1 = nginx_mod.write_nginx_config(project, config)
        ok2, m2 = nginx_mod.reload_nginx()
        msg = f"{m1}  |  {m2}"
        flash(stdscr, msg, ok=ok1 and ok2)
        log_mod.log(f"nginx apply {name}: {msg}", "info" if ok1 and ok2 else "error")
        return (msg, ok1 and ok2)

    elif action == "remove":
        if not confirm(stdscr,
                       f"Remove '{name}'? Stops service, removes unit & nginx config.",
                       default=False):
            return None
        svc_mod.stop_service(name)
        svc_mod.remove_unit_file(name)
        if has_port:
            nginx_mod.remove_nginx_config(name, config)
            nginx_mod.reload_nginx()
        cfg_mod.remove_project(config, name)
        flash(stdscr, f"Removed '{name}'", ok=True)
        log_mod.log(f"removed {name}", "info")
        return (f"Removed {name}", True)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Live service resource monitor
# ═══════════════════════════════════════════════════════════════════════════════

def screen_service_monitor(stdscr, project_name):
    curses.curs_set(0)
    while True:
        sdata = mon_mod.service_metrics(project_name)
        cpu   = mon_mod.cpu_percent()
        mem   = mon_mod.memory_info()

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, f"Resources: {project_name}")
        draw_footer(stdscr, [("q/Esc", "back")])

        def bar(val, mx, width=30):
            pct    = min(1.0, val / mx) if mx else 0
            filled = int(pct * width)
            return "[" + "█" * filled + "░" * (width - filled) + f"] {pct*100:4.0f}%"

        rows = [
            ("", ""),
            ("Service CPU",    f"{sdata['cpu_percent']:6.1f}%  {bar(sdata['cpu_percent'], 100)}"),
            ("Service Memory", f"{sdata['mem_mb']:6.1f} MB  {bar(sdata['mem_mb'], mem['total_mb'])}"),
            ("Service PID",    str(sdata["pid"]) if sdata["pid"] else "— (not running)"),
            ("", ""),
            ("System CPU",     f"{cpu:6.1f}%  {bar(cpu, 100)}"),
            ("System Memory",  f"{mem['used_mb']:6.0f}/{mem['total_mb']:.0f} MB  {bar(mem['used_mb'], mem['total_mb'])}"),
            ("", ""),
        ]

        lw = 18
        for i, (label, value) in enumerate(rows):
            r = 3 + i
            if r >= h - 1:
                break
            if not label:
                continue
            safe_addstr(stdscr, r, 2, f"{label:<{lw}}", curses.color_pair(CP_DIM))
            safe_addstr(stdscr, r, 2 + lw + 2, value[:w - lw - 6])

        ts = time.strftime("%H:%M:%S")
        safe_addstr(stdscr, h - 2, w - 12, ts, curses.color_pair(CP_DIM))
        stdscr.refresh()

        stdscr.timeout(1000)
        ch = stdscr.getch()
        stdscr.timeout(-1)
        if is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK):
            break


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: System-wide monitor
# ═══════════════════════════════════════════════════════════════════════════════

def screen_monitor(stdscr, config):
    curses.curs_set(0)
    projects = config.get("projects", [])
    names    = [p["name"] for p in projects]

    while True:
        try:
            cpu  = mon_mod.cpu_percent()
            mem  = mon_mod.memory_info()
            disk = mon_mod.disk_info()
            la   = mon_mod.load_avg()
            up   = mon_mod.uptime_str()
            svc_data = {n: mon_mod.service_metrics(n) for n in names}
        except Exception as e:
            pager(stdscr, "Monitor Error", str(e))
            return

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, "System Monitor")
        draw_footer(stdscr, [("q/Esc", "back"), ("s", "save PNG"), ("auto", "refresh 2s")])

        def bar(val, mx, width=24):
            pct    = min(1.0, val / mx) if mx else 0
            filled = int(pct * width)
            return "[" + "█" * filled + "░" * (width - filled) + f"] {pct*100:4.1f}%"

        r = 2
        safe_addstr(stdscr, r, 2,
            f"  Uptime: {up}   Load: {la[0]:.2f} {la[1]:.2f} {la[2]:.2f}   {time.strftime('%H:%M:%S')}",
            curses.color_pair(CP_DIM))
        r += 1
        stdscr.hline(r, 0, curses.ACS_HLINE, w)
        r += 1

        lw = 14
        for label, val in [
            ("CPU",    f"{cpu:6.1f}%   {bar(cpu, 100)}"),
            ("Memory", f"{mem['used_mb']:6.0f}/{mem['total_mb']:.0f} MB  {bar(mem['used_mb'], mem['total_mb'])}"),
            ("Disk",   f"{disk['used_gb']:6.1f}/{disk['total_gb']:.1f} GB  {bar(disk['used_gb'], disk['total_gb'])}"),
        ]:
            if r >= h - 1:
                break
            safe_addstr(stdscr, r, 2, f"{label:<{lw}}", curses.color_pair(CP_DIM))
            safe_addstr(stdscr, r, 2 + lw + 2, val[:w - lw - 6])
            r += 1

        if svc_data:
            r += 1
            if r < h - 1:
                stdscr.hline(r, 0, curses.ACS_HLINE, w)
                r += 1
            max_cpu = max((v["cpu_percent"] for v in svc_data.values()), default=1) or 1
            max_mem = max((v["mem_mb"]      for v in svc_data.values()), default=1) or 1
            for sname, sd in svc_data.items():
                if r >= h - 2:
                    break
                pid_str = str(sd["pid"]) if sd["pid"] else "—"
                safe_addstr(stdscr, r, 2,
                    f"{sname:<20}  CPU {sd['cpu_percent']:5.1f}%  {bar(sd['cpu_percent'], max(max_cpu,0.1), 18)}"[:w-3])
                r += 1
                if r < h - 1:
                    safe_addstr(stdscr, r, 2,
                        f"{'':20}  MEM {sd['mem_mb']:5.1f}MB  {bar(sd['mem_mb'], max(max_mem,0.1), 18)}  PID {pid_str}"[:w-3],
                        curses.color_pair(CP_DIM))
                    r += 1

        stdscr.refresh()
        stdscr.timeout(2000)
        ch = stdscr.getch()
        stdscr.timeout(-1)
        if is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK):
            break
        elif ch == ord('s'):
            snapshot = mon_mod.full_snapshot(names)
            os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False,
                dir=os.path.join(BASE_DIR, "logs"),
                prefix="monitor_"
            ) as tmp:
                tmp_path = tmp.name
            ok = mon_mod.generate_monitor_image(snapshot, tmp_path)
            flash(stdscr, f"PNG saved: {tmp_path}" if ok else "matplotlib not installed", ok=ok)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Add project
# ═══════════════════════════════════════════════════════════════════════════════

def screen_add_project(stdscr, config):
    type_choice = menu(stdscr, "Add Project — Choose Type", PROJECT_TYPES,
                       subtitle="Select the project framework / runtime",
                       footer_hints=[("↑↓", "choose"), ("Enter", "select"), ("Esc", "cancel")])
    if type_choice is None:
        return None
    ptype = PROJECT_TYPES[type_choice]

    fields = [
        FormField("name",         "Project name",      required=True,
                  hint="Unique identifier, e.g. my_fastapi"),
        FormField("project_path", "Project path",      default="/root/",
                  required=True, hint="Absolute path to the project directory"),
        FormField("port",         "Port",
                  hint="Leave blank for bots / background workers"),
        FormField("route",        "Nginx route",
                  default=DEFAULT_ROUTES.get(ptype, "") or "",
                  hint="e.g. /  or  /api/  — leave blank if no web exposure"),
        FormField("venv_path",    "Python / venv path",
                  default=CURRENT_PYTHON,
                  hint="Full path to python3 binary, e.g. /root/proj/venv/bin/python3"),
        FormField("runcommand",   "Run command", required=True,
                  hint="Full command to start the service"),
    ]
    fields[-1].value = build_run_command(ptype, "/root/", "", CURRENT_PYTHON)

    data = form(stdscr, f"Add Project ({ptype})", fields)
    if data is None:
        return None

    port_val = None
    if data["port"].strip():
        try:
            port_val = int(data["port"].strip())
        except ValueError:
            flash(stdscr, f"Invalid port '{data['port']}'", ok=False)
            return None
        if cfg_mod.is_port_taken(config, port_val):
            flash(stdscr, f"Port {port_val} already taken.", ok=False)
            return None

    project = {
        "name":         data["name"],
        "type":         ptype,
        "project_path": data["project_path"],
        "runcommand":   data["runcommand"],
        "venv_path":    data["venv_path"] or None,
    }
    if port_val:
        project["port"]  = port_val
    if data.get("route"):
        project["route"] = data["route"]

    errs = cfg_mod.validate_project(project)
    if errs:
        pager(stdscr, "Validation Errors", "\n".join(errs))
        return None

    try:
        cfg_mod.add_project(config, project)
    except ValueError as e:
        flash(stdscr, str(e), ok=False)
        return (str(e), False)

    if confirm(stdscr, f"Write systemd unit for '{project['name']}' now?", default=True):
        ok, msg = svc_mod.write_unit_file(project)
        flash(stdscr, msg, ok=ok)

    if port_val and confirm(stdscr, f"Apply nginx config for '{project['name']}'?", default=True):
        cfg2 = cfg_mod.load_config()
        ok1, m1 = nginx_mod.write_nginx_config(project, cfg2)
        ok2, m2 = nginx_mod.reload_nginx()
        flash(stdscr, f"{m1} | {m2}", ok=ok1 and ok2)

    msg = f"Project '{project['name']}' added."
    log_mod.log(msg, "info")
    return (msg, True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Edit project
# ═══════════════════════════════════════════════════════════════════════════════

def screen_edit_project(stdscr, project, config):
    name = project["name"]
    fields = [
        FormField("project_path", "Project path",  default=project.get("project_path", "")),
        FormField("port",         "Port",           default=str(project.get("port", ""))),
        FormField("route",        "Nginx route",    default=project.get("route", "")),
        FormField("venv_path",    "Python / venv",  default=project.get("venv_path", "")),
        FormField("runcommand",   "Run command",    default=project.get("runcommand", ""),
                  required=True),
    ]
    data = form(stdscr, f"Edit Project: {name}", fields)
    if data is None:
        return None

    port_val = project.get("port")
    if data["port"].strip():
        try:
            port_val = int(data["port"].strip())
        except ValueError:
            flash(stdscr, "Invalid port.", ok=False)
            return None
        if cfg_mod.is_port_taken(config, port_val, exclude_name=name):
            flash(stdscr, f"Port {port_val} is taken.", ok=False)
            return None

    cfg_mod.update_project(config, name, {
        "project_path": data["project_path"],
        "runcommand":   data["runcommand"],
        "venv_path":    data["venv_path"] or None,
        "port":         port_val,
        "route":        data.get("route") or None,
    })
    updated = cfg_mod.get_project(cfg_mod.load_config(), name)
    ok, msg = svc_mod.write_unit_file(updated)
    flash(stdscr, f"Saved. {msg}", ok=ok)
    log_mod.log(f"edited {name}", "info")
    return (f"Updated {name}", ok)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Nginx menu
# ═══════════════════════════════════════════════════════════════════════════════

def screen_nginx_menu(stdscr, config):
    items = [
        "Apply all nginx configs",
        "Reload nginx",
        "Preview combined nginx config",
        "Edit nginx settings",
    ]
    choice = menu(stdscr, "Nginx Management", items,
                  footer_hints=[("↑↓", "navigate"), ("Enter", "select"), ("Esc", "back")])
    if choice is None:
        return None

    if choice == 0:
        msgs   = []
        ok_all = True
        for p in config.get("projects", []):
            if not p.get("port"):
                continue
            ok, m = nginx_mod.write_nginx_config(p, config)
            msgs.append(f"{p['name']}: {'OK' if ok else 'FAIL'}")
            ok_all &= ok
        ok2, m2 = nginx_mod.reload_nginx()
        msgs.append(f"Reload: {'OK' if ok2 else 'FAIL'}  {m2}")
        pager(stdscr, "Nginx Apply Results", "\n".join(msgs))
        return ("\n".join(msgs), ok_all and ok2)

    elif choice == 1:
        ok, msg = nginx_mod.reload_nginx()
        flash(stdscr, msg, ok=ok)
        return (msg, ok)

    elif choice == 2:
        pager(stdscr, "Combined Nginx Config",
              nginx_mod.generate_combined_nginx_config(config))
        return None

    elif choice == 3:
        ng = config.get("nginx", {})
        fields = [
            FormField("server_name",    "Server name",     default=ng.get("server_name", "_"),
                      hint="nginx server_name, e.g. example.com or _"),
            FormField("error_page_dir", "Error page dir",  default=ng.get("error_page_dir", "/var/www/vps-manager-errors")),
            FormField("config_dir",     "sites-available", default=ng.get("config_dir", "/etc/nginx/sites-available")),
            FormField("enabled_dir",    "sites-enabled",   default=ng.get("enabled_dir", "/etc/nginx/sites-enabled")),
        ]
        data = form(stdscr, "Edit Nginx Settings", fields)
        if data:
            config["nginx"].update(data)
            cfg_mod.save_config(config)
            flash(stdscr, "Nginx settings saved.", ok=True)
            return ("Nginx settings updated", True)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: SSL menu
# ═══════════════════════════════════════════════════════════════════════════════

def screen_ssl_menu(stdscr, config):
    if not ssl_mod.certbot_available():
        pager(stdscr, "SSL — certbot not found",
              "certbot is not installed.\n\n"
              "Install with:\n"
              "  sudo apt install certbot python3-certbot-nginx -y\n\n"
              "Then run this menu again.")
        return

    items = [
        "View certificate status",
        "Obtain certificate (--nginx)",
        "Obtain certificate (--webroot)",
        "Renew all certificates",
        "Renew (dry run — test only)",
        "Revoke certificate",
    ]
    choice = menu(stdscr, "SSL / Let's Encrypt", items,
                  subtitle=f"certbot: {ssl_mod.certbot_version()}",
                  footer_hints=[("↑↓", "navigate"), ("Enter", "select"), ("Esc", "back")])
    if choice is None:
        return

    if choice == 0:
        certs = ssl_mod.list_certificates()
        if not certs:
            flash(stdscr, "No certificates found.", ok=False)
            return
        lines = []
        for c in certs:
            days = None
            for d in c.get("domains", []):
                days = ssl_mod.certificate_expiry_days(d)
                if days is not None:
                    break
            status = ssl_mod.ssl_status_text(c.get("name", ""))
            lines.append(
                f"Name   : {c.get('name','?')}\n"
                f"Domains: {' '.join(c.get('domains',[]))}\n"
                f"Expires: {c.get('expiry','?')}\n"
                f"Status : {status}\n"
                f"Path   : {c.get('path','?')}\n"
            )
        pager(stdscr, "SSL Certificates", "\n─────────────\n".join(lines))

    elif choice in (1, 2):
        plugin = "nginx" if choice == 1 else "webroot"
        fields = [
            FormField("domains", "Domains (space-separated)",
                      required=True, hint="e.g. example.com www.example.com"),
            FormField("email",   "Email (optional)",
                      hint="Let's Encrypt notification email"),
        ]
        if plugin == "webroot":
            fields.append(FormField("webroot", "Webroot path",
                                    default="/var/www/html", required=True))

        data = form(stdscr, f"Obtain Certificate ({plugin})", fields)
        if data is None:
            return

        domains = data["domains"].split()
        email   = data.get("email", "").strip()
        webroot = data.get("webroot", None)

        if not domains:
            flash(stdscr, "No domains entered.", ok=False)
            return
        if not confirm(stdscr, f"Obtain SSL cert for: {', '.join(domains)} ?", default=True):
            return

        flash(stdscr, "Running certbot… (this may take ~30s)", ok=True)
        stdscr.refresh()
        ok, output = ssl_mod.obtain_certificate(domains, email=email, webroot=webroot)
        pager(stdscr, f"certbot output ({'OK' if ok else 'FAIL'})", output)
        log_mod.log(f"SSL obtain {domains}: {'ok' if ok else 'fail'}", "info" if ok else "error")

        if ok and confirm(stdscr, "Reload nginx to activate HTTPS?", default=True):
            ok2, m2 = nginx_mod.reload_nginx()
            flash(stdscr, m2, ok=ok2)

    elif choice == 3:
        if not confirm(stdscr, "Renew all Let's Encrypt certificates now?", default=True):
            return
        flash(stdscr, "Running certbot renew…", ok=True)
        stdscr.refresh()
        ok, output = ssl_mod.renew_certificates(dry_run=False)
        pager(stdscr, f"certbot renew ({'OK' if ok else 'FAIL'})", output)
        log_mod.log(f"SSL renew all: {'ok' if ok else 'fail'}", "info" if ok else "error")

    elif choice == 4:
        flash(stdscr, "Running certbot renew --dry-run…", ok=True)
        stdscr.refresh()
        ok, output = ssl_mod.renew_certificates(dry_run=True)
        pager(stdscr, f"Dry run ({'OK' if ok else 'FAIL'})", output)

    elif choice == 5:
        fields = [FormField("domain", "Domain to revoke", required=True,
                            hint="Must match the primary domain of the certificate")]
        data = form(stdscr, "Revoke Certificate", fields)
        if not data:
            return
        domain = data["domain"].strip()
        if not confirm(stdscr, f"Revoke certificate for '{domain}'? Cannot be undone.", default=False):
            return
        ok, output = ssl_mod.revoke_certificate(domain)
        pager(stdscr, f"Revoke ({'OK' if ok else 'FAIL'})", output)
        log_mod.log(f"SSL revoke {domain}: {'ok' if ok else 'fail'}", "info" if ok else "error")


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Telegram bot menu  — uses the SAME python/venv as run.py
# ═══════════════════════════════════════════════════════════════════════════════

def _bot_project():
    """Build the bot pseudo-project dict using the current Python executable."""
    return {
        "name":         "vps-admin-bot",
        "type":         "aiogram",
        "project_path": BASE_DIR,
        "runcommand":   f"{BOT_PYTHON} {BOT_SCRIPT}",
        "venv_path":    BOT_VENV or None,
    }


def screen_bot_menu(stdscr, config):
    bot_cfg   = cfg_mod.get_bot_config(config)
    token     = bot_cfg.get("token", "")
    enabled   = bot_cfg.get("enabled", False)
    admin_ids = bot_cfg.get("admin_ids", [])

    state = service_state_label("vps-admin-bot")

    items = [
        "Configure bot token & admin IDs",
        f"{'Disable bot' if enabled else 'Enable bot'}",
        "Start bot service",
        "Stop bot service",
        "Restart bot service",
        "View bot logs",
        "View bot info / paths",
    ]

    choice = menu(stdscr, "Telegram Bot", items,
                  subtitle=(f"token={'set' if token else 'NOT SET'}  "
                            f"admins={len(admin_ids)}  "
                            f"state={state}"),
                  footer_hints=[("↑↓", "navigate"), ("Enter", "select"), ("Esc", "back")])
    if choice is None:
        return None

    # ── Configure ─────────────────────────────────────────────────────────
    if choice == 0:
        fields = [
            FormField("token",     "Bot token",
                      default=token, required=True,
                      hint="From @BotFather — 123456789:AAA..."),
            FormField("admin_ids", "Admin Telegram IDs",
                      default=" ".join(str(x) for x in admin_ids),
                      required=True,
                      hint="Space-separated IDs, e.g. 123456 789012"),
        ]
        data = form(stdscr, "Configure Telegram Bot", fields)
        if not data:
            return None

        ids = [x.strip() for x in data["admin_ids"].split() if x.strip().isdigit()]
        if not ids:
            flash(stdscr, "No valid admin IDs entered.", ok=False)
            return None

        cfg_mod.set_bot_config(config, data["token"].strip(), ids, enabled=True)

        bp = _bot_project()
        ok, msg = svc_mod.write_unit_file(bp)
        if ok:
            flash(stdscr, "Bot configured. Unit written. Use Start to launch.", ok=True)
        else:
            flash(stdscr, f"Config saved but unit file failed: {msg}", ok=False)

        log_mod.log("bot configured", "info")
        return ("Bot configured", True)

    # ── Toggle enable ──────────────────────────────────────────────────────
    elif choice == 1:
        new_state = not enabled
        bot_cfg["enabled"] = new_state
        config["bot"] = bot_cfg
        cfg_mod.save_config(config)
        msg = f"Bot {'enabled' if new_state else 'disabled'}"
        flash(stdscr, msg, ok=True)
        return (msg, True)

    # ── Start ──────────────────────────────────────────────────────────────
    elif choice == 2:
        if not token:
            flash(stdscr, "Configure bot token first (option 1).", ok=False)
            return None
        # Ensure unit file is present and up-to-date
        bp = _bot_project()
        if not svc_mod.unit_file_exists("vps-admin-bot"):
            svc_mod.write_unit_file(bp)
        ok, msg = svc_mod.start_service("vps-admin-bot")
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"bot start: {msg}", "info" if ok else "error")
        return (msg, ok)

    elif choice == 3:
        ok, msg = svc_mod.stop_service("vps-admin-bot")
        flash(stdscr, msg, ok=ok)
        return (msg, ok)

    elif choice == 4:
        ok, msg = svc_mod.restart_service("vps-admin-bot")
        flash(stdscr, msg, ok=ok)
        return (msg, ok)

    # ── Logs ──────────────────────────────────────────────────────────────
    elif choice == 5:
        if not svc_mod.unit_file_exists("vps-admin-bot"):
            flash(stdscr, "Bot service not deployed yet. Configure first.", ok=False)
            return None
        st = svc_mod.get_service_status("vps-admin-bot")
        pager(stdscr, "Bot Logs", st["logs"] or "(no logs)")
        return None

    # ── Info ──────────────────────────────────────────────────────────────
    elif choice == 6:
        masked = (token[:10] + "…" + token[-4:]) if len(token) > 14 else (token or "(not set)")
        text = (
            f"Token     : {masked}\n"
            f"Admins    : {', '.join(str(x) for x in admin_ids) or '(none)'}\n"
            f"Enabled   : {'yes' if enabled else 'no'}\n"
            f"State     : {state}\n\n"
            f"Python    : {BOT_PYTHON}\n"
            f"Venv      : {BOT_VENV or '(none)'}\n"
            f"Script    : {BOT_SCRIPT}\n"
            f"Unit file : /etc/systemd/system/vps-vps-admin-bot.service\n\n"
            f"To install aiogram into this venv run:\n"
            f"  {BOT_PYTHON} -m pip install aiogram==2.25.1\n"
        )
        pager(stdscr, "Bot Info", text)
        return None

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Error viewer
# ═══════════════════════════════════════════════════════════════════════════════

def screen_errors(stdscr, errors):
    if not errors:
        flash(stdscr, "No service errors detected.", ok=True)
        return

    items = [f"{e['name']}  [{e['state']}]  {e['last_log'][:60]}" for e in errors]
    while True:
        choice = menu(stdscr, "Service Errors", items,
                      subtitle="Services in failed/error state",
                      footer_hints=[("↑↓", "navigate"), ("Enter", "details"), ("Esc", "back")])
        if choice is None:
            return
        e    = errors[choice]
        text = (
            f"Service : {e['name']}\n"
            f"State   : {e['state']}\n\n"
            f"─── systemctl status ───\n{e['status_text']}\n\n"
            f"─── journalctl logs ───\n{e['logs']}"
        )
        pager(stdscr, f"Error Detail: {e['name']}", text)


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main(stdscr):
    curses.curs_set(0)
    init_colors()

    stdscr.erase()
    h, w = stdscr.getmaxyx()
    splash = ["VPS Manager  v3", "──────────────────────────────", "Loading…"]
    for i, line in enumerate(splash):
        safe_addstr(stdscr, h // 2 - 1 + i, max(0, w // 2 - len(line) // 2), line)
    stdscr.refresh()
    curses.napms(350)

    try:
        config = cfg_mod.load_config()
    except RuntimeError as e:
        pager(stdscr, "Config Error", str(e))
        return

    screen_dashboard(stdscr)


def run():
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            curses.endwin()
        except Exception:
            pass
    print("vps-manager exited.")


if __name__ == "__main__":
    run()