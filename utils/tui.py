"""
vps-manager/utils/tui.py
─────────────────────────
Minimal terminal UI engine.
No external dependencies — pure curses.

Changes v4:
  - form(): horizontal scroll for long input values (path fields etc.)
  - help_menu(): complete rewrite with all sections including git
"""

import curses
import textwrap
from typing import List, Optional, Tuple

# ─── Colour pair IDs ─────────────────────────────────────────────────────────
CP_NORMAL     = 0
CP_SELECTED   = 1
CP_TITLE      = 2
CP_STATUS_OK  = 3
CP_STATUS_ERR = 4
CP_STATUS_WAR = 5
CP_DIM        = 6
CP_BORDER     = 7


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_SELECTED,  curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_TITLE,     curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP_STATUS_OK, curses.COLOR_GREEN,  -1)
    curses.init_pair(CP_STATUS_ERR,curses.COLOR_RED,    -1)
    curses.init_pair(CP_STATUS_WAR,curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_DIM,       8,                   -1)
    curses.init_pair(CP_BORDER,    curses.COLOR_CYAN,   -1)


# ─── Key constants ────────────────────────────────────────────────────────────
KEY_UP    = [curses.KEY_UP,  ]
KEY_DOWN  = [curses.KEY_DOWN,]
KEY_LEFT  = [curses.KEY_LEFT,]
KEY_RIGHT = [curses.KEY_RIGHT]
KEY_ENTER = [curses.KEY_ENTER, ord('\n'), ord('\r'), 10, 13]
KEY_SPACE = [ord(' ')]
KEY_ESC   = [27]
KEY_QUIT  = [ord('q'), ord('Q')]
KEY_BACK  = KEY_ESC + [ord('b'), ord('B')]
KEY_HELP  = [ord('h'), ord('H')]


def is_key(ch: int, group: list) -> bool:
    return ch in group


# ─── Drawing helpers ──────────────────────────────────────────────────────────

