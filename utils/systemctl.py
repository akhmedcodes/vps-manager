"""
vps-manager/utils/systemctl.py
Manages systemd service unit files and service lifecycle commands.
"""

import os
import subprocess
import textwrap
from typing import Tuple


SYSTEMD_DIR = "/etc/systemd/system"


def service_name(project_name: str) -> str:
    return f"vps-{project_name}.service"


def service_path(project_name: str) -> str:
    return os.path.join(SYSTEMD_DIR, service_name(project_name))


def generate_unit_file(project: dict) -> str:
    """
    Generate a systemd unit file content for a given project dict.
    """
    name        = project["name"]
    runcommand  = project["runcommand"]
    project_path = project.get("project_path", "/root")
    description = f"VPS Manager: {name} ({project.get('type', 'custom')})"
    user        = project.get("user", "root")
    env_extras  = ""

    # If venv_path provided, inject PATH
    if project.get("venv_path"):
        venv_bin = os.path.dirname(project["venv_path"])
        env_extras = f'\nEnvironment="PATH={venv_bin}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"'

    unit = textwrap.dedent(f"""\
        [Unit]
        Description={description}
        After=network.target

        [Service]
        Type=simple
        User={user}
        WorkingDirectory={project_path}
        ExecStart={runcommand}{env_extras}
        Restart=on-failure
        RestartSec=5
        StandardOutput=journal
        StandardError=journal
        SyslogIdentifier={name}

        [Install]
        WantedBy=multi-user.target
    """)
    return unit


def write_unit_file(project: dict) -> Tuple[bool, str]:
    """Write the systemd unit file to disk. Returns (success, message)."""
    path = service_path(project["name"])
    content = generate_unit_file(project)
    try:
        with open(path, "w") as f:
            f.write(content)
        _run(["systemctl", "daemon-reload"])
        return True, f"Unit file written: {path}"
    except PermissionError:
        return False, f"Permission denied writing {path}. Run as root."
    except Exception as e:
        return False, str(e)


def remove_unit_file(project_name: str) -> Tuple[bool, str]:
    """Stop the service, disable it, and remove the unit file."""
    svc = service_name(project_name)
    path = service_path(project_name)
    try:
        _run(["systemctl", "stop", svc])
        _run(["systemctl", "disable", svc])
        if os.path.exists(path):
            os.remove(path)
        _run(["systemctl", "daemon-reload"])
        return True, f"Service {svc} removed."
    except PermissionError:
        return False, "Permission denied. Run as root."
    except Exception as e:
        return False, str(e)


def start_service(project_name: str) -> Tuple[bool, str]:
    svc = service_name(project_name)
    ok, out = _run(["systemctl", "start", svc])
    if ok:
        _run(["systemctl", "enable", svc])
        return True, f"Started {svc}"
    return False, out


def stop_service(project_name: str) -> Tuple[bool, str]:
    svc = service_name(project_name)
    ok, out = _run(["systemctl", "stop", svc])
    if ok:
        return True, f"Stopped {svc}"
    return False, out


def restart_service(project_name: str) -> Tuple[bool, str]:
    svc = service_name(project_name)
    ok, out = _run(["systemctl", "restart", svc])
    if ok:
        return True, f"Restarted {svc}"
    return False, out


def get_service_status(project_name: str) -> dict:
    """
    Returns a dict with keys: active (bool), status_line (str), logs (str).
    """
    svc = service_name(project_name)

    # is-active
    result = subprocess.run(
        ["systemctl", "is-active", svc],
        capture_output=True, text=True
    )
    active_state = result.stdout.strip()
    is_active = (active_state == "active")

    # status summary
    status_result = subprocess.run(
        ["systemctl", "status", svc, "--no-pager", "-n", "0"],
        capture_output=True, text=True
    )
    status_lines = status_result.stdout.strip()

    # last 30 journal lines
    log_result = subprocess.run(
        ["journalctl", "-u", svc, "-n", "30", "--no-pager", "--output=short-iso"],
        capture_output=True, text=True
    )
    logs = log_result.stdout.strip() or "(no logs)"

    return {
        "active": is_active,
        "state": active_state,
        "status_text": status_lines,
        "logs": logs,
    }


def unit_file_exists(project_name: str) -> bool:
    return os.path.exists(service_path(project_name))


def enable_service(project_name: str) -> Tuple[bool, str]:
    svc = service_name(project_name)
    ok, out = _run(["systemctl", "enable", svc])
    return ok, out


def _run(cmd: list) -> Tuple[bool, str]:
    """Run a subprocess command. Returns (success, output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stderr.strip() or result.stdout.strip())
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"
    except Exception as e:
        return False, str(e)