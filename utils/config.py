"""
vps-manager/utils/config.py
Handles reading, writing, and validating the JSON configuration file.
"""

import json
import os
import copy
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "projects": [],
    "nginx": {
        "server_name": "_",
        "error_page_dir": "/var/www/vps-manager-errors",
        "config_dir": "/etc/nginx/sites-available",
        "enabled_dir": "/etc/nginx/sites-enabled"
    }
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
        # Ensure nginx section exists
        if "nginx" not in data:
            data["nginx"] = DEFAULT_CONFIG["nginx"]
        if "projects" not in data:
            data["projects"] = []
        return data
    except (json.JSONDecodeError, IOError) as e:
        raise RuntimeError(f"Failed to load config.json: {e}")


def save_config(config: dict) -> None:
    """Save configuration to config.json."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        raise RuntimeError(f"Failed to save config.json: {e}")


def get_project(config: dict, name: str) -> Optional[dict]:
    """Get a project by name."""
    for p in config.get("projects", []):
        if p["name"] == name:
            return p
    return None


def add_project(config: dict, project: dict) -> None:
    """Add a new project to config."""
    if get_project(config, project["name"]):
        raise ValueError(f"Project '{project['name']}' already exists.")
    config["projects"].append(project)
    save_config(config)


def remove_project(config: dict, name: str) -> None:
    """Remove a project from config by name."""
    original = len(config["projects"])
    config["projects"] = [p for p in config["projects"] if p["name"] != name]
    if len(config["projects"]) == original:
        raise ValueError(f"Project '{name}' not found.")
    save_config(config)


def update_project(config: dict, name: str, updates: dict) -> None:
    """Update fields of an existing project."""
    for p in config["projects"]:
        if p["name"] == name:
            p.update(updates)
            save_config(config)
            return
    raise ValueError(f"Project '{name}' not found.")


def validate_project(project: dict) -> list:
    """
    Validate project fields. Returns list of error strings.
    Empty list means valid.
    """
    errors = []
    ptype = project.get("type", "custom")
    required = REQUIRED_FIELDS.get(ptype, REQUIRED_FIELDS["custom"])

    for field in required:
        if not project.get(field):
            errors.append(f"Missing required field: '{field}' for type '{ptype}'")

    # Port validation
    if "port" in project:
        port = project["port"]
        if not isinstance(port, int) or not (1 <= port <= 65535):
            errors.append(f"Invalid port: {port}. Must be 1–65535.")

    # Name validation
    name = project.get("name", "")
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        errors.append("Project name must be alphanumeric (underscores/hyphens allowed).")

    return errors


def is_port_taken(config: dict, port: int, exclude_name: str = None) -> bool:
    """Check if a port is already assigned to another project."""
    for p in config["projects"]:
        if p.get("port") == port and p.get("name") != exclude_name:
            return True
    return False


def get_nginx_config(config: dict) -> dict:
    """Return the nginx section of config."""
    return config.get("nginx", DEFAULT_CONFIG["nginx"])