def safe_addstr(win, y: int, x: int, text: str, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    max_len = w - x - 1
    if max_len <= 0:
        return
    try:
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def draw_header(win, title: str, subtitle: str = ""):
    h, w = win.getmaxyx()
    attr = curses.color_pair(CP_TITLE) | curses.A_BOLD
    win.attron(attr)
    win.hline(0, 0, ' ', w)
    safe_addstr(win, 0, 1, f" VPS Manager  ›  {title} ", attr)
    win.attroff(attr)
    if subtitle:
        safe_addstr(win, 1, 2, subtitle[:w - 3], curses.color_pair(CP_DIM))


def draw_footer(win, hints: List[Tuple[str, str]]):
    h, w = win.getmaxyx()
    attr = curses.color_pair(CP_TITLE)
    win.attron(attr)
    win.hline(h - 1, 0, ' ', w)
    x = 1
    for key, desc in hints:
        segment = f" {key}  {desc} "
        if x + len(segment) >= w - 1:
            break
        try:
            win.addstr(h - 1, x, f" {key}", curses.color_pair(CP_TITLE) | curses.A_BOLD)
            win.addstr(h - 1, x + 1 + len(key), f"  {desc} ", curses.color_pair(CP_TITLE))
        except curses.error:
            pass
        x += len(segment) + 1
    win.attroff(attr)


def status_attr(state: str) -> int:
    s = state.lower()
    if s == "active":
        return curses.color_pair(CP_STATUS_OK) | curses.A_BOLD
    if s in ("failed", "error"):
        return curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD
    if s == "no-unit":
        return curses.color_pair(CP_DIM)
    return curses.color_pair(CP_STATUS_WAR)


# ─── Help menu ────────────────────────────────────────────────────────────────

def help_menu(stdscr):
    curses.curs_set(0)
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  VPS MANAGER v4 — Complete Setup & Usage Guide",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "─── KEYBOARD SHORTCUTS (Dashboard) ─────────────────────",
        "  ↑ / ↓       Navigate project list",
        "  Enter        Open selected project menu",
        "  n            Add new project",
        "  N            Nginx management",
        "  s            SSL / Let's Encrypt",
        "  m            System monitor",
        "  g            Git manager",
        "  t            Telegram bot",
        "  e            View service errors",
        "  H            This help page",
        "  q            Quit",
        "",
        "─── KEYBOARD SHORTCUTS (Forms) ──────────────────────────",
        "  ↑ / ↓  or Tab    Move between fields",
        "  ← / →             Move cursor inside field",
        "  Home / End        Jump to start / end of field",
        "  Backspace / Del   Delete character",
        "  Enter             Next field / Submit (on last field)",
        "  Esc               Cancel / go back",
        "",
        "  NOTE: Long paths are scrolled horizontally.",
        "        The visible window follows your cursor.",
        "",
        "─── 1. SYSTEM REQUIREMENTS ──────────────────────────────",
        "  • Ubuntu 20.04 / 22.04 / 24.04 (recommended)",
        "  • Root access or sudo privileges",
        "  • Internet connection for package installs",
        "  • Python 3.10+ required",
        "",
        "─── 2. REQUIRED APT PACKAGES ────────────────────────────",
        "  Run once after fresh install:",
        "",
        "    sudo apt update && sudo apt install -y \\",
        "        python3 python3-pip python3-venv \\",
        "        nginx git curl build-essential \\",
        "        certbot python3-certbot-nginx",
        "",
        "─── 3. PYTHON VIRTUAL ENVIRONMENT ───────────────────────",
        "  Recommended setup:",
        "",
        "    cd /path/to/your/project",
        "    python3 -m venv venv",
        "    source venv/bin/activate",
        "    pip install <your-packages>",
        "",
        "  ⚠  When adding a project, set 'Python/venv path' to:",
        "     /path/to/your/project/venv/bin/python3",
        "",
        "  ⚠  systemd ExecStart MUST use the venv python,",
        "     not the system python3.",
        "",
        "─── 4. ADDING A PROJECT ─────────────────────────────────",
        "  Press [n] on the dashboard, then fill in:",
        "",
        "  • Project name    — unique, alphanumeric + _ -",
        "  • Project path    — absolute path (created if missing)",
        "  • Port            — leave blank for bots / workers",
        "  • Nginx route     — e.g. /  or  /api/  (for web apps)",
        "  • Python/venv     — full path to python binary",
        "  • Run command     — full command to start the service",
        "",
        "  After adding, you'll be asked to:",
        "    → Write systemd unit file",
        "    → Apply nginx config (if port set)",
        "",
        "─── 5. NETWORK & PORTS ──────────────────────────────────",
        "  Open required ports in firewall:",
        "    sudo ufw allow 22    # SSH",
        "    sudo ufw allow 80    # HTTP",
        "    sudo ufw allow 443   # HTTPS",
        "    sudo ufw enable",
        "",
        "  Check listening ports:",
        "    sudo ss -tulnp",
        "",
        "─── 6. NGINX SETUP ──────────────────────────────────────",
        "  VPS Manager auto-generates nginx configs.",
        "  Press [N] to manage nginx.",
        "",
        "  Manual check / reload:",
        "    sudo nginx -t",
        "    sudo systemctl reload nginx",
        "",
        "  Config files are written to:",
        "    /etc/nginx/sites-available/vps-<name>",
        "    /etc/nginx/sites-enabled/vps-<name>  (symlink)",
        "",
        "─── 7. SSL / HTTPS ──────────────────────────────────────",
        "  Uses Let's Encrypt via certbot.",
        "  Press [s] to manage certificates.",
        "",
        "  Manual renew:",
        "    sudo certbot renew",
        "",
        "  Check certbot version:",
        "    certbot --version",
        "",
        "  If certbot not found:",
        "    sudo apt install certbot python3-certbot-nginx",
        "",
        "─── 8. SYSTEMD SERVICES ─────────────────────────────────",
        "  Each project gets a unit file:",
        "    /etc/systemd/system/vps-<name>.service",
        "",
        "  Manual service commands:",
        "    sudo systemctl status vps-<name>",
        "    sudo systemctl restart vps-<name>",
        "    sudo systemctl enable vps-<name>",
        "    journalctl -u vps-<name> -f",
        "",
        "─── 9. GIT MANAGER ──────────────────────────────────────",
        "  Press [g] on the dashboard to open Git Manager.",
        "",
        "  First use: select a repository path",
        "    • Choose from existing project folders, or",
        "    • Enter path manually",
        "    • If folder has no git repo, you can git init it",
        "",
        "  The selected repo path is saved in config.json.",
        "  Use 'Change repository path' to switch repos.",
        "",
        "  Features:",
        "    Branches   → switch, create, delete, merge, rename",
        "    Commits    → browse log, view diffs, checkout commit",
        "    Staging    → stage all, stage file, unstage",
        "    Committing → commit, amend last commit",
        "    Stash      → push, list, pop, drop, show diff",
        "    Remotes    → add, remove, fetch, pull, push",
        "    Tools      → rm --cached, .gitignore editor,",
        "                  git user config, tags",
        "",
        "  rm --cached workflow:",
        "    1. Run 'rm --cached (untrack files)'",
        "    2. Enter file pattern (e.g. secrets.env or .)",
        "    3. Optionally add pattern to .gitignore",
        "    4. Commit the removal: 'Commit staged changes'",
        "",
        "─── 10. TELEGRAM BOT ────────────────────────────────────",
        "  Press [t] to configure the admin bot.",
        "",
        "  Setup steps:",
        "    1. Create a bot via @BotFather on Telegram",
        "    2. Get your Telegram user ID (use @userinfobot)",
        "    3. In vps-manager: t → Configure bot token",
        "    4. Enter token + admin IDs",
        "    5. Start bot service",
        "",
        "  Install aiogram (required):",
        "    pip install aiogram==2.25.1",
        "",
        "  Bot features:",
        "    /status    — all services status",
        "    /monitor   — PNG dashboard (needs matplotlib)",
        "    /projects  — inline project management",
        "    /logs      — per-service logs",
        "    /ssl       — certificate status",
        "    /renew     — renew all certificates",
        "    /system    — CPU/memory/disk",
        "",
        "  Error reporting:",
        "    When a bot command causes an error,",
        "    the full traceback is sent as a .txt file.",
        "",
        "─── 11. COMMON ERRORS & FIXES ───────────────────────────",
        "  Permission denied writing unit file",
        "    → Run vps-manager as root: sudo python3 run.py",
        "",
        "  Port already in use",
        "    → Change port in project settings",
        "    → Or: sudo fuser -k <port>/tcp",
        "",
        "  aiogram not installed",
        "    → pip install aiogram==2.25.1",
        "",
        "  certbot not found",
        "    → sudo apt install certbot python3-certbot-nginx",
        "",
        "  Service fails to start",
        "    → Press [e] to view error details",
        "    → Check run command and python path",
        "    → journalctl -u vps-<name> -n 50",
        "",
        "  git: command not found",
        "    → sudo apt install git",
        "",
        "  nginx -t fails after config apply",
        "    → Check server_name in nginx settings [N]",
        "    → sudo nginx -t  for detailed error",
        "",
        "─── 12. FILE LOCATIONS ──────────────────────────────────",
        "  config.json           — main config (projects, bot, nginx)",
        "  logs/                 — vps-manager logs + monitor PNGs",
        "  bot/admin_bot.py      — Telegram bot script",
        "  utils/                — all utility modules",
        "",
        "  /etc/nginx/sites-available/vps-*   — nginx configs",
        "  /etc/systemd/system/vps-*.service  — unit files",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  Press H anytime to return to this guide.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "  ↑/↓ scroll   PgUp/PgDn page   Esc back",
    ]

    scroll = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header
        attr_title = curses.color_pair(CP_TITLE) | curses.A_BOLD
        stdscr.attron(attr_title)
        stdscr.hline(0, 0, ' ', w)
        safe_addstr(stdscr, 0, 1, " VPS Manager  ›  Setup & Usage Guide ", attr_title)
        stdscr.attroff(attr_title)

        draw_footer(stdscr, [("↑↓", "scroll"), ("PgUp/Dn", "page"), ("Esc/q", "back")])

        header_height = 1
        visible_end   = h - 1
        visible_count = visible_end - header_height

        # Clamp scroll
        max_scroll = max(0, len(lines) - visible_count)
        scroll = max(0, min(scroll, max_scroll))

        for i in range(visible_count):
            line_idx = scroll + i
            if line_idx >= len(lines):
                break
            line = lines[line_idx]
            y    = header_height + i

            # Colour coding
            attr = 0
            if line.startswith("━"):
                attr = curses.color_pair(CP_BORDER)
            elif line.startswith("───"):
                attr = curses.color_pair(CP_DIM) | curses.A_BOLD
            elif line.startswith("  •") or line.startswith("    •"):
                attr = curses.color_pair(CP_STATUS_OK)
            elif line.startswith("  ⚠") or line.startswith("    ⚠"):
                attr = curses.color_pair(CP_STATUS_WAR) | curses.A_BOLD
            elif line.strip().startswith("→"):
                attr = curses.color_pair(CP_DIM)
            elif "sudo " in line or line.strip().startswith("pip ") or line.strip().startswith("python"):
                attr = curses.color_pair(CP_STATUS_WAR)

            try:
                stdscr.addstr(y, 2, line[:w - 4], attr)
            except curses.error:
                pass

        # Scrollbar
        if len(lines) > visible_count:
            bar_h = max(1, visible_count * visible_count // max(len(lines), 1))
            bar_y = header_height + (scroll * max(1, visible_count - bar_h) // max(1, max_scroll))
            for by in range(header_height, h - 1):
                ch_bar = '█' if bar_y <= by < bar_y + bar_h else '▒'
                try:
                    stdscr.addstr(by, w - 1, ch_bar, curses.color_pair(CP_DIM))
                except curses.error:
                    pass

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_UP):
            scroll = max(0, scroll - 1)
        elif is_key(ch, KEY_DOWN):
            scroll = min(max_scroll, scroll + 1)
        elif ch == curses.KEY_PPAGE:
            scroll = max(0, scroll - visible_count)
        elif ch == curses.KEY_NPAGE:
            scroll = min(max_scroll, scroll + visible_count)
        elif ch == curses.KEY_HOME:
            scroll = 0
        elif ch == curses.KEY_END:
            scroll = max_scroll
        elif is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK + KEY_HELP):
            break


