"""
vps-manager/utils/monitor.py
────────────────────────────
System and per-service CPU/Memory monitoring.
Uses /proc filesystem — no psutil dependency.
Generates PNG charts via matplotlib for Telegram bot delivery.
"""

import os
import re
import time
import subprocess
from typing import Optional


# ─── System-wide metrics ──────────────────────────────────────────────────────

def cpu_percent() -> float:
    """Read CPU usage % averaged over 200ms from /proc/stat."""
    def _read():
        with open("/proc/stat") as f:
            line = f.readline()
        vals = list(map(int, line.split()[1:8]))
        total = sum(vals)
        idle  = vals[3]
        return total, idle

    t1, i1 = _read()
    time.sleep(0.2)
    t2, i2 = _read()
    delta_total = t2 - t1
    delta_idle  = i2 - i1
    if delta_total == 0:
        return 0.0
    return round(100.0 * (1 - delta_idle / delta_total), 1)


def memory_info() -> dict:
    """
    Returns dict with keys:
      total_mb, used_mb, free_mb, available_mb, percent
    """
    data = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                data[parts[0].rstrip(":")] = int(parts[1])  # kB

    total     = data.get("MemTotal", 0)
    available = data.get("MemAvailable", data.get("MemFree", 0))
    used      = total - available

    return {
        "total_mb":     round(total     / 1024, 1),
        "used_mb":      round(used      / 1024, 1),
        "free_mb":      round(available / 1024, 1),
        "available_mb": round(available / 1024, 1),
        "percent":      round(100.0 * used / total, 1) if total else 0.0,
    }


def disk_info(path: str = "/") -> dict:
    """
    Returns dict: total_gb, used_gb, free_gb, percent
    """
    stat = os.statvfs(path)
    total = stat.f_frsize * stat.f_blocks
    free  = stat.f_frsize * stat.f_bfree
    used  = total - free
    return {
        "total_gb": round(total / 1024**3, 2),
        "used_gb":  round(used  / 1024**3, 2),
        "free_gb":  round(free  / 1024**3, 2),
        "percent":  round(100.0 * used / total, 1) if total else 0.0,
    }


def load_avg() -> tuple:
    """Returns (1min, 5min, 15min) load averages."""
    with open("/proc/loadavg") as f:
        parts = f.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def uptime_str() -> str:
    """Human-readable system uptime."""
    with open("/proc/uptime") as f:
        seconds = float(f.read().split()[0])
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


# ─── Per-service metrics ──────────────────────────────────────────────────────

def _service_main_pid(service_name: str) -> Optional[int]:
    """Get MainPID of a systemd service."""
    result = subprocess.run(
        ["systemctl", "show", service_name, "--property=MainPID"],
        capture_output=True, text=True
    )
    match = re.search(r"MainPID=(\d+)", result.stdout)
    if match:
        pid = int(match.group(1))
        return pid if pid > 0 else None
    return None


