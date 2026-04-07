#!/usr/bin/env python3
"""
vps-manager/scripts/deploy.py
Full deploy helper: writes systemd unit + nginx config + reloads nginx.
Usage: python3 deploy.py <project_name>
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import load_config, get_project
from utils.systemctl import write_unit_file, start_service
from utils.nginx import write_nginx_config, reload_nginx


def main():
    if len(sys.argv) < 2:
        print("Usage: deploy.py <project_name>")
        sys.exit(1)

    name    = sys.argv[1]
    config  = load_config()
    project = get_project(config, name)

    if not project:
        print(f"[ERROR] Project '{name}' not found in config.json")
        sys.exit(1)

    steps = [
        ("Writing systemd unit",  lambda: write_unit_file(project)),
        ("Writing nginx config",  lambda: write_nginx_config(project, config)),
        ("Reloading nginx",       reload_nginx),
        ("Starting service",      lambda: start_service(name)),
    ]

    all_ok = True
    for label, fn in steps:
        ok, msg = fn()
        tag = "OK  " if ok else "FAIL"
        print(f"  [{tag}] {label}: {msg}")
        if not ok:
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()