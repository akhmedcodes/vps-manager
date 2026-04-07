"""
vps-manager/utils/ssl.py
─────────────────────────
Let's Encrypt certificate management via certbot.
Requires: sudo apt install certbot python3-certbot-nginx -y
"""

import subprocess
import os
import re
from typing import Tuple, List, Optional


# ─── Certbot availability ──────────────────────────────────────────────────────

def certbot_available() -> bool:
    result = subprocess.run(
        ["which", "certbot"], capture_output=True, text=True
    )
    return result.returncode == 0


def certbot_version() -> str:
    result = subprocess.run(
        ["certbot", "--version"], capture_output=True, text=True
    )
    return (result.stdout + result.stderr).strip()


# ─── Certificate operations ───────────────────────────────────────────────────

def obtain_certificate(
    domains: List[str],
    email: str = "",
    dry_run: bool = False,
    webroot: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Obtain or renew a certificate using certbot --nginx (default) or
    --webroot if webroot path is provided.

    domains   : list of domain strings, e.g. ["example.com", "www.example.com"]
    email     : contact email for Let's Encrypt
    dry_run   : run with --dry-run flag (no actual cert issued)
    webroot   : if set, uses webroot plugin instead of --nginx
    """
    if not certbot_available():
        return False, (
            "certbot not found. Install with:\n"
            "  sudo apt install certbot python3-certbot-nginx -y"
        )
    if not domains:
        return False, "No domains specified."

    cmd = ["certbot"]

    if webroot:
        cmd += ["certonly", "--webroot", "-w", webroot]
    else:
        cmd += ["--nginx"]

    for d in domains:
        cmd += ["-d", d.strip()]

    if email:
        cmd += ["--email", email, "--agree-tos", "--no-eff-email"]
    else:
        cmd += ["--register-unsafely-without-email", "--agree-tos"]

    if dry_run:
        cmd.append("--dry-run")

    cmd.append("--non-interactive")

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return True, output.strip()
    return False, output.strip()


def revoke_certificate(domain: str) -> Tuple[bool, str]:
    """Revoke the certificate for a domain."""
    cert_path = f"/etc/letsencrypt/live/{domain}/cert.pem"
    if not os.path.exists(cert_path):
        return False, f"Certificate not found at {cert_path}"

    result = subprocess.run(
        ["certbot", "revoke", "--cert-path", cert_path, "--non-interactive",
         "--delete-after-revoke"],
        capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()


def renew_certificates(dry_run: bool = False) -> Tuple[bool, str]:
    """Run certbot renew for all certificates."""
    cmd = ["certbot", "renew", "--non-interactive"]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()


def list_certificates() -> List[dict]:
    """
    Return list of installed certificates.
    Each entry: {name, domains, expiry, path}
    """
    result = subprocess.run(
        ["certbot", "certificates"],
        capture_output=True, text=True
    )
    certs = []
    current: dict = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Certificate Name:"):
            if current:
                certs.append(current)
            current = {"name": line.split(":", 1)[1].strip(),
                       "domains": [], "expiry": "", "path": ""}
        elif line.startswith("Domains:") and current is not None:
            current["domains"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("Expiry Date:") and current is not None:
            current["expiry"] = line.split(":", 1)[1].strip()
        elif line.startswith("Certificate Path:") and current is not None:
            current["path"] = line.split(":", 1)[1].strip()
    if current:
        certs.append(current)
    return certs


def certificate_expiry_days(domain: str) -> Optional[int]:
    """Return days until the cert for domain expires, or None."""
    cert_path = f"/etc/letsencrypt/live/{domain}/cert.pem"
    if not os.path.exists(cert_path):
        return None
    result = subprocess.run(
        ["openssl", "x509", "-enddate", "-noout", "-in", cert_path],
        capture_output=True, text=True
    )
    match = re.search(r"notAfter=(.+)", result.stdout)
    if not match:
        return None
    from datetime import datetime
    try:
        expiry = datetime.strptime(match.group(1).strip(), "%b %d %H:%M:%S %Y %Z")
        delta  = expiry - datetime.utcnow()
        return delta.days
    except Exception:
        return None


# ─── Nginx SSL block helpers ──────────────────────────────────────────────────

def has_ssl_certificate(domain: str) -> bool:
    """Check if a certificate exists for this domain."""
    return os.path.exists(f"/etc/letsencrypt/live/{domain}/fullchain.pem")


def ssl_status_text(domain: str) -> str:
    """One-line status string for a domain's SSL cert."""
    if not has_ssl_certificate(domain):
        return "no certificate"
    days = certificate_expiry_days(domain)
    if days is None:
        return "cert present (expiry unknown)"
    if days < 0:
        return f"EXPIRED ({abs(days)}d ago)"
    if days < 14:
        return f"expires in {days}d (renew soon!)"
    return f"valid ({days}d remaining)"