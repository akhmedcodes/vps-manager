#!/usr/bin/env python3
"""
vps-manager/scripts/start_service.py
CLI helper: start a project service by name.
Usage: python3 start_service.py <project_name>
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import load_config, get_project
from utils.systemctl import start_service, write_unit_file, unit_file_exists


def main():
    if len(sys.argv) < 2:
        print("Usage: start_service.py <project_name>")
        sys.exit(1)

    name   = sys.argv[1]
    config = load_config()
    project = get_project(config, name)

    if not project:
        print(f"[ERROR] Project '{name}' not found in config.json")
        sys.exit(1)

    # Ensure unit file exists
    if not unit_file_exists(name):
        print(f"[INFO] Writing unit file for '{name}'...")
        ok, msg = write_unit_file(project)
        print(f"  {'OK' if ok else 'FAIL'}: {msg}")
        if not ok:
            sys.exit(1)

    ok, msg = start_service(name)
    print(f"  {'OK' if ok else 'FAIL'}: {msg}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()