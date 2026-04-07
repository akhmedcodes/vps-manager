"""
vps-manager/utils/tui.py
Minimal terminal UI engine: keyboard navigation, menus, forms.
No external dependencies — uses curses from stdlib.
"""

import curses
import textwrap
from typing import List, Optional, Tuple, Callable


CP_NORMAL    = 0
CP_SELECTED  = 1    
CP_TITLE     = 2   
CP_STATUS_OK = 3    
CP_STATUS_ERR= 4    
CP_STATUS_WAR= 5    
CP_DIM       = 6    
CP_BORDER    = 7   


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_SELECTED,  curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(CP_TITLE,     curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(CP_STATUS_OK, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_STATUS_ERR,curses.COLOR_RED,   -1)
    curses.init_pair(CP_STATUS_WAR,curses.COLOR_YELLOW,-1)
    curses.init_pair(CP_DIM,       8,                  -1)
    curses.init_pair(CP_BORDER,    curses.COLOR_WHITE, -1)


# ─── Key constants ───────────────────────────────────────────────────────────
KEY_UP    = [curses.KEY_UP,   ]
KEY_DOWN  = [curses.KEY_DOWN, ]
KEY_LEFT  = [curses.KEY_LEFT, ]
KEY_RIGHT = [curses.KEY_RIGHT,]
KEY_ENTER = [curses.KEY_ENTER, ord('\n'), ord('\r'), 10, 13]
KEY_SPACE = [ord(' ')]
KEY_ESC   = [27]
KEY_QUIT  = [ord('q'), ord('Q')]
KEY_BACK  = KEY_ESC


def is_key(ch: int, group: list) -> bool:
    return ch in group


# ─── Drawing helpers ─────────────────────────────────────────────────────────

def safe_addstr(win, y: int, x: int, text: str, attr=0):
    """addstr that clips to window bounds."""
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
    win.attron(curses.color_pair(CP_TITLE) | curses.A_BOLD)
    win.hline(0, 0, ' ', w)
    safe_addstr(win, 0, 2, f"  VPS Manager  »  {title}  ", curses.color_pair(CP_TITLE) | curses.A_BOLD)
    win.attroff(curses.color_pair(CP_TITLE) | curses.A_BOLD)
    if subtitle:
        safe_addstr(win, 1, 2, subtitle, curses.color_pair(CP_DIM))


def draw_footer(win, hints: List[Tuple[str, str]]):
    """hints = [("↑↓", "navigate"), ("Enter", "select"), ...]"""
    h, w = win.getmaxyx()
    win.attron(curses.color_pair(CP_TITLE))
    win.hline(h - 1, 0, ' ', w)
    x = 1
    for key, desc in hints:
        text = f" {key}:{desc} "
        safe_addstr(win, h - 1, x, text, curses.color_pair(CP_TITLE))
        x += len(text) + 1
        if x >= w - 2:
            break
    win.attroff(curses.color_pair(CP_TITLE))


def status_attr(state: str) -> int:
    """Return colour attribute for a service state string."""
    s = state.lower()
    if s == "active":
        return curses.color_pair(CP_STATUS_OK) | curses.A_BOLD
    if s in ("failed", "error"):
        return curses.color_pair(CP_STATUS_ERR) | curses.A_BOLD
    return curses.color_pair(CP_STATUS_WAR)


# ─── Menu widget ─────────────────────────────────────────────────────────────

def menu(stdscr, title: str, items: List[str],
         subtitle: str = "",
         footer_hints: List[Tuple[str, str]] = None,
         start_index: int = 0) -> Optional[int]:
    """
    Vertical menu. Returns selected index or None (ESC/q).
    Items can include disabled items prefixed with '---' (separators).
    """
    curses.curs_set(0)
    if footer_hints is None:
        footer_hints = [("↑↓/ws", "navigate"), ("Enter", "select"), ("q/Esc", "back")]

    idx = max(0, min(start_index, len(items) - 1))
    scroll = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title, subtitle)
        draw_footer(stdscr, footer_hints)

        visible_start = 2
        visible_end   = h - 1
        visible_rows  = visible_end - visible_start

        # Keep idx in view
        if idx - scroll >= visible_rows - 1:
            scroll = idx - visible_rows + 2
        if idx - scroll < 0:
            scroll = idx
        scroll = max(0, scroll)

        for i, item in enumerate(items):
            row = visible_start + (i - scroll)
            if row < visible_start or row >= visible_end:
                continue

            is_sep = item.startswith("---")
            is_sel = (i == idx) and not is_sep

            if is_sep:
                # Render separator
                label = item.lstrip("- ").strip()
                safe_addstr(stdscr, row, 2,
                    f"  {label}",
                    curses.color_pair(CP_DIM) | curses.A_BOLD)
                continue

            prefix = " ● " if is_sel else "   "
            attr   = curses.color_pair(CP_SELECTED) | curses.A_BOLD if is_sel else 0

            if is_sel:
                stdscr.attron(attr)
                stdscr.hline(row, 0, ' ', w)
                stdscr.attroff(attr)

            safe_addstr(stdscr, row, 0, f"{prefix}{item}", attr)

        # Scroll indicator
        if len(items) > visible_rows:
            total = len(items)
            bar_h = max(1, visible_rows * visible_rows // total)
            bar_y = visible_start + (idx * (visible_rows - bar_h)) // max(1, total - 1)
            for by in range(visible_start, visible_end):
                char = '█' if visible_start + bar_y - visible_start <= by < visible_start + bar_y - visible_start + bar_h else '░'
                safe_addstr(stdscr, by, w - 2, char, curses.color_pair(CP_DIM))

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

    return None


# ─── Confirmation dialog ──────────────────────────────────────────────────────

def confirm(stdscr, message: str, default: bool = False) -> bool:
    """Show a Y/N confirmation dialog. Returns True/False."""
    curses.curs_set(0)
    options = ["  No  ", "  Yes  "]
    sel = 1 if default else 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, "Confirm")
        draw_footer(stdscr, [("←→/ad", "choose"), ("Enter", "confirm"), ("Esc", "cancel")])

        # Box
        box_w = min(60, w - 4)
        box_h = 7
        box_y = h // 2 - box_h // 2
        box_x = w // 2 - box_w // 2

        # Draw message
        lines = textwrap.wrap(message, box_w - 4)
        for i, line in enumerate(lines[:4]):
            safe_addstr(stdscr, box_y + 1 + i, box_x + 2, line)

        # Buttons
        btn_y = box_y + box_h - 2
        btn_x = box_x + box_w // 2 - 8
        for i, opt in enumerate(options):
            attr = curses.color_pair(CP_SELECTED) | curses.A_BOLD if i == sel else curses.A_NORMAL
            safe_addstr(stdscr, btn_y, btn_x + i * 9, opt, attr)

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