def _pid_cpu_mem(pid: int) -> tuple:
    """
    Read (cpu_percent, mem_rss_mb) for a PID.
    CPU is sampled over 300ms. Returns (0.0, 0.0) on failure.
    """
    def _read_stat(p):
        try:
            with open(f"/proc/{p}/stat") as f:
                data = f.read().split()
            utime  = int(data[13])
            stime  = int(data[14])
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
            return utime + stime, uptime
        except Exception:
            return None, None

    def _read_mem(p):
        try:
            with open(f"/proc/{p}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024  # MB
        except Exception:
            return 0.0
        return 0.0

    hz = os.sysconf("SC_CLK_TCK")
    t1, up1 = _read_stat(pid)
    if t1 is None:
        return 0.0, 0.0
    time.sleep(0.3)
    t2, up2 = _read_stat(pid)
    if t2 is None:
        return 0.0, 0.0

    cpu = round(100.0 * (t2 - t1) / hz / max(0.001, up2 - up1), 1)
    mem = round(_read_mem(pid), 1)
    return cpu, mem


def service_metrics(project_name: str) -> dict:
    """
    Returns {cpu_percent, mem_mb, pid} for a running service.
    Returns zeros if the service is not running.
    """
    from utils.systemctl import service_name
    svc = service_name(project_name)
    pid = _service_main_pid(svc)
    if not pid:
        return {"cpu_percent": 0.0, "mem_mb": 0.0, "pid": None}
    cpu, mem = _pid_cpu_mem(pid)
    return {"cpu_percent": cpu, "mem_mb": mem, "pid": pid}


# ─── System snapshot (all-in-one) ────────────────────────────────────────────

def full_snapshot(project_names: list) -> dict:
    """
    Returns a complete snapshot dict used by both TUI and bot chart generator.
    """
    mem  = memory_info()
    disk = disk_info()
    la   = load_avg()
    cpu  = cpu_percent()

    services = {}
    for name in project_names:
        services[name] = service_metrics(name)

    return {
        "cpu":      cpu,
        "mem":      mem,
        "disk":     disk,
        "load_avg": la,
        "uptime":   uptime_str(),
        "services": services,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─── Chart generation (PNG for Telegram) ─────────────────────────────────────

def generate_monitor_image(snapshot: dict, out_path: str) -> bool:
    """
    Render a dark-themed monitoring dashboard PNG.
    Requires matplotlib. Returns True on success.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import matplotlib.gridspec as gridspec
        import numpy as np
    except ImportError:
        return False

    BG      = "#0d1117"
    PANEL   = "#161b22"
    BORDER  = "#30363d"
    TEXT    = "#e6edf3"
    DIM     = "#8b949e"
    GREEN   = "#3fb950"
    YELLOW  = "#d29922"
    RED     = "#f85149"
    BLUE    = "#58a6ff"
    PURPLE  = "#bc8cff"

    def _bar_color(pct):
        if pct < 60: return GREEN
        if pct < 85: return YELLOW
        return RED

    services = snapshot.get("services", {})
    n_svc    = len(services)

    # Layout: top row (cpu, mem, disk gauges) + service rows
    rows = 2 + max(1, n_svc)
    fig  = plt.figure(figsize=(10, 2.8 + rows * 0.7), facecolor=BG)
    gs   = gridspec.GridSpec(rows, 3, figure=fig,
                             hspace=0.55, wspace=0.35,
                             left=0.05, right=0.97,
                             top=0.93, bottom=0.05)

    def _gauge_bar(ax, value, max_val, label, unit="", color=None):
        pct = min(100.0, 100.0 * value / max_val) if max_val else 0
        bar_color = color or _bar_color(pct)
        ax.set_facecolor(PANEL)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
            spine.set_linewidth(0.8)

        ax.barh(0, 100, height=0.6, color=BORDER, left=0)
        ax.barh(0, pct,  height=0.6, color=bar_color, left=0)

        ax.set_xlim(0, 100)
        ax.set_ylim(-0.8, 0.8)
        ax.set_yticks([])
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.tick_params(axis='x', labelsize=6, colors=DIM, pad=1)

        ax.text(0.5, 0.72, label, transform=ax.transAxes,
                ha='center', va='bottom', fontsize=8,
                color=TEXT, fontweight='bold')
        val_text = f"{value:.1f}{unit}  /  {max_val:.0f}{unit}  ({pct:.0f}%)"
        ax.text(0.5, -0.62, val_text, transform=ax.transAxes,
                ha='center', va='top', fontsize=6.5, color=DIM)

    # Row 0: title + meta
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.set_facecolor(BG)
    ax_title.axis("off")
    ax_title.text(0.0, 0.8, "VPS Monitor",
                  transform=ax_title.transAxes,
                  ha='left', va='top', fontsize=13,
                  color=TEXT, fontweight='bold')
    meta = (f"uptime: {snapshot.get('uptime','?')}   "
            f"load: {snapshot['load_avg'][0]:.2f} {snapshot['load_avg'][1]:.2f} {snapshot['load_avg'][2]:.2f}   "
            f"  {snapshot.get('timestamp','')}")
    ax_title.text(0.0, 0.05, meta,
                  transform=ax_title.transAxes,
                  ha='left', va='bottom', fontsize=7, color=DIM)

    # Row 1: CPU / Memory / Disk gauges
    ax_cpu  = fig.add_subplot(gs[1, 0])
    ax_mem  = fig.add_subplot(gs[1, 1])
    ax_disk = fig.add_subplot(gs[1, 2])

    cpu_pct  = snapshot["cpu"]
    mem      = snapshot["mem"]
    disk     = snapshot["disk"]

    _gauge_bar(ax_cpu,  cpu_pct,            100,
               "CPU", "%", color=_bar_color(cpu_pct))
    _gauge_bar(ax_mem,  mem["used_mb"],     mem["total_mb"],
               "Memory", " MB", color=_bar_color(mem["percent"]))
    _gauge_bar(ax_disk, disk["used_gb"],    disk["total_gb"],
               "Disk", " GB", color=_bar_color(disk["percent"]))

    # Rows 2+: per-service
    if services:
        max_cpu = max((v["cpu_percent"] for v in services.values()), default=1) or 1
        max_mem = max((v["mem_mb"]      for v in services.values()), default=1) or 1

        for i, (sname, sdata) in enumerate(services.items()):
            row = 2 + i
            ax_sc = fig.add_subplot(gs[row, 0])
            ax_sm = fig.add_subplot(gs[row, 1])
            ax_si = fig.add_subplot(gs[row, 2])

            _gauge_bar(ax_sc, sdata["cpu_percent"], max(max_cpu, 0.1),
                       f"{sname}  CPU", "%", color=BLUE)
            _gauge_bar(ax_sm, sdata["mem_mb"],      max(max_mem, 0.1),
                       f"{sname}  RAM", " MB", color=PURPLE)

            # Info cell
            ax_si.set_facecolor(PANEL)
            for spine in ax_si.spines.values():
                spine.set_edgecolor(BORDER); spine.set_linewidth(0.8)
            ax_si.axis("off")

            pid_str  = str(sdata["pid"]) if sdata["pid"] else "—"
            cpu_str  = f"{sdata['cpu_percent']:.1f}%"
            mem_str  = f"{sdata['mem_mb']:.1f} MB"
            ax_si.text(0.08, 0.75, sname,  transform=ax_si.transAxes,
                       fontsize=7.5, color=TEXT, fontweight='bold', va='top')
            ax_si.text(0.08, 0.42, f"CPU {cpu_str}  MEM {mem_str}  PID {pid_str}",
                       transform=ax_si.transAxes,
                       fontsize=6.5, color=DIM, va='top')
    else:
        ax_empty = fig.add_subplot(gs[2, :])
        ax_empty.set_facecolor(PANEL)
        ax_empty.axis("off")
        ax_empty.text(0.5, 0.5, "No services tracked",
                      transform=ax_empty.transAxes,
                      ha='center', va='center', color=DIM, fontsize=9)

    plt.savefig(out_path, dpi=140, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close(fig)
    return True