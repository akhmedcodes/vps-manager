"""
vps-manager/utils/config.py
Handles reading, writing, and validating the JSON configuration file.
"""

import json
import os
import copy
from typing import Optional

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "projects": [],
    "nginx": {
        "server_name":   "_",
        "error_page_dir": "/var/www/vps-manager-errors",
        "config_dir":    "/etc/nginx/sites-available",
        "enabled_dir":   "/etc/nginx/sites-enabled",
    },
    "bot": {
        "token":     "",
        "admin_ids": [],
        "enabled":   False,
    },
    "ssl": {
        "email":   "",
        "domains": [],
    },
}

REQUIRED_FIELDS = {
    "django":   ["name", "type", "port", "route", "runcommand", "project_path"],
    "fastapi":  ["name", "type", "port", "route", "runcommand", "project_path"],
    "flask":    ["name", "type", "port", "route", "runcommand", "project_path"],
    "nodejs":   ["name", "type", "port", "route", "runcommand", "project_path"],
    "react":    ["name", "type", "port", "route", "runcommand", "project_path"],
    "aiogram":  ["name", "type", "runcommand", "project_path"],
    "custom":   ["name", "type", "runcommand", "project_path"],
}


def load_config() -> dict:
    """Load configuration from config.json. Creates default if missing."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        # Backfill missing top-level sections
        for key, val in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = copy.deepcopy(val)
        return data
    except (json.JSONDecodeError, IOError) as e:
        raise RuntimeError(f"Failed to load config.json: {e}")


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        raise RuntimeError(f"Failed to save config.json: {e}")


def get_project(config: dict, name: str) -> Optional[dict]:
    for p in config.get("projects", []):
        if p["name"] == name:
            return p
    return None


def add_project(config: dict, project: dict) -> None:
    if get_project(config, project["name"]):
        raise ValueError(f"Project '{project['name']}' already exists.")
    config["projects"].append(project)
    save_config(config)


def remove_project(config: dict, name: str) -> None:
    original = len(config["projects"])
    config["projects"] = [p for p in config["projects"] if p["name"] != name]
    if len(config["projects"]) == original:
        raise ValueError(f"Project '{name}' not found.")
    save_config(config)


def update_project(config: dict, name: str, updates: dict) -> None:
    for p in config["projects"]:
        if p["name"] == name:
            p.update(updates)
            save_config(config)
            return
    raise ValueError(f"Project '{name}' not found.")


def validate_project(project: dict) -> list:
    errors  = []
    ptype   = project.get("type", "custom")
    required = REQUIRED_FIELDS.get(ptype, REQUIRED_FIELDS["custom"])
    for field in required:
        if not project.get(field):
            errors.append(f"Missing required field: '{field}' for type '{ptype}'")
    if "port" in project:
        port = project["port"]
        if not isinstance(port, int) or not (1 <= port <= 65535):
            errors.append(f"Invalid port: {port}. Must be 1–65535.")
    name = project.get("name", "")
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        errors.append("Project name must be alphanumeric (underscores/hyphens allowed).")
    return errors


def is_port_taken(config: dict, port: int, exclude_name: str = None) -> bool:
    for p in config["projects"]:
        if p.get("port") == port and p.get("name") != exclude_name:
            return True
    return False


def get_nginx_config(config: dict) -> dict:
    return config.get("nginx", copy.deepcopy(DEFAULT_CONFIG["nginx"]))


def get_bot_config(config: dict) -> dict:
    return config.get("bot", copy.deepcopy(DEFAULT_CONFIG["bot"]))


def set_bot_config(config: dict, token: str, admin_ids: list, enabled: bool = True) -> None:
    config["bot"] = {
        "token":     token,
        "admin_ids": [int(x) for x in admin_ids if str(x).strip().isdigit()],
        "enabled":   enabled,
    }
    save_config(config)


def get_ssl_config(config: dict) -> dict:
    return config.get("ssl", copy.deepcopy(DEFAULT_CONFIG["ssl"]))