# ─── Menu widget ──────────────────────────────────────────────────────────────

def menu(stdscr, title: str, items: List[str],
         subtitle: str = "",
         footer_hints: List[Tuple[str, str]] = None,
         start_index: int = 0) -> Optional[int]:
    """
    Vertical scrollable menu.
    Returns selected index or None on cancel.
    Items starting with '---' are section separators (not selectable).
    """
    curses.curs_set(0)
    if footer_hints is None:
        footer_hints = [("↑↓", "navigate"), ("Enter", "select"), ("Esc/q", "back")]

    idx    = max(0, min(start_index, len(items) - 1))
    scroll = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        header_rows = 2 if subtitle else 1
        draw_header(stdscr, title, subtitle)
        draw_footer(stdscr, footer_hints)

        top    = header_rows + 1
        bottom = h - 1
        vis    = bottom - top

        # Keep selection visible
        if idx - scroll >= vis - 1:
            scroll = idx - vis + 2
        if idx - scroll < 0:
            scroll = idx
        scroll = max(0, scroll)

        for i, item in enumerate(items):
            row = top + (i - scroll)
            if row < top or row >= bottom:
                continue

            is_sep = item.startswith("---")
            is_sel = (i == idx) and not is_sep

            if is_sep:
                label = item.lstrip("- ").strip()
                safe_addstr(stdscr, row, 2, f"── {label} ", curses.color_pair(CP_DIM) | curses.A_BOLD)
                try:
                    stdscr.hline(row, 2 + 4 + len(label), curses.ACS_HLINE, w - 6 - len(label))
                except curses.error:
                    pass
                continue

            if is_sel:
                stdscr.attron(curses.color_pair(CP_SELECTED) | curses.A_BOLD)
                stdscr.hline(row, 0, ' ', w)
                safe_addstr(stdscr, row, 0, f"  ▶  {item}",
                            curses.color_pair(CP_SELECTED) | curses.A_BOLD)
                stdscr.attroff(curses.color_pair(CP_SELECTED) | curses.A_BOLD)
            else:
                safe_addstr(stdscr, row, 0, f"     {item}")

        # Scrollbar
        if len(items) > vis:
            total  = len(items)
            bar_h  = max(1, vis * vis // total)
            bar_y  = top + (idx * (vis - bar_h)) // max(1, total - 1)
            for by in range(top, bottom):
                ch = '█' if bar_y <= by < bar_y + bar_h else '▒'
                safe_addstr(stdscr, by, w - 1, ch, curses.color_pair(CP_DIM))

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_UP):
            idx = max(0, idx - 1)
            while idx > 0 and items[idx].startswith("---"):
                idx -= 1
        elif is_key(ch, KEY_DOWN):
            idx = min(len(items) - 1, idx + 1)
            while idx < len(items) - 1 and items[idx].startswith("---"):
                idx += 1
        elif is_key(ch, KEY_ENTER):
            if not items[idx].startswith("---"):
                return idx
        elif is_key(ch, KEY_BACK + KEY_QUIT):
            return None


