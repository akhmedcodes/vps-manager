#!/usr/bin/env python3
"""
vps-manager/run.py
──────────────────
Main interactive CLI entry point for VPS Manager.

Navigation:
  ↑ / ↓  or  W / S   →  move through list
  ← / →  or  A / D   →  switch panels / toggle buttons
  Space               →  (multi-select where applicable)
  Enter               →  confirm / open
  Esc / b / B         →  back / cancel
  q / Q               →  quit (from main menu)
"""

import curses
import os
import sys
import textwrap
from typing import Optional, List

# ── path setup ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from utils import config as cfg_mod
from utils import systemctl as svc_mod
from utils import nginx as nginx_mod
from utils import logger as log_mod
from utils.tui import (
    init_colors, safe_addstr, draw_header, draw_footer, flash,
    menu, confirm, pager, form, FormField,
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_ENTER, KEY_ESC, KEY_BACK, KEY_QUIT, KEY_SPACE,
    is_key,
    CP_SELECTED, CP_TITLE, CP_STATUS_OK, CP_STATUS_ERR,
    CP_STATUS_WAR, CP_DIM, CP_BORDER,
    status_attr,
)

# ── project types & defaults ──────────────────────────────────────────────────
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


# ── helpers ───────────────────────────────────────────────────────────────────

def collect_errors(config: dict) -> List[dict]:
    """
    Collect all projects that have a Failed/Error systemd state.
    Returns list of {name, state, last_log}.
    """
    errors = []
    for p in config.get("projects", []):
        name = p["name"]
        if not svc_mod.unit_file_exists(name):
            continue
        st = svc_mod.get_service_status(name)
        if st["state"] in ("failed", "error"):
            last_log = st["logs"].splitlines()[-1] if st["logs"] else ""
            errors.append({"name": name, "state": st["state"], "last_log": last_log,
                           "status_text": st["status_text"], "logs": st["logs"]})
    return errors


def service_state_label(project_name: str) -> str:
    if not svc_mod.unit_file_exists(project_name):
        return "no-unit"
    st = svc_mod.get_service_status(project_name)
    return st["state"]


