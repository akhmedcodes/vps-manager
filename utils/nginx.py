"""
vps-manager/utils/nginx.py
Generates and manages Nginx server block configurations per project.
"""

import os
import subprocess
import textwrap
from typing import Tuple


def _error_page_html(project_name: str, error_code: int, error_title: str) -> str:
    """Generate a minimal, clean HTML error page for a project."""
    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>{error_code} — {error_title}</title>
          <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              background: #0f0f0f;
              color: #e0e0e0;
              display: flex;
              align-items: center;
              justify-content: center;
              min-height: 100vh;
              padding: 2rem;
            }}
            .container {{
              max-width: 540px;
              text-align: center;
            }}
            .code {{
              font-size: 6rem;
              font-weight: 700;
              color: #444;
              line-height: 1;
            }}
            .title {{
              font-size: 1.4rem;
              margin: 1rem 0 0.5rem;
              color: #aaa;
            }}
            .project {{
              font-size: 0.85rem;
              color: #555;
              margin-top: 2rem;
              font-family: monospace;
            }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="code">{error_code}</div>
            <div class="title">{error_title}</div>
            <div class="project">service: {project_name}</div>
          </div>
        </body>
        </html>
    """)


def write_error_pages(project: dict, error_page_dir: str) -> Tuple[bool, str]:
    """
    Write custom error pages (502, 503, 504) for a project.
    Returns (success, message).
    """
    name = project["name"]
    pages = {
        502: "Bad Gateway — Service Unavailable",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }
    try:
        project_error_dir = os.path.join(error_page_dir, name)
        os.makedirs(project_error_dir, exist_ok=True)
        for code, title in pages.items():
            html = _error_page_html(name, code, title)
            path = os.path.join(project_error_dir, f"{code}.html")
            with open(path, "w") as f:
                f.write(html)
        return True, f"Error pages written to {project_error_dir}"
    except PermissionError:
        return False, f"Permission denied writing error pages to {error_page_dir}."
    except Exception as e:
        return False, str(e)


def generate_server_block(project: dict, nginx_cfg: dict) -> str:
    """
    Generate an Nginx server block for a single project.
    Only web projects (with port + route) get location blocks.
    """
    name         = project["name"]
    port         = project.get("port")
    route        = project.get("route", "/")
    server_name  = nginx_cfg.get("server_name", "_")
    error_dir    = nginx_cfg.get("error_page_dir", "/var/www/vps-manager-errors")

    if not port:
        # No port → not a web service, skip nginx block
        return f"# Project '{name}' has no port; no nginx block generated.\n"

    # Normalise route
    if not route.endswith("/"):
        route = route + "/"

    error_pages_block = textwrap.dedent(f"""\
        error_page 502 /502.html;
            error_page 503 /503.html;
            error_page 504 /504.html;
            location ~ ^/(502|503|504)\\.html$ {{
                root {error_dir}/{name};
                internal;
            }}""")

    block = textwrap.dedent(f"""\
        # --- {name} ({project.get('type', 'custom')}) ---
        server {{
            listen 80;
            server_name {server_name};

            {error_pages_block}

            location {route} {{
                proxy_pass http://127.0.0.1:{port}/;
                proxy_http_version 1.1;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
                proxy_set_header Upgrade $http_upgrade;
                proxy_set_header Connection "upgrade";
                proxy_read_timeout 120s;
                proxy_connect_timeout 10s;
            }}
        }}
    """)
    return block


def generate_combined_nginx_config(config: dict) -> str:
    """
    Generate a single nginx config file containing blocks for all web projects.
    """
    nginx_cfg = config.get("nginx", {})
    projects  = config.get("projects", [])
    web_projects = [p for p in projects if p.get("port")]

    if not web_projects:
        return "# No web projects configured.\n"

    parts = ["# Generated by vps-manager — do not edit manually\n"]
    for p in web_projects:
        parts.append(generate_server_block(p, nginx_cfg))
    return "\n".join(parts)


def write_nginx_config(project: dict, config: dict) -> Tuple[bool, str]:
    """
    Write a per-project nginx config file to sites-available and symlink it.
    """
    nginx_cfg    = config.get("nginx", {})
    config_dir   = nginx_cfg.get("config_dir", "/etc/nginx/sites-available")
    enabled_dir  = nginx_cfg.get("enabled_dir",  "/etc/nginx/sites-enabled")
    error_dir    = nginx_cfg.get("error_page_dir", "/var/www/vps-manager-errors")
    name         = project["name"]

    if not project.get("port"):
        return True, f"Skipped nginx config for '{name}' (no port)."

    # Write error pages first
    write_error_pages(project, error_dir)

    config_file  = os.path.join(config_dir, f"vps-{name}")
    enabled_link = os.path.join(enabled_dir, f"vps-{name}")
    content      = generate_server_block(project, nginx_cfg)

    try:
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(enabled_dir, exist_ok=True)
        with open(config_file, "w") as f:
            f.write(content)

        # Symlink to sites-enabled
        if os.path.islink(enabled_link):
            os.unlink(enabled_link)
        os.symlink(config_file, enabled_link)

        return True, f"Nginx config written: {config_file}"
    except PermissionError:
        return False, f"Permission denied. Run as root."
    except Exception as e:
        return False, str(e)


def remove_nginx_config(project_name: str, config: dict) -> Tuple[bool, str]:
    """Remove nginx config and symlink for a project."""
    nginx_cfg   = config.get("nginx", {})
    config_dir  = nginx_cfg.get("config_dir", "/etc/nginx/sites-available")
    enabled_dir = nginx_cfg.get("enabled_dir", "/etc/nginx/sites-enabled")

    config_file  = os.path.join(config_dir, f"vps-{project_name}")
    enabled_link = os.path.join(enabled_dir, f"vps-{project_name}")

    try:
        if os.path.islink(enabled_link):
            os.unlink(enabled_link)
        if os.path.exists(config_file):
            os.remove(config_file)
        return True, f"Nginx config removed for '{project_name}'."
    except PermissionError:
        return False, "Permission denied. Run as root."
    except Exception as e:
        return False, str(e)


def reload_nginx() -> Tuple[bool, str]:
    """Test nginx config and reload if valid."""
    test = subprocess.run(
        ["nginx", "-t"], capture_output=True, text=True
    )
    if test.returncode != 0:
        return False, f"Nginx config test failed:\n{test.stderr.strip()}"

    result = subprocess.run(
        ["systemctl", "reload", "nginx"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return True, "Nginx reloaded successfully."
    return False, result.stderr.strip()


def nginx_config_preview(project: dict, config: dict) -> str:
    """Return a preview of the nginx block that would be generated."""
    return generate_server_block(project, config.get("nginx", {}))