# ─── Confirm dialog ───────────────────────────────────────────────────────────

def confirm(stdscr, message: str, default: bool = False) -> bool:
    curses.curs_set(0)
    sel = 1 if default else 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, "Confirm")
        draw_footer(stdscr, [("←→", "choose"), ("Enter", "confirm"), ("Esc", "cancel")])

        box_w = min(64, w - 6)
        box_h = 7
        box_y = h // 2 - box_h // 2
        box_x = w // 2 - box_w // 2

        attr_b = curses.color_pair(CP_BORDER)
        try:
            stdscr.attron(attr_b)
            stdscr.hline(box_y,           box_x, curses.ACS_HLINE, box_w)
            stdscr.hline(box_y + box_h,   box_x, curses.ACS_HLINE, box_w)
            stdscr.vline(box_y,           box_x,          curses.ACS_VLINE, box_h + 1)
            stdscr.vline(box_y,           box_x + box_w,  curses.ACS_VLINE, box_h + 1)
            stdscr.addch(box_y,           box_x,          curses.ACS_ULCORNER)
            stdscr.addch(box_y,           box_x + box_w,  curses.ACS_URCORNER)
            stdscr.addch(box_y + box_h,   box_x,          curses.ACS_LLCORNER)
        except curses.error:
            pass
        stdscr.attroff(attr_b)

        lines = textwrap.wrap(message, box_w - 4)
        for i, line in enumerate(lines[:4]):
            safe_addstr(stdscr, box_y + 2 + i, box_x + 2, line)

        btn_y = box_y + box_h - 1
        labels = ["  No  ", "  Yes  "]
        total_btn_w = sum(len(l) for l in labels) + 4
        bx = w // 2 - total_btn_w // 2
        for i, lbl in enumerate(labels):
            attr = (curses.color_pair(CP_SELECTED) | curses.A_BOLD) if i == sel else curses.A_NORMAL
            safe_addstr(stdscr, btn_y, bx, lbl, attr)
            bx += len(lbl) + 2

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_LEFT):
            sel = 0
        elif is_key(ch, KEY_RIGHT):
            sel = 1
        elif is_key(ch, KEY_ENTER):
            return sel == 1
        elif is_key(ch, KEY_ESC):
            return False


