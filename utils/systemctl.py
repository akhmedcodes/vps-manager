"""
vps-manager/utils/systemctl.py
──────────────────────────────
Manage systemd services for vps-manager projects.
All public functions return (ok: bool, message: str) tuples.
"""

import os
import subprocess
import re
from typing import Tuple

UNIT_PREFIX = "vps-"


def service_name(project_name: str) -> str:
    """Return the full systemd service name for a project."""
    return f"{UNIT_PREFIX}{project_name}.service"


def unit_path(project_name: str) -> str:
    return f"/etc/systemd/system/{service_name(project_name)}"


def unit_file_exists(project_name: str) -> bool:
    return os.path.exists(unit_path(project_name))


# ─── Unit file generation ─────────────────────────────────────────────────────

def _build_env_path(project: dict) -> str:
    """Build PATH for the service Environment= line."""
    venv = project.get("venv_path", "")
    if not venv:
        return "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    # venv_path may be the python binary or the venv root
    if os.path.isfile(venv):
        venv_bin = os.path.dirname(venv)
    else:
        venv_bin = os.path.join(venv.rstrip("/"), "bin")

    return f"{venv_bin}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def write_unit_file(project: dict) -> Tuple[bool, str]:
    """
    Write (or overwrite) the systemd unit file for a project.
    Also runs systemctl daemon-reload.
    """
    name       = project["name"]
    runcommand = project.get("runcommand", "")
    work_dir   = project.get("project_path", "/root")
    env_path   = _build_env_path(project)
    svc        = service_name(name)

    unit = f"""\
[Unit]
Description=VPS Manager: {name} ({project.get('type', 'custom')})
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={work_dir}
ExecStart={runcommand}
Environment="PATH={env_path}"
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier={name}

[Install]
WantedBy=multi-user.target
"""
    path = unit_path(name)
    try:
        with open(path, "w") as f:
            f.write(unit)
    except PermissionError:
        return False, f"Permission denied writing {path}. Run as root."
    except OSError as e:
        return False, f"Failed to write unit file: {e}"

    result = subprocess.run(
        ["systemctl", "daemon-reload"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, f"daemon-reload failed: {result.stderr.strip()}"

    return True, f"Unit file written: {path}"


def remove_unit_file(project_name: str) -> Tuple[bool, str]:
    path = unit_path(project_name)
    if not os.path.exists(path):
        return True, "Unit file not found (already gone)."
    try:
        # Disable first so symlinks are cleaned up
        subprocess.run(
            ["systemctl", "disable", service_name(project_name)],
            capture_output=True
        )
        os.remove(path)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        return True, f"Removed {path}"
    except OSError as e:
        return False, f"Failed to remove unit file: {e}"


# ─── Service control ──────────────────────────────────────────────────────────

def _run_ctl(*args) -> Tuple[bool, str]:
    result = subprocess.run(
        ["systemctl"] + list(args),
        capture_output=True, text=True
    )
    out = (result.stdout + result.stderr).strip()
    return result.returncode == 0, out or " ".join(args) + " done"


def start_service(project_name: str) -> Tuple[bool, str]:
    ok, msg = _run_ctl("enable", "--now", service_name(project_name))
    if not ok:
        return ok, msg
    return True, f"Started {service_name(project_name)}"


def stop_service(project_name: str) -> Tuple[bool, str]:
    ok, msg = _run_ctl("stop", service_name(project_name))
    return ok, msg or f"Stopped {service_name(project_name)}"


def restart_service(project_name: str) -> Tuple[bool, str]:
    ok, msg = _run_ctl("restart", service_name(project_name))
    return ok, msg or f"Restarted {service_name(project_name)}"


# ─── Status & logs ────────────────────────────────────────────────────────────

def get_service_status(project_name: str) -> dict:
    """
    Return dict:
      state        — active / inactive / failed / activating / unknown
      status_text  — full systemctl status output
      logs         — last 60 lines from journalctl
    """
    svc = service_name(project_name)

    # Active state
    r = subprocess.run(
        ["systemctl", "is-active", svc],
        capture_output=True, text=True
    )
    state = r.stdout.strip() or "unknown"

    # Full status
    r2 = subprocess.run(
        ["systemctl", "status", svc, "--no-pager", "-l"],
        capture_output=True, text=True
    )
    status_text = r2.stdout or r2.stderr or "(no output)"

    # Journal logs
    r3 = subprocess.run(
        ["journalctl", "-u", svc, "-n", "60", "--no-pager", "--output=short"],
        capture_output=True, text=True
    )
    logs = r3.stdout or "(no journal entries)"

    return {
        "state":       state,
        "status_text": status_text,
        "logs":        logs,
    }