# ─── Pager (full-screen text viewer) ─────────────────────────────────────────

def pager(stdscr, title: str, text: str):
    """
    Scrollable text pager. ESC or q to exit.
    """
    curses.curs_set(0)
    lines = text.splitlines()
    scroll = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title)
        draw_footer(stdscr, [("↑↓/ws", "scroll"), ("PgUp/PgDn", "page"), ("Esc/q", "back")])

        visible_rows = h - 3
        for i in range(visible_rows):
            line_idx = scroll + i
            if line_idx >= len(lines):
                break
            safe_addstr(stdscr, 2 + i, 1, lines[line_idx][:w - 2])

        # Scroll % indicator
        if len(lines) > visible_rows:
            pct = int(100 * scroll / max(1, len(lines) - visible_rows))
            safe_addstr(stdscr, h - 1, w - 8,
                        f" {pct:3d}% ", curses.color_pair(CP_TITLE))

        stdscr.refresh()
        ch = stdscr.getch()

        if is_key(ch, KEY_UP):
            scroll = max(0, scroll - 1)
        elif is_key(ch, KEY_DOWN):
            scroll = min(max(0, len(lines) - visible_rows), scroll + 1)
        elif ch in [curses.KEY_PPAGE]:
            scroll = max(0, scroll - visible_rows)
        elif ch in [curses.KEY_NPAGE]:
            scroll = min(max(0, len(lines) - visible_rows), scroll + visible_rows)
        elif is_key(ch, KEY_ESC + KEY_QUIT + KEY_BACK):
            return