# ─── Pager ────────────────────────────────────────────────────────────────────

def pager(stdscr, title: str, text: str):
    curses.curs_set(0)
    lines  = text.splitlines()
    scroll = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title)
        draw_footer(stdscr, [("↑↓", "scroll"), ("PgUp/Dn", "page"), ("Esc/q", "back")])

        vis = h - 3
        for i in range(vis):
            li = scroll + i
            if li >= len(lines):
                break
            safe_addstr(stdscr, 2 + i, 1, lines[li][:w - 2])

        if len(lines) > vis:
            pct = int(100 * scroll / max(1, len(lines) - vis))
            safe_addstr(stdscr, h - 1, w - 7,
                        f" {pct:3d}% ", curses.color_pair(CP_TITLE))

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_UP):
            scroll = max(0, scroll - 1)
        elif is_key(ch, KEY_DOWN):
            scroll = min(max(0, len(lines) - vis), scroll + 1)
        elif ch == curses.KEY_PPAGE:
            scroll = max(0, scroll - vis)
        elif ch == curses.KEY_NPAGE:
            scroll = min(max(0, len(lines) - vis), scroll + vis)
        elif is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK):
            return


# ─── Flash banner ─────────────────────────────────────────────────────────────

def flash(stdscr, message: str, ok: bool = True):
    h, w = stdscr.getmaxyx()
    attr = (curses.color_pair(CP_STATUS_OK) if ok else curses.color_pair(CP_STATUS_ERR)) | curses.A_BOLD
    stdscr.attron(attr)
    stdscr.hline(2, 0, ' ', w)
    icon = "✓" if ok else "✗"
    safe_addstr(stdscr, 2, 2, f"  {icon}  {message}  ", attr)
    stdscr.attroff(attr)
    stdscr.refresh()
    curses.napms(1600)


