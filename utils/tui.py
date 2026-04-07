"""
vps-manager/utils/tui.py
─────────────────────────
Minimal terminal UI engine.
No external dependencies — pure curses.
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
KEY_HELP = [ord('h'), ord('H')]


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
        # key part bold, desc part normal
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

def help_menu(stdscr):
    curses.curs_set(0)
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚙️  BEFORE USING VPS MANAGER",
        "",
        "1. SYSTEM REQUIREMENTS:",
        "   • Ubuntu 20.04 / 22.04 (recommended)",
        "   • Root access or sudo user",
        "   • Internet connection",
        "",
        "2. REQUIRED APT PACKAGES:",
        "   Run:",
        "   sudo apt update",
        "   sudo apt install -y \\",
        "       python3 python3-pip python3-venv \\",
        "       nginx git curl \\",
        "       certbot python3-certbot-nginx \\",
        "       build-essential",
        "",
        "3. PYTHON & LIBRARIES:",
        "   • Python 3.10+ required",
        "   • Install aiogram:",
        "       pip install aiogram==2.25.1",
        "",
        "   ⚠️ IMPORTANT:",
        "   • Use SAME python as systemd",
        "   • Prefer: python3 -m pip install ...",
        "",
        "4. VIRTUAL ENVIRONMENT (OPTIONAL):",
        "   python3 -m venv venv",
        "   source venv/bin/activate",
        "   pip install aiogram==2.25.1",
        "",
        "   ⚠️ If using systemd:",
        "   ExecStart must use venv python!",
        "",
        "5. NETWORK & PORTS:",
        "   Open required ports:",
        "   • 22   → SSH",
        "   • 80   → HTTP",
        "   • 443  → HTTPS",
        "",
        "   Check open ports:",
        "   sudo ss -tulnp",
        "",
        "6. NGINX SETUP:",
        "   • Used for reverse proxy",
        "   • Auto-configured by vps-manager",
        "   • Test config:",
        "       sudo nginx -t",
        "",
        "7. SSL (HTTPS):",
        "   • Uses Let's Encrypt (certbot)",
        "   • Check installation:",
        "       certbot --version",
        "",
        "   • Renew manually:",
        "       sudo certbot renew",
        "",
        "   ⚠️ If error:",
        "       sudo apt install certbot",
        "",
        "8. SYSTEMD SERVICES:",
        "   • Used to run projects in background",
        "   • Commands:",
        "       sudo systemctl status <name>",
        "       sudo systemctl restart <name>",
        "",
        "9. PROJECT REQUIREMENTS:",
        "   Each project should have:",
        "   • runcommand (python, node, etc.)",
        "   • port",
        "   • working directory",
        "",
        "10. COMMON ERRORS:",
        "   • aiogram not installed → pip install",
        "   • certbot not found → apt install",
        "   • port in use → change port",
        "   • permission denied → use sudo",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "💡 TIP:",
        "   Press 'H' anytime to open this guide.",
        "",
        "Press any key to go back..."
    ]

    scroll = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        
        title = "📘 VPS Manager - Setup Guide"
        stdscr.addstr(1, 2, title[:w-4], curses.A_BOLD)
        draw_footer(stdscr, [("↑↓", "scroll"), ("PgUp/Dn", "page"), ("Esc", "back")])

        # Calculate visible area
        header_height = 3
        visible_end = h - 1
        visible_count = visible_end - header_height
        
        # Display visible lines
        for i in range(visible_count):
            line_idx = scroll + i
            if line_idx >= len(lines):
                break
            try:
                stdscr.addstr(header_height + i, 2, lines[line_idx][:w-4])
            except curses.error:
                pass

        # Show scroll indicator if content is longer than screen
        if len(lines) > visible_count:
            total = len(lines)
            bar_h = max(1, visible_count * visible_count // total)
            bar_y = header_height + (scroll * (visible_count - bar_h)) // max(1, total - visible_count)
            for by in range(header_height, h - 1):
                ch = '█' if bar_y <= by < bar_y + bar_h else '▒'
                try:
                    stdscr.addstr(by, w - 1, ch, curses.color_pair(CP_DIM))
                except curses.error:
                    pass

        stdscr.refresh()
        ch = stdscr.getch()
        
        # Handle key presses
        if is_key(ch, KEY_UP):
            scroll = max(0, scroll - 1)
        elif is_key(ch, KEY_DOWN):
            scroll = min(max(0, len(lines) - visible_count), scroll + 1)
        elif ch == curses.KEY_PPAGE:
            scroll = max(0, scroll - visible_count)
        elif ch == curses.KEY_NPAGE:
            scroll = min(max(0, len(lines) - visible_count), scroll + visible_count)
        elif is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK):
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
    # 0 = No, 1 = Yes
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

        # Border
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

        # Buttons
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
    Multi-field inline form.
    ↑/↓ or Tab moves between fields.
    Enter on last field submits. Esc cancels.
    """
    curses.curs_set(1)
    active  = 0
    cursors = [len(f.value) for f in fields]

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title)
        draw_footer(stdscr, [("↑↓/Tab", "next field"), ("Enter", "submit/next"), ("Esc", "cancel")])

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
            if is_active:
                stdscr.attron(curses.color_pair(CP_SELECTED))
                stdscr.hline(y, box_x, ' ', field_w + 2)
                stdscr.attroff(curses.color_pair(CP_SELECTED))
                safe_addstr(stdscr, y, box_x + 1, fld.value[:field_w],
                            curses.color_pair(CP_SELECTED))
                cur_x = box_x + 1 + min(cursors[i], field_w - 1)
                try:
                    stdscr.move(y, min(cur_x, w - 2))
                except curses.error:
                    pass
            else:
                safe_addstr(stdscr, y, box_x,
                            f"[{fld.value[:field_w]:<{field_w}}]",
                            curses.color_pair(CP_DIM))

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
            prev = active
            while True:
                active = max(0, active - 1)
                if not fields[active].required or active == 0:
                    break
            cursors[active] = len(fields[active].value)
            if start_y + active*3 >= h - 1:
                start_y -= 3

        elif is_key(ch, KEY_DOWN) or ch == ord('\t'):
            prev = active
            while True:
                active = min(len(fields) - 1, active + 1)
                if not fields[active].required or active == len(fields)-1:
                    break
            cursors[active] = len(fields[active].value)
            if start_y + active*3 >= h - 1:
                start_y += 3

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

        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            c = cursors[active]
            if c > 0:
                field.value = field.value[:c - 1] + field.value[c:]
                cursors[active] = c - 1

        elif ch == curses.KEY_DC:
            c = cursors[active]
            if c < len(field.value):
                field.value = field.value[:c] + field.value[c + 1:]

        elif ch == curses.KEY_HOME:
            cursors[active] = 0

        elif ch == curses.KEY_END:
            cursors[active] = len(field.value)

        elif ch == curses.KEY_LEFT:
            cursors[active] = max(0, cursors[active] - 1)

        elif ch == curses.KEY_RIGHT:
            cursors[active] = min(len(field.value), cursors[active] + 1)

        elif 32 <= ch <= 126:
            c = cursors[active]
            field.value = field.value[:c] + chr(ch) + field.value[c:]
            cursors[active] = c + 1