def build_run_command(ptype: str, project_path: str, port: str, python: str) -> str:
    template = DEFAULT_COMMANDS.get(ptype, DEFAULT_COMMANDS["custom"])
    return template.format(
        python=python or "python3",
        project_path=project_path.rstrip("/"),
        port=port or "8000",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Dashboard (project list)
# ═══════════════════════════════════════════════════════════════════════════════

def screen_dashboard(stdscr):
    curses.curs_set(0)
    idx = 0
    last_msg = ("", True)

    while True:
        config   = cfg_mod.load_config()
        projects = config.get("projects", [])
        errors   = collect_errors(config)

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        err_badge = f"  [{len(errors)} error(s)]" if errors else ""
        draw_header(stdscr, "Dashboard" + err_badge)
        draw_footer(stdscr, [
            ("↑↓", "navigate"), ("Enter", "manage"), ("n", "new project"),
            ("N", "nginx"), ("e", "errors"), ("q", "quit"),
        ])

        # Error notice bar (row 2)
        if errors:
            stdscr.attron(curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)
            stdscr.hline(2, 0, ' ', w)
            msg = f"  ! {len(errors)} service(s) in error state — press [e] to view"
            safe_addstr(stdscr, 2, 0, msg[:w - 1],
                        curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)
            stdscr.attroff(curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD)

        # Flash last action message
        if last_msg[0]:
            row = 3 if errors else 2
            attr = curses.color_pair(CP_STATUS_OK) if last_msg[1] else curses.color_pair(CP_STATUS_ERR)
            safe_addstr(stdscr, row, 2, last_msg[0][:w - 4], attr)

        # Column header
        col_row = 4 if (errors or last_msg[0]) else 3
        col_name  = "Name"
        col_type  = "Type"
        col_port  = "Port"
        col_route = "Route"
        col_state = "Status"

        name_w  = max(20, w // 4)
        type_w  = 10
        port_w  = 7
        route_w = 14
        state_w = 12

        header_line = (f"  {'─'*2}  {col_name:<{name_w}}  {col_type:<{type_w}}"
                       f"  {col_port:<{port_w}}  {col_route:<{route_w}}  {col_state}")
        safe_addstr(stdscr, col_row, 0, header_line[:w - 1],
                    curses.color_pair(CP_DIM))
        stdscr.hline(col_row + 1, 0, curses.ACS_HLINE, w)

        # Project rows
        list_start = col_row + 2
        visible    = h - list_start - 1

        if not projects:
            safe_addstr(stdscr, list_start + 1, 4,
                "No projects configured. Press [n] to add one.",
                curses.color_pair(CP_DIM))
        else:
            idx = max(0, min(idx, len(projects) - 1))
            for i, p in enumerate(projects):
                row = list_start + i
                if row >= h - 1:
                    break

                is_sel = (i == idx)
                name   = p["name"]
                ptype  = p.get("type",  "?")
                port   = str(p.get("port", "—"))
                route  = p.get("route", "—") or "—"
                state  = service_state_label(name)

                sel_prefix = " ▶ " if is_sel else "   "

                if is_sel:
                    stdscr.attron(curses.color_pair(CP_SELECTED) | curses.A_BOLD)
                    stdscr.hline(row, 0, ' ', w)

                base_attr = (curses.color_pair(CP_SELECTED) | curses.A_BOLD) if is_sel else 0
                safe_addstr(stdscr, row, 0,
                    f"{sel_prefix}{name:<{name_w}}  {ptype:<{type_w}}"
                    f"  {port:<{port_w}}  {route:<{route_w}} ",
                    base_attr)

                if is_sel:
                    stdscr.attroff(curses.color_pair(CP_SELECTED) | curses.A_BOLD)

                # State coloured separately
                state_x = 3 + name_w + 2 + type_w + 2 + port_w + 2 + route_w + 1
                safe_addstr(stdscr, row, state_x, state, status_attr(state))

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
        elif ch == ord('e'):
            screen_errors(stdscr, errors)
            last_msg = ("", True)
        elif is_key(ch, KEY_QUIT):
            if confirm(stdscr, "Exit VPS Manager?", default=False):
                return


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Per-project menu
# ═══════════════════════════════════════════════════════════════════════════════

def screen_project_menu(stdscr, project: dict, config: dict):
    name  = project["name"]
    state = service_state_label(name)
    has_unit = svc_mod.unit_file_exists(name)
    has_port = bool(project.get("port"))

    items = [
        f"Start service",
        f"Stop service",
        f"Restart service",
        f"--- Status & Logs",
        f"View service status",
        f"View logs (live tail)",
        f"--- Configuration",
        f"Edit project",
        f"View nginx config",
        f"Apply nginx config",
        f"--- Danger",
        f"Remove project",
    ]

    choice = menu(stdscr, f"Project: {name}",
                  items,
                  subtitle=f"type={project.get('type','?')}  "
                           f"port={project.get('port','—')}  "
                           f"state={state}",
                  footer_hints=[("↑↓", "navigate"), ("Enter", "select"),
                                ("Esc", "back")])
    if choice is None:
        return None

    # Map visible index → action (skipping separators)
    actions = [
        "start", "stop", "restart",
        None,
        "status", "logs",
        None,
        "edit", "nginx_preview", "nginx_apply",
        None,
        "remove",
    ]
    action = actions[choice]
    if not action:
        return None

    # ── start ────────────────────────────────────────────────────────────────
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

    # ── stop ─────────────────────────────────────────────────────────────────
    elif action == "stop":
        ok, msg = svc_mod.stop_service(name)
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"stop {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    # ── restart ──────────────────────────────────────────────────────────────
    elif action == "restart":
        ok, msg = svc_mod.restart_service(name)
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"restart {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    # ── status ───────────────────────────────────────────────────────────────
    elif action == "status":
        if not has_unit:
            flash(stdscr, "No systemd unit file found for this project.", ok=False)
            return None
        st = svc_mod.get_service_status(name)
        text = st["status_text"] + "\n\n─── Recent logs ───\n" + st["logs"]
        pager(stdscr, f"Status: {name}", text)
        return None

    # ── logs ─────────────────────────────────────────────────────────────────
    elif action == "logs":
        if not has_unit:
            flash(stdscr, "No systemd unit file found.", ok=False)
            return None
        st = svc_mod.get_service_status(name)
        pager(stdscr, f"Logs: {name}", st["logs"])
        return None

    # ── edit ─────────────────────────────────────────────────────────────────
    elif action == "edit":
        return screen_edit_project(stdscr, project, config)

    # ── nginx preview ────────────────────────────────────────────────────────
    elif action == "nginx_preview":
        if not has_port:
            flash(stdscr, "Project has no port — no nginx block generated.", ok=False)
            return None
        text = nginx_mod.nginx_config_preview(project, config)
        pager(stdscr, f"Nginx config preview: {name}", text)
        return None

    # ── nginx apply ──────────────────────────────────────────────────────────
    elif action == "nginx_apply":
        if not has_port:
            flash(stdscr, "Project has no port — skip nginx.", ok=False)
            return None
        ok1, m1 = nginx_mod.write_nginx_config(project, config)
        ok2, m2 = nginx_mod.reload_nginx()
        msg = f"{m1}  |  {m2}"
        ok  = ok1 and ok2
        flash(stdscr, msg, ok=ok)
        log_mod.log(f"nginx apply {name}: {msg}", "info" if ok else "error")
        return (msg, ok)

    # ── remove ───────────────────────────────────────────────────────────────
    elif action == "remove":
        if not confirm(stdscr,
                       f"Remove project '{name}'? This will stop the service, "
                       f"delete the unit file, and remove nginx config.",
                       default=False):
            return None
        msgs = []
        ok_all = True

        ok, m = svc_mod.remove_unit_file(name)
        msgs.append(m); ok_all &= ok

        if has_port:
            ok, m = nginx_mod.remove_nginx_config(name, config)
            msgs.append(m); ok_all &= ok
            nginx_mod.reload_nginx()

        cfg_mod.remove_project(config, name)
        msg = "  ".join(msgs)
        flash(stdscr, f"Removed '{name}'", ok=True)
        log_mod.log(f"removed project {name}", "info")
        return (f"Removed {name}", True)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Add project
# ═══════════════════════════════════════════════════════════════════════════════

def screen_add_project(stdscr, config: dict):
    # Step 1: choose type
    type_choice = menu(stdscr, "Add Project — Choose Type",
                       PROJECT_TYPES,
                       subtitle="Select the project framework / runtime",
                       footer_hints=[("↑↓", "choose"), ("Enter", "select"),
                                     ("Esc", "cancel")])
    if type_choice is None:
        return None
    ptype = PROJECT_TYPES[type_choice]

    # Step 2: fill form
    has_port  = ptype not in ("aiogram", "custom") or True  # always ask; user can leave blank
    has_route = DEFAULT_ROUTES.get(ptype) is not None

    fields = [
        FormField("name",         "Project name",       required=True,
                  hint="Unique identifier, e.g. my_fastapi"),
        FormField("project_path", "Project path",       default="/root/",
                  required=True, hint="Absolute path to the project directory"),
        FormField("port",         "Port",
                  default=str(DEFAULT_ROUTES.get(ptype) or ""),
                  hint="Leave blank for background services (bots, workers)"),
        FormField("route",        "Nginx route",
                  default=DEFAULT_ROUTES.get(ptype, "") or "",
                  hint="e.g. / or /api/ — leave blank if no web exposure"),
        FormField("venv_path",    "Python interpreter / venv",
                  default="python3",
                  hint="e.g. /root/myproject/venv/bin/python3"),
        FormField("runcommand",   "Run command",        required=True,
                  hint="Full command to start the service"),
    ]

    # Pre-fill runcommand from template
    for f in fields:
        if f.key == "runcommand":
            f.value = build_run_command(ptype, "/root/", "", "python3")

    data = form(stdscr, f"Add Project ({ptype})", fields)
    if data is None:
        return None

    # Convert port
    port_str = data.get("port", "").strip()
    port_val = None
    if port_str:
        try:
            port_val = int(port_str)
        except ValueError:
            flash(stdscr, f"Invalid port '{port_str}'", ok=False)
            return None
        if cfg_mod.is_port_taken(config, port_val):
            flash(stdscr, f"Port {port_val} is already taken.", ok=False)
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

    errors = cfg_mod.validate_project(project)
    if errors:
        pager(stdscr, "Validation Errors", "\n".join(errors))
        return None

    try:
        cfg_mod.add_project(config, project)
    except ValueError as e:
        flash(stdscr, str(e), ok=False)
        return (str(e), False)

    # Optionally write unit file now
    if confirm(stdscr, f"Write systemd unit file for '{project['name']}' now?", default=True):
        ok, msg = svc_mod.write_unit_file(project)
        flash(stdscr, msg, ok=ok)

    # Optionally write nginx config
    if port_val and confirm(stdscr, f"Generate and apply nginx config for '{project['name']}'?", default=True):
        cfg2 = cfg_mod.load_config()  # reload
        ok1, m1 = nginx_mod.write_nginx_config(project, cfg2)
        ok2, m2 = nginx_mod.reload_nginx()
        flash(stdscr, f"{m1} | {m2}", ok=ok1 and ok2)

    msg = f"Project '{project['name']}' added."
    log_mod.log(msg, "info")
    return (msg, True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Edit project
# ═══════════════════════════════════════════════════════════════════════════════

def screen_edit_project(stdscr, project: dict, config: dict):
    name = project["name"]
    fields = [
        FormField("project_path", "Project path",    default=project.get("project_path", "")),
        FormField("port",         "Port",             default=str(project.get("port", ""))),
        FormField("route",        "Nginx route",      default=project.get("route", "")),
        FormField("venv_path",    "Python / venv",    default=project.get("venv_path", "")),
        FormField("runcommand",   "Run command",      default=project.get("runcommand", ""),
                  required=True),
    ]

    data = form(stdscr, f"Edit Project: {name}", fields)
    if data is None:
        return None

    port_str = data.get("port", "").strip()
    port_val = project.get("port")
    if port_str:
        try:
            port_val = int(port_str)
        except ValueError:
            flash(stdscr, "Invalid port.", ok=False)
            return None
        if cfg_mod.is_port_taken(config, port_val, exclude_name=name):
            flash(stdscr, f"Port {port_val} is taken.", ok=False)
            return None

    updates = {
        "project_path": data["project_path"],
        "runcommand":   data["runcommand"],
        "venv_path":    data["venv_path"] or None,
        "port":         port_val,
        "route":        data.get("route") or None,
    }
    updates = {k: v for k, v in updates.items() if v is not None or k in ("route",)}

    cfg_mod.update_project(config, name, updates)

    # Re-write unit file
    updated = cfg_mod.get_project(cfg_mod.load_config(), name)
    ok, msg = svc_mod.write_unit_file(updated)
    flash(stdscr, f"Saved. {msg}", ok=ok)
    log_mod.log(f"edited project {name}", "info")
    return (f"Updated {name}", ok)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Nginx menu
# ═══════════════════════════════════════════════════════════════════════════════

def screen_nginx_menu(stdscr, config: dict):
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
        msgs = []
        ok_all = True
        for p in config.get("projects", []):
            if not p.get("port"):
                continue
            ok, m = nginx_mod.write_nginx_config(p, config)
            msgs.append(f"{p['name']}: {'OK' if ok else 'FAIL'}")
            ok_all &= ok
        ok2, m2 = nginx_mod.reload_nginx()
        msgs.append(f"Reload: {'OK' if ok2 else 'FAIL'} {m2}")
        pager(stdscr, "Nginx Apply Results", "\n".join(msgs))
        log_mod.log("nginx apply all", "info" if ok_all else "error")
        return ("\n".join(msgs), ok_all and ok2)

    elif choice == 1:
        ok, msg = nginx_mod.reload_nginx()
        flash(stdscr, msg, ok=ok)
        return (msg, ok)

    elif choice == 2:
        combined = nginx_mod.generate_combined_nginx_config(config)
        pager(stdscr, "Combined Nginx Config", combined)
        return None

    elif choice == 3:
        return screen_edit_nginx_settings(stdscr, config)

    return None


def screen_edit_nginx_settings(stdscr, config: dict):
    ng = config.get("nginx", {})
    fields = [
        FormField("server_name",    "Server name",      default=ng.get("server_name", "_"),
                  hint="Nginx server_name directive, e.g. example.com or _"),
        FormField("error_page_dir", "Error page dir",   default=ng.get("error_page_dir", "/var/www/vps-manager-errors"),
                  hint="Where to write project-specific error HTML pages"),
        FormField("config_dir",     "sites-available",  default=ng.get("config_dir", "/etc/nginx/sites-available")),
        FormField("enabled_dir",    "sites-enabled",    default=ng.get("enabled_dir", "/etc/nginx/sites-enabled")),
    ]

    data = form(stdscr, "Edit Nginx Settings", fields)
    if data is None:
        return None

    config["nginx"].update(data)
    cfg_mod.save_config(config)
    flash(stdscr, "Nginx settings saved.", ok=True)
    return ("Nginx settings updated", True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCREEN: Error viewer
# ═══════════════════════════════════════════════════════════════════════════════

def screen_errors(stdscr, errors: List[dict]):
    if not errors:
        flash(stdscr, "No service errors detected.", ok=True)
        return

    items = [f"{e['name']}  [{e['state']}]  {e['last_log'][:60]}" for e in errors]
    while True:
        choice = menu(stdscr, "Service Errors",
                      items,
                      subtitle="Services in failed/error state — Enter to view full details",
                      footer_hints=[("↑↓", "navigate"), ("Enter", "details"), ("Esc", "back")])
        if choice is None:
            return
        e = errors[choice]
        text = (
            f"Service : {e['name']}\n"
            f"State   : {e['state']}\n\n"
            f"─── systemctl status ───\n{e['status_text']}\n\n"
            f"─── journalctl logs ───\n{e['logs']}"
        )
        pager(stdscr, f"Error Detail: {e['name']}", text)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(stdscr):
    curses.curs_set(0)
    init_colors()
    # Brief splash / startup
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    lines = [
        "VPS Manager",
        "──────────────────────────────",
        "Loading configuration...",
    ]
    for i, line in enumerate(lines):
        safe_addstr(stdscr, h // 2 - len(lines) // 2 + i,
                    w // 2 - len(line) // 2, line)
    stdscr.refresh()
    curses.napms(400)

    # Validate config readable
    try:
        config = cfg_mod.load_config()
    except RuntimeError as e:
        pager(stdscr, "Config Error", str(e))
        return

    screen_dashboard(stdscr)


def check_sudo():
    if os.geteuid() != 0:
        print("Please run this script with sudo!")
        print("Example: sudo python3 run.py")
        sys.exit(1)


def run():
    check_sudo()
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