# ─── Form ─────────────────────────────────────────────────────────────────────

class FormField:
    def __init__(self, key: str, label: str, default: str = "",
                 required: bool = False, hint: str = ""):
        self.key      = key
        self.label    = label
        self.value    = default
        self.required = required
        self.hint     = hint


def form(stdscr, title: str, fields: List[FormField]) -> Optional[dict]:
    """
    Multi-field inline form with horizontal scrolling for long values.
    ↑/↓ or Tab moves between fields.
    Enter on last field submits. Esc cancels.

    Long values (paths, commands) scroll horizontally so the end
    of the string is always visible as you type.
    """
    curses.curs_set(1)
    active  = 0
    cursors = [len(f.value) for f in fields]
    # view_offsets[i] = leftmost char index shown in field i
    view_offsets = [0] * len(fields)

    def _clamp_view(i, field_w):
        """Ensure cursor is visible; adjust view_offset if needed."""
        c  = cursors[i]
        vo = view_offsets[i]
        # cursor too far right
        if c - vo >= field_w - 1:
            view_offsets[i] = c - field_w + 2
        # cursor too far left
        if c - vo < 0:
            view_offsets[i] = c
        view_offsets[i] = max(0, view_offsets[i])

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title)
        draw_footer(stdscr, [("↑↓/Tab", "next field"), ("Enter", "submit/next"),
                              ("Esc", "cancel"), ("←→", "cursor")])

        label_w = max((len(f.label) for f in fields), default=10) + 2
        field_w = min(56, w - label_w - 8)
        start_y = 2

        for i, fld in enumerate(fields):
            y = start_y + i * 3
            if y + 1 >= h - 1:
                break

            is_active = (i == active)
            req_mark  = "*" if fld.required else " "
            l_attr    = curses.A_BOLD if is_active else curses.color_pair(CP_DIM)

            safe_addstr(stdscr, y, 2, f"{req_mark} {fld.label:<{label_w}}", l_attr)

            box_x = 2 + 2 + label_w

            # Build visible slice of value
            vo          = view_offsets[i]
            visible_val = fld.value[vo: vo + field_w]
            # Pad to field_w
            display_val = f"{visible_val:<{field_w}}"

            # Left/right overflow indicators
            left_indicator  = "<" if vo > 0 else " "
            right_indicator = ">" if len(fld.value) > vo + field_w else " "

            if is_active:
                stdscr.attron(curses.color_pair(CP_SELECTED))
                stdscr.hline(y, box_x, ' ', field_w + 4)
                stdscr.attroff(curses.color_pair(CP_SELECTED))

                # overflow indicators
                safe_addstr(stdscr, y, box_x,
                            left_indicator, curses.color_pair(CP_STATUS_WAR) | curses.A_BOLD
                            if vo > 0 else curses.color_pair(CP_SELECTED))
                safe_addstr(stdscr, y, box_x + 1,
                            display_val[:field_w],
                            curses.color_pair(CP_SELECTED))
                safe_addstr(stdscr, y, box_x + 1 + field_w,
                            right_indicator,
                            curses.color_pair(CP_STATUS_WAR) | curses.A_BOLD
                            if len(fld.value) > vo + field_w else curses.color_pair(CP_SELECTED))

                # Place real cursor
                cur_x = box_x + 1 + (cursors[i] - vo)
                cur_x = max(box_x + 1, min(cur_x, box_x + field_w))
                try:
                    stdscr.move(y, min(cur_x, w - 2))
                except curses.error:
                    pass
            else:
                # Inactive: show beginning of value
                safe_addstr(stdscr, y, box_x,
                            f"[{fld.value[:field_w]:<{field_w}}]",
                            curses.color_pair(CP_DIM))
                # Show > if value truncated
                if len(fld.value) > field_w:
                    safe_addstr(stdscr, y, box_x + field_w + 1, ">",
                                curses.color_pair(CP_STATUS_WAR))

            if fld.hint and is_active and y + 1 < h - 1:
                safe_addstr(stdscr, y + 1, box_x + 1,
                            fld.hint[:w - box_x - 3],
                            curses.color_pair(CP_DIM))

        stdscr.refresh()
        ch    = stdscr.getch()
        field = fields[active]

        if is_key(ch, KEY_ESC):
            curses.curs_set(0)
            return None

        elif is_key(ch, KEY_UP):
            active = max(0, active - 1)
            cursors[active] = len(fields[active].value)
            _clamp_view(active, field_w)

        elif is_key(ch, KEY_DOWN) or ch == ord('\t'):
            active = min(len(fields) - 1, active + 1)
            cursors[active] = len(fields[active].value)
            _clamp_view(active, field_w)

        elif is_key(ch, KEY_ENTER):
            if active == len(fields) - 1:
                missing = [f.label for f in fields if f.required and not f.value.strip()]
                if missing:
                    flash(stdscr, f"Required: {', '.join(missing)}", ok=False)
                    continue
                curses.curs_set(0)
                return {f.key: f.value.strip() for f in fields}
            else:
                active += 1
                cursors[active] = len(fields[active].value)
                _clamp_view(active, field_w)

        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            c = cursors[active]
            if c > 0:
                field.value = field.value[:c - 1] + field.value[c:]
                cursors[active] = c - 1
                _clamp_view(active, field_w)

        elif ch == curses.KEY_DC:
            c = cursors[active]
            if c < len(field.value):
                field.value = field.value[:c] + field.value[c + 1:]
            _clamp_view(active, field_w)

        elif ch == curses.KEY_HOME:
            cursors[active]      = 0
            view_offsets[active] = 0

        elif ch == curses.KEY_END:
            cursors[active] = len(field.value)
            _clamp_view(active, field_w)

        elif ch == curses.KEY_LEFT:
            cursors[active] = max(0, cursors[active] - 1)
            _clamp_view(active, field_w)

        elif ch == curses.KEY_RIGHT:
            cursors[active] = min(len(field.value), cursors[active] + 1)
            _clamp_view(active, field_w)

        elif 32 <= ch <= 126:
            c = cursors[active]
            field.value = field.value[:c] + chr(ch) + field.value[c:]
            cursors[active] = c + 1
            _clamp_view(active, field_w)