# ─── Notification banner (non-blocking) ──────────────────────────────────────

def flash(stdscr, message: str, ok: bool = True):
    """Brief full-width message bar on row 2."""
    h, w = stdscr.getmaxyx()
    attr = curses.color_pair(CP_STATUS_OK) if ok else curses.color_pair(CP_STATUS_ERR)
    attr |= curses.A_BOLD
    stdscr.attron(attr)
    stdscr.hline(2, 0, ' ', w)
    safe_addstr(stdscr, 2, 2, f"  {'✓' if ok else '✗'}  {message}  ", attr)
    stdscr.attroff(attr)
    stdscr.refresh()
    curses.napms(1400)


# ─── Input form ───────────────────────────────────────────────────────────────

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
    Multi-field input form. Returns dict of {key: value} or None on cancel.
    Navigate with Up/Down, edit with printable chars, Backspace to delete.
    Enter on last field or Tab submits. Esc cancels.
    """
    curses.curs_set(1)
    active = 0
    # Initialise cursors
    cursors = [len(f.value) for f in fields]

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        draw_header(stdscr, title)
        draw_footer(stdscr, [
            ("↑↓", "next field"), ("Enter", "submit"), ("Esc", "cancel")
        ])

        label_w = max(len(f.label) for f in fields) + 2
        field_w = min(50, w - label_w - 6)
        start_y = 3

        for i, field in enumerate(fields):
            y = start_y + i * 3
            if y + 1 >= h - 1:
                break

            is_active = (i == active)
            lattr  = curses.A_BOLD if is_active else curses.color_pair(CP_DIM)
            req    = "*" if field.required else " "

            safe_addstr(stdscr, y, 2, f"{req} {field.label:<{label_w}}", lattr)

            # Input box
            box_x = 2 + 2 + label_w
            if is_active:
                stdscr.attron(curses.color_pair(CP_SELECTED))
                stdscr.hline(y, box_x, ' ', field_w + 2)
                stdscr.attroff(curses.color_pair(CP_SELECTED))
                display_val = field.value
                safe_addstr(stdscr, y, box_x + 1, display_val[:field_w],
                            curses.color_pair(CP_SELECTED))
                # Cursor position
                cur_x = box_x + 1 + min(cursors[i], field_w - 1)
                stdscr.move(y, min(cur_x, w - 2))
            else:
                safe_addstr(stdscr, y, box_x, f"[{field.value[:field_w]:<{field_w}}]",
                            curses.color_pair(CP_DIM))

            if field.hint and is_active:
                safe_addstr(stdscr, y + 1, box_x, field.hint[:w - box_x - 2],
                            curses.color_pair(CP_DIM))

        stdscr.refresh()
        ch = stdscr.getch()
        field = fields[active]

        if is_key(ch, KEY_ESC):
            curses.curs_set(0)
            return None

        elif is_key(ch, KEY_UP):
            active = max(0, active - 1)

        elif is_key(ch, KEY_DOWN) or ch == ord('\t'):
            active = min(len(fields) - 1, active + 1)

        elif is_key(ch, KEY_ENTER):
            # Last field → submit; otherwise move down
            if active == len(fields) - 1:
                # Validate required
                missing = [f.label for f in fields if f.required and not f.value.strip()]
                if missing:
                    flash(stdscr, f"Required: {', '.join(missing)}", ok=False)
                    continue
                curses.curs_set(0)
                return {f.key: f.value.strip() for f in fields}
            else:
                active += 1

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