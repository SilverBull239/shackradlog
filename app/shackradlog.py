#!/usr/bin/env python3
"""
shackradlog.py — Ham Radio Contact Logger
SQLite backend · TUI interface · ADIF / CSV / JSON export
Requires Python 3.11+  |  No third-party dependencies

Copyright (C) 2026  Aron Tkachuk
Contact: silverbull239@proton.me
Paper mail: intentionally omitted

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# ── GPL interactive startup notice (required by GPL section 5c) ───────────────
_GPL_NOTICE = """\
shackradlog  Copyright (C) 2026  Aron Tkachuk
This program comes with ABSOLUTELY NO WARRANTY; for details type 'show w'.
This is free software, and you are welcome to redistribute it
under certain conditions; type 'show c' for details.\
"""

_GPL_WARRANTY = """\
DISCLAIMER OF WARRANTY (GPL v3, sections 15-16):

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
  APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
  HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT
  WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT
  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
  PARTICULAR PURPOSE. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE
  OF THE PROGRAM IS WITH YOU. SHOULD THE PROGRAM PROVE DEFECTIVE, YOU
  ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  See <https://www.gnu.org/licenses/gpl-3.0.txt> for the full license.\
"""

_GPL_CONDITIONS = """\
REDISTRIBUTION CONDITIONS (GPL v3, summary):

  You may copy and distribute verbatim copies of this program.
  You may modify and distribute modified copies under the GPL v3.
  You must keep copyright notices intact and provide the full license text.
  You must make source code available to anyone you distribute binaries to.
  You may NOT impose further restrictions on recipients' rights.

  Full license: <https://www.gnu.org/licenses/gpl-3.0.txt>
  Contact:      silverbull239@proton.me\
"""

import curses
import os
import re
import sqlite3
import sys
import datetime
from pathlib import Path

# ── Require Python 3.11+ ──────────────────────────────────────────────────────
if sys.version_info < (3, 11):
    sys.exit("shackradlog requires Python 3.11 or newer.")

# ── Paths ─────────────────────────────────────────────────────────────────────
DB_DIR  = Path.home() / ".shackradlog"
DB_PATH = DB_DIR / "shackradlog.db"
CONFIG_FILE = DB_DIR / "mycall"
DB_DIR.mkdir(parents=True, exist_ok=True)

def get_my_callsigns() -> str:
    """Load operator callsign(s) from ~/.shackradlog/mycall if it exists.
    
    Supports labeled format: HAM:KJ5PEJ, GMRS:WRYS604
    Or simple format: KJ5PEJ, WRYS604
    """
    if CONFIG_FILE.exists():
        try:
            text = CONFIG_FILE.read_text().strip()
            # Split by comma or newline
            parts = [c.strip() for c in text.replace('\n', ',').split(',') if c.strip()]
            formatted = []
            for part in parts:
                if ':' in part:
                    # Labeled format like "HAM:KJ5PEJ"
                    label, call = part.split(':', 1)
                    formatted.append(f"{label.strip().upper()}: {call.strip().upper()}")
                else:
                    # Simple callsign
                    formatted.append(part.upper())
            return '; '.join(formatted) if formatted else ""
        except Exception:
            return ""
    return ""

# ── Frequency / band helpers (see shackradlog_freq.py) ────────────────────────────
from shackradlog_freq import BAND_MAP, normalize_freq, freq_to_band

# ── Location parsing (see shackradlog_location.py) ─────────────────────────────────
from shackradlog_location import parse_location, _fmt_location

# ── Database layer (see shackradlog_db.py) ─────────────────────────────────────────
from shackradlog_db import (
    db_connect, db_insert, db_update, db_delete,
    db_fetch, db_worked_counts, db_stats,
    # Frequency/Repeater database
    FREQ_TYPES, freq_db_init, freq_db_insert, freq_db_update,
    freq_db_delete, freq_db_fetch, freq_db_get,
)

# ── Export/Import (see shackradlog_export.py) ─────────────────────────────────────
from shackradlog_export import (
    export_adif, export_csv, export_json,
    import_adif, import_csv, import_json, check_duplicate,
    _ADIF_MODE_MAP,
)

# ── Color pairs ───────────────────────────────────────────────────────────────
CP = dict(title=1, header=2, odd=3, even=4, field=5,
          input=6, status=7, border=8, highlight=9, key=10, dim=11, warn=12)
CP_OVERLAY = 13   # white on black — opaque overlay interior fill

def init_colors():
    if not curses.has_colors():
        return  # Gracefully degrade on terminals without color support
    curses.start_color()
    curses.use_default_colors()
    # ── Palette ───────────────────────────────────────────────────────────────
    # title     : black on cyan        — title bars
    # header    : bold cyan on default — column headers
    # odd       : white on default     — normal rows
    # even      : bright yellow on default — alternating rows (warm, readable)
    # field     : cyan on default      — form field labels
    # input     : white on blue        — active input box
    # status    : black on green       — status / hint bars
    # border    : cyan on default      — box borders, separators
    # highlight : black on yellow      — selected row / active field label
    # key       : bold green on default — key hints, previews
    # dim       : white on black (bold=off) — secondary/hint text inside overlays
    # warn      : white on red         — warnings (solid bg, always readable)
    # overlay   : white on black       — overlay interior fill (opaque background)
    curses.init_pair(CP["title"],     curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(CP["header"],    curses.COLOR_CYAN,   -1)
    curses.init_pair(CP["odd"],       curses.COLOR_WHITE,  curses.COLOR_BLACK)
    curses.init_pair(CP["even"],      curses.COLOR_YELLOW, -1)
    curses.init_pair(CP["field"],     curses.COLOR_CYAN,   -1)
    curses.init_pair(CP["input"],     curses.COLOR_WHITE,  curses.COLOR_BLUE)
    curses.init_pair(CP["status"],    curses.COLOR_BLACK,  curses.COLOR_GREEN)
    curses.init_pair(CP["border"],    curses.COLOR_CYAN,   -1)
    curses.init_pair(CP["highlight"], curses.COLOR_BLACK,  curses.COLOR_YELLOW)
    curses.init_pair(CP["key"],       curses.COLOR_GREEN,  -1)
    curses.init_pair(CP["dim"],       curses.COLOR_WHITE,  curses.COLOR_BLACK)
    curses.init_pair(CP["warn"],      curses.COLOR_WHITE,  curses.COLOR_RED)
    # Overlay background — must be called here so CP_OVERLAY is always ready
    curses.init_pair(CP_OVERLAY,      curses.COLOR_WHITE,  curses.COLOR_BLACK)

def cp(name: str, bold: bool = False) -> int:
    attr = curses.color_pair(CP[name])
    return attr | curses.A_BOLD if bold else attr

# ── Drawing helpers ───────────────────────────────────────────────────────────
def safe_add(win, y: int, x: int, text: str, attr: int = 0):
    try:
        max_y, max_x = win.getmaxyx()
        if y < 0 or y >= max_y or x < 0 or x >= max_x:
            return
        win.addstr(y, x, text[: max_x - x - 1], attr)
    except curses.error:
        pass

def fill_box(win, y: int, x: int, h: int, w: int):
    """Fill the interior of a box with spaces using overlay color (black bg).
    Call this before draw_box to create a clean opaque overlay."""
    attr = curses.color_pair(CP_OVERLAY)
    blank = " " * (w - 2)
    for row in range(1, h - 1):
        try:
            max_y, max_x = win.getmaxyx()
            if y + row >= max_y:
                break
            win.addstr(y + row, x + 1, blank[: max_x - x - 2], attr)
        except curses.error:
            pass

def draw_box(win, y: int, x: int, h: int, w: int, color: str = "border",
             fill: bool = False):
    """Draw a box. If fill=True, flood the interior with the overlay colour first."""
    if fill:
        fill_box(win, y, x, h, w)
    a = cp(color)
    chars = [curses.ACS_ULCORNER, curses.ACS_URCORNER,
             curses.ACS_LLCORNER, curses.ACS_LRCORNER,
             curses.ACS_HLINE,    curses.ACS_VLINE]
    try:
        win.attron(a)
        win.addch(y,     x,     chars[0])
        win.addch(y,     x+w-1, chars[1])
        win.addch(y+h-1, x,     chars[2])
        win.addch(y+h-1, x+w-1, chars[3])
        for i in range(1, w-1):
            win.addch(y,     x+i, chars[4])
            win.addch(y+h-1, x+i, chars[4])
        for i in range(1, h-1):
            win.addch(y+i, x,     chars[5])
            win.addch(y+i, x+w-1, chars[5])
        win.attroff(a)
    except curses.error:
        pass

# ── Text input widget ─────────────────────────────────────────────────────────
def get_input(win, y: int, x: int, width: int, prefill: str = "") -> str | None:
    curses.curs_set(1)
    buf = list(prefill)
    pos = len(buf)

    while True:
        display = ("".join(buf))[:width].ljust(width)
        safe_add(win, y, x, display, cp("input"))
        try:
            win.move(y, min(x + pos, x + width - 1))
        except curses.error:
            pass
        win.refresh()

        ch = win.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            break
        elif ch == 27:
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0:
                buf.pop(pos - 1); pos -= 1
        elif ch == curses.KEY_DC:
            if pos < len(buf): buf.pop(pos)
        elif ch == curses.KEY_LEFT:
            pos = max(0, pos - 1)
        elif ch == curses.KEY_RIGHT:
            pos = min(len(buf), pos + 1)
        elif ch == curses.KEY_HOME:
            pos = 0
        elif ch == curses.KEY_END:
            pos = len(buf)
        elif 32 <= ch <= 126 and len(buf) < width - 1:
            buf.insert(pos, chr(ch)); pos += 1

    curses.curs_set(0)
    return "".join(buf).strip()

# ── Field definitions ─────────────────────────────────────────────────────────
FORM_FIELDS: list[tuple[str, str, str]] = [
    # (key, label, hint)
    ("callsign", "Callsign",       "e.g. W1AW"),
    ("freq",     "Frequency (MHz)","e.g. 14.225  →  band auto-detected"),
    ("mode",     "Mode",           "SSB USB LSB CW FT8 FT4 JS8 FM AM RTTY WSPR PSK31 ..."),
    ("rst_sent", "RST Sent",       "e.g. 59  or  599"),
    ("rst_rcvd", "RST Rcvd",       "e.g. 59  or  599"),
    ("qth",      "QTH",            "City, State or Grid square"),
    ("power",    "Power (W)",      "e.g. 100"),
    ("notes",    "Notes",          "Any extra info"),
]

# ── New / Edit contact form ───────────────────────────────────────────────────
# Navigation actions returned from the inner input loop
_ACT_NEXT   = "next"
_ACT_PREV   = "prev"
_ACT_SAVE   = "save"
_ACT_CANCEL = "cancel"

def _form_input(stdscr, y: int, x: int, width: int, prefill: str = "") -> tuple[str, str]:
    """
    Like get_input but also handles ↑ (prev field), F2/Ctrl+S (save now).
    Returns (value, action) where action is one of _ACT_*.
    LEFT/RIGHT only move within the text; UP/DOWN navigate fields.
    """
    curses.curs_set(1)
    buf    = list(prefill)
    pos    = len(buf)
    action = _ACT_NEXT  # safe default for any unrecognized key code

    while True:
        display = ("".join(buf))[:width].ljust(width)
        safe_add(stdscr, y, x, display, cp("input"))
        try:
            stdscr.move(y, min(x + pos, x + width - 1))
        except curses.error:
            pass
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (curses.KEY_ENTER, 10, 13):
            action = _ACT_NEXT
            break
        elif ch == 27:
            action = _ACT_CANCEL
            break
        elif ch == 19:          # Ctrl+S — save and exit form
            action = _ACT_SAVE
            break
        elif ch == curses.KEY_UP:
            action = _ACT_PREV
            break
        elif ch == curses.KEY_DOWN:
            action = _ACT_NEXT
            break
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0: buf.pop(pos - 1); pos -= 1
        elif ch == curses.KEY_DC:
            if pos < len(buf): buf.pop(pos)
        elif ch == curses.KEY_LEFT:
            pos = max(0, pos - 1)
        elif ch == curses.KEY_RIGHT:
            pos = min(len(buf), pos + 1)
        elif ch == curses.KEY_HOME:
            pos = 0
        elif ch == curses.KEY_END:
            pos = len(buf)
        elif 32 <= ch <= 126 and len(buf) < width - 1:
            buf.insert(pos, chr(ch)); pos += 1

    curses.curs_set(0)
    return "".join(buf).strip(), action


def _qth_preview(raw: str) -> str:
    """
    Return a one-line preview string for a QTH value as the user types.
    Uses parse_location with no callsign — fast, no DB write.
    Returns '' when raw is empty.
    """
    if not raw.strip():
        return ""
    loc = parse_location(raw, "")
    if loc["qth_ambiguous"]:
        return f"→ {loc['qth_display']}  ⚠ ambiguous — pick on save"
    if loc["qth_resolved"]:
        return f"→ {loc['qth_display']}"
    return "→ ⚠ not recognized (stored as free text)"


def _location_picker(stdscr, candidates: list[dict]) -> dict | None:
    """
    Show a disambiguation overlay listing candidate cities.
    Returns the chosen city dict, or None if the user pressed ESC (keep best guess).
    """
    if not candidates:
        return None

    max_y, max_x = stdscr.getmaxyx()
    pw = min(62, max_x - 4)
    ph = len(candidates) + 6
    py = max(1, (max_y - ph) // 2)
    px = max(1, (max_x - pw) // 2)
    sel = 0

    def fmt(c: dict) -> str:
        admin = c.get("admin1_name") or c.get("admin1_code") or ""
        pop   = c.get("population") or 0
        pop_s = f"{pop:,}" if pop else "?"
        loc   = f"{c['city']}, {admin}, {c['country']}" if admin else f"{c['city']}, {c['country']}"
        return f"  {loc:<38}  pop {pop_s}"

    while True:
        stdscr.clear()
        draw_box(stdscr, py, px, ph, pw, fill=True)
        safe_add(stdscr, py, px + (pw - 22) // 2,
                 " AMBIGUOUS LOCATION ", cp("title", bold=True))
        safe_add(stdscr, py+1, px+3,
                 "Multiple cities match — choose one:", cp("field"))

        for i, c in enumerate(candidates):
            attr = cp("highlight", bold=True) if i == sel else cp("odd")
            safe_add(stdscr, py+2+i, px+2, fmt(c)[:pw-4].ljust(pw-4), attr)

        safe_add(stdscr, py+ph-2, px+3,
                 " ↑↓=select  ENTER=confirm  ESC=keep best guess ".ljust(pw-6),
                 cp("status"))
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == curses.KEY_UP:
            sel = max(0, sel - 1)
        elif ch == curses.KEY_DOWN:
            sel = min(len(candidates) - 1, sel + 1)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return candidates[sel]
        elif ch == 27:
            return None


def _draw_form(stdscr, rows, fy, fx, form_h, form_w, label_w, input_w,
               auto_date, auto_utc, values, prefills, idx, edit_row):
    stdscr.clear()
    draw_table_screen(stdscr, rows)
    draw_box(stdscr, fy, fx, form_h, form_w, fill=True)
    title = " EDIT CONTACT " if edit_row else " NEW CONTACT "
    safe_add(stdscr, fy, fx + (form_w - len(title)) // 2, title, cp("title", bold=True))

    safe_add(stdscr, fy+1, fx+2,
             f"  Date (UTC): {auto_date}    Time (UTC): {auto_utc}",
             cp("field"))
    safe_add(stdscr, fy+2, fx+2, "─" * (form_w - 4), cp("border"))

    for i, (key, label, hint) in enumerate(FORM_FIELDS):
        row_y = fy + 3 + i
        is_cur = (i == idx)
        lab_attr = cp("highlight", bold=True) if is_cur else cp("field")
        safe_add(stdscr, row_y, fx+2, f"  {label:<{label_w}}", lab_attr)
        val = values.get(key, prefills.get(key, ""))
        inp_attr = cp("input") if is_cur else cp("odd")
        safe_add(stdscr, row_y, fx+2+label_w+2, val[:input_w].ljust(input_w), inp_attr)

    hint_y = fy + 3 + len(FORM_FIELDS) + 1
    safe_add(stdscr, hint_y, fx+2,
             " ↑↓=navigate  ENTER=next  ^S=SAVE  ESC=cancel ".ljust(form_w-4),
             cp("status"))
    cur_hint = FORM_FIELDS[idx][2]
    safe_add(stdscr, hint_y+1, fx+3, cur_hint[:form_w-4], cp("dim"))

    # Live band preview when on freq field
    if FORM_FIELDS[idx][0] == "freq":
        cur_val = values.get("freq", prefills.get("freq", ""))
        norm    = normalize_freq(cur_val)
        band    = freq_to_band(cur_val)
        preview = f"→ {norm} MHz" if norm != cur_val else ""
        if band:
            preview += f"  [{band}]"
        if preview:
            safe_add(stdscr, hint_y+2, fx+3, preview[:form_w-4], cp("key", bold=True))

    # Live location preview when on qth field
    if FORM_FIELDS[idx][0] == "qth":
        cur_val = values.get("qth", prefills.get("qth", "")).strip()
        preview = _qth_preview(cur_val)
        safe_add(stdscr, hint_y+2, fx+3,
                 preview[:form_w-4].ljust(form_w-6), cp("key", bold=True))

    stdscr.refresh()


def _callsign_history(conn: sqlite3.Connection, prefix: str) -> list[sqlite3.Row]:
    """
    Return up to 10 previous contacts whose callsign starts with prefix.
    Ordered most-recent first.
    """
    if not prefix:
        return []
    return conn.execute(
        "SELECT * FROM contacts WHERE callsign LIKE ? "
        "ORDER BY date DESC, utc DESC LIMIT 10",
        (f"{prefix.upper()}%",)
    ).fetchall()


def _best_autofill(rows: list[sqlite3.Row], exact: str) -> sqlite3.Row | None:
    """
    From a list of previous contacts, return the best autofill candidate.
    Exact callsign match wins; otherwise most recent.
    """
    if not rows:
        return None
    exact_upper = exact.upper()
    for r in rows:
        if r["callsign"] == exact_upper:
            return r
    return rows[0]


def _post_to_dashboard(contact: dict) -> None:
    """Post a single contact to the ham shack dashboard API. Silently fails if unavailable."""
    import urllib.request, urllib.error, json
    from pathlib import Path

    conf_path = Path.home() / ".shackradlog/dashboard.conf"
    if not conf_path.exists():
        return

    conf = {}
    for line in conf_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()

    url   = conf.get("dashboard_url")
    token = conf.get("dashboard_token")
    if not url or not token:
        return

    # Build ADIF record string from contact dict
    def af(tag, val):
        if val:
            v = str(val)
            return f"<{tag}:{len(v)}>{v}"
        return ""

    date = contact.get("date", "").replace("-", "")
    time = contact.get("utc", "").replace(":", "")[:4]

    adif = (
        af("CALL",      contact.get("callsign")) +
        af("QSO_DATE",  date) +
        af("TIME_ON",   time) +
        af("BAND",      contact.get("band")) +
        af("FREQ",      contact.get("freq")) +
        af("MODE",      contact.get("mode")) +
        af("RST_SENT",  contact.get("rst_sent")) +
        af("RST_RCVD",  contact.get("rst_rcvd")) +
        af("GRIDSQUARE",contact.get("qth_grid")) +
        af("QTH",       contact.get("qth_display")) +
        af("COMMENT",   contact.get("notes")) +
        "<EOR>"
    )

    payload = json.dumps({"adif": adif}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=3, context=__import__('ssl')._create_unverified_context())
    except Exception:
        open(str(Path.home() / 'dashboard_debug.log'), 'a').write(__import__('traceback').format_exc() + '\n')

def quick_log_form(stdscr, conn: sqlite3.Connection,
                   rows: list) -> dict | None:
    """
    Compact quick-log overlay — 5 fields, callsign autofill from history.

    Fields: Callsign → Freq → Mode → RST Sent → RST Rcvd
    Tab / Enter on callsign field accepts autofill suggestion.
    RST fields default to 59 (Tab/Enter accepts default without typing).
    Ctrl+S or Enter on last field saves immediately.
    ESC cancels.
    """
    max_y, max_x = stdscr.getmaxyx()

    # Layout
    QFIELDS = [
        ("callsign", "Callsign",  "e.g. W1AW  —  Tab to accept autofill"),
        ("freq",     "Freq (MHz)","e.g. 14.225  —  band auto-detected"),
        ("mode",     "Mode",      "SSB / CW / FT8 / FM / ..."),
        ("rst_sent", "RST Sent",  "default: 59"),
        ("rst_rcvd", "RST Rcvd",  "default: 59"),
    ]
    DEFAULTS = {"rst_sent": "59", "rst_rcvd": "59"}

    form_h  = len(QFIELDS) + 9
    form_w  = min(56, max_x - 4)
    fy      = max(0, (max_y - form_h) // 2)
    fx      = max(0, (max_x - form_w) // 2)
    label_w = 12
    input_w = form_w - label_w - 6

    now       = datetime.datetime.now(datetime.timezone.utc)
    auto_date = now.strftime("%Y-%m-%d")
    auto_utc  = now.strftime("%H:%M")

    values: dict[str, str] = {}
    autofill: sqlite3.Row | None = None
    idx = 0

    def draw(suggest: str = ""):
        stdscr.clear()
        draw_table_screen(stdscr, rows)
        draw_box(stdscr, fy, fx, form_h, form_w, fill=True)

        title = " QUICK LOG "
        safe_add(stdscr, fy, fx + (form_w - len(title)) // 2,
                 title, cp("title", bold=True))
        safe_add(stdscr, fy+1, fx+2,
                 f"  {auto_date}  {auto_utc} UTC",
                 cp("field"))
        safe_add(stdscr, fy+2, fx+2, "─" * (form_w - 4), cp("border"))

        for i, (key, label, _) in enumerate(QFIELDS):
            row_y   = fy + 3 + i
            is_cur  = (i == idx)
            lab_attr = cp("highlight", bold=True) if is_cur else cp("field")
            safe_add(stdscr, row_y, fx+2, f"  {label:<{label_w}}", lab_attr)
            val = values.get(key, "")
            if not val and key in DEFAULTS and not is_cur:
                # Show default in dim style
                safe_add(stdscr, row_y, fx+2+label_w+2,
                         DEFAULTS[key][:input_w].ljust(input_w), cp("dim"))
            else:
                safe_add(stdscr, row_y, fx+2+label_w+2,
                         val[:input_w].ljust(input_w),
                         cp("input") if is_cur else cp("odd"))

        # Autofill suggestion bar
        hint_y = fy + 3 + len(QFIELDS) + 1
        if suggest:
            sug_str = f" ↹ Tab: {suggest}"[:form_w - 4]
            safe_add(stdscr, hint_y, fx+2,
                     sug_str.ljust(form_w - 4), cp("key", bold=True))
        else:
            safe_add(stdscr, hint_y, fx+2, " " * (form_w - 4), cp("border"))

        cur_hint = QFIELDS[idx][2]
        safe_add(stdscr, hint_y+1, fx+3, cur_hint[:form_w-4], cp("dim"))
        safe_add(stdscr, hint_y+2, fx+2,
                 " ↑↓=navigate  ENTER=next  ^S=SAVE  ESC=cancel ".ljust(form_w-4),
                 cp("status"))

        # Live band preview on freq field
        if QFIELDS[idx][0] == "freq":
            cur_val = values.get("freq", "")
            norm    = normalize_freq(cur_val)
            band    = freq_to_band(cur_val)
            preview = f"→ {norm} MHz" if norm and norm != cur_val else ""
            if band:
                preview += f"  [{band}]"
            if preview:
                safe_add(stdscr, hint_y+2, fx+3, preview[:form_w-4], cp("key", bold=True))

        stdscr.refresh()

    while True:
        key_name = QFIELDS[idx][0]

        # Build autofill suggestion for callsign field
        suggest = ""
        if key_name == "callsign":
            prefix  = values.get("callsign", "")
            history = _callsign_history(conn, prefix)
            autofill = dict(_best_autofill(history, prefix)) if _best_autofill(history, prefix) else None
            if autofill and autofill["callsign"] != prefix.upper():
                suggest = (f"{autofill['callsign']}  "
                           f"{autofill['freq']} {autofill['band']}  "
                           f"{autofill['mode']}  "
                           f"{autofill.get('qth_display') or autofill.get('qth') or ''}"
                           ).strip()
            elif autofill and autofill["callsign"] == prefix.upper():
                # Exact match — show what will be filled
                suggest = (f"prev: {autofill['freq']} {autofill['band']}  "
                           f"{autofill['mode']}  "
                           f"{autofill.get('qth_display') or autofill.get('qth') or ''}"
                           ).strip()

        draw(suggest)

        # Input
        row_y   = fy + 3 + idx
        prefill = values.get(key_name, "")
        curses.curs_set(1)
        buf    = list(prefill)
        pos    = len(buf)
        action = _ACT_NEXT  # safe default — any unhandled key advances

        while True:
            disp = "".join(buf)[:input_w].ljust(input_w)
            safe_add(stdscr, row_y, fx+2+label_w+2, disp, cp("input"))
            try:
                stdscr.move(row_y, fx+2+label_w+2+min(pos, input_w-1))
            except curses.error:
                pass
            stdscr.refresh()
            ch = stdscr.getch()

            if ch == 9 and key_name == "callsign" and autofill:
                # Tab — accept autofill, stay on callsign field to confirm
                values["callsign"] = autofill["callsign"]
                values["freq"]     = autofill["freq"]     or ""
                values["mode"]     = autofill["mode"]     or ""
                buf = list(autofill["callsign"])
                pos = len(buf)
                action = _ACT_NEXT  # will redraw; idx stays same until Enter
                break

            elif ch in (curses.KEY_ENTER, 10, 13):
                # Enter on RST fields with empty input → accept default
                if not buf and key_name in DEFAULTS:
                    values[key_name] = DEFAULTS[key_name]
                else:
                    val = "".join(buf).strip()
                    if key_name in ("callsign", "mode"):
                        val = val.upper()
                    values[key_name] = val
                action = _ACT_NEXT
                break

            elif ch == 19:  # Ctrl+S
                val = "".join(buf).strip()
                if key_name in ("callsign", "mode"):
                    val = val.upper()
                values[key_name] = val
                action = _ACT_SAVE
                break

            elif ch == 27:
                curses.curs_set(0)
                return None

            elif ch == curses.KEY_UP:
                val = "".join(buf).strip()
                if key_name in ("callsign", "mode"): val = val.upper()
                values[key_name] = val
                action = _ACT_PREV
                break

            elif ch == curses.KEY_DOWN:
                val = "".join(buf).strip()
                if key_name in ("callsign", "mode"): val = val.upper()
                values[key_name] = val
                action = _ACT_NEXT
                break

            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if pos > 0: buf.pop(pos-1); pos -= 1
            elif ch == curses.KEY_DC:
                if pos < len(buf): buf.pop(pos)
            elif ch == curses.KEY_LEFT:
                pos = max(0, pos-1)
            elif ch == curses.KEY_RIGHT:
                pos = min(len(buf), pos+1)
            elif ch == curses.KEY_HOME:
                pos = 0
            elif ch == curses.KEY_END:
                pos = len(buf)
            elif 32 <= ch <= 126 and len(buf) < input_w - 1:
                buf.insert(pos, chr(ch)); pos += 1

                # Live autofill update on callsign field
                if key_name == "callsign":
                    cur_cs  = "".join(buf).upper()
                    history = _callsign_history(conn, cur_cs)
                    _raw = _best_autofill(history, cur_cs)
                    autofill = dict(_raw) if _raw else None
                    if autofill and autofill["callsign"] != cur_cs:
                        sug = (f" ↹ Tab: {autofill['callsign']}  "
                               f"{autofill['freq']} {autofill['band']}  "
                               f"{autofill['mode']}")[:form_w-4]
                    elif autofill:
                        sug = (f" ↹ Tab: prev {autofill['freq']} "
                               f"{autofill['band']}  {autofill['mode']}")[:form_w-4]
                    else:
                        sug = ""
                    hint_y = fy + 3 + len(QFIELDS) + 1
                    safe_add(stdscr, hint_y, fx+2,
                             sug.ljust(form_w-4) if sug else " "*(form_w-4),
                             cp("key", bold=True) if sug else cp("border"))
                    stdscr.refresh()

        curses.curs_set(0)

        if action == _ACT_CANCEL:
            return None

        elif action == _ACT_SAVE:
            # Fill any remaining untouched fields with defaults
            for k, *_ in QFIELDS:
                if k not in values or not values[k]:
                    values[k] = DEFAULTS.get(k, "")
                    if k in ("callsign", "mode"):
                        values[k] = values[k].upper()
            # Carry over QTH/power/notes from autofill if available
            if autofill:
                if not values.get("qth"):
                    values["qth"] = autofill.get("qth") or autofill.get("qth_raw") or ""
                if not values.get("power"):
                    values["power"] = autofill["power"] or ""
            values.setdefault("qth",   "")
            values.setdefault("power", "")
            values.setdefault("notes", "")
            return {"date": auto_date, "utc": auto_utc, **values}

        elif action == _ACT_PREV:
            idx = max(0, idx - 1)

        else:  # _ACT_NEXT
            if idx < len(QFIELDS) - 1:
                idx += 1
            else:
                # Last field + Enter = save
                for k, *_ in QFIELDS:
                    if k not in values or not values[k]:
                        values[k] = DEFAULTS.get(k, "")
                        if k in ("callsign", "mode"):
                            values[k] = values[k].upper()
                if autofill:
                    if not values.get("qth"):
                        values["qth"] = autofill.get("qth") or autofill.get("qth_raw") or ""
                    if not values.get("power"):
                        values["power"] = autofill["power"] or ""
                values.setdefault("qth",   "")
                values.setdefault("power", "")
                values.setdefault("notes", "")
                return {"date": auto_date, "utc": auto_utc, **values}


def _maybe_pick_location(stdscr, values: dict, callsign: str) -> dict:
    """
    If the QTH resolves to an ambiguous city, show the picker and update
    values["qth"] with a disambiguated value. Returns updated values dict.
    """
    qth_raw = values.get("qth", "").strip()
    if not qth_raw:
        return values
    loc = parse_location(qth_raw, callsign)
    if loc.get("qth_ambiguous") and loc.get("qth_candidates"):
        chosen = _location_picker(stdscr, loc["qth_candidates"])
        if chosen:
            # Rewrite qth to "City, State" so next parse_location is unambiguous
            admin = chosen.get("admin1_code") or ""
            if admin:
                values["qth"] = f"{chosen['city']}, {admin}"
            else:
                values["qth"] = f"{chosen['city']}, {chosen['country']}"
    return values


def contact_form(stdscr, rows: list, edit_row: sqlite3.Row | None = None) -> dict | None:
    max_y, max_x = stdscr.getmaxyx()
    form_h = len(FORM_FIELDS) + 10
    form_w = min(66, max_x - 4)
    fy = max(0, (max_y - form_h) // 2)
    fx = max(0, (max_x - form_w) // 2)
    label_w = 18
    input_w = form_w - label_w - 6

    now = datetime.datetime.now(datetime.timezone.utc)
    auto_date = edit_row["date"] if edit_row else now.strftime("%Y-%m-%d")
    auto_utc  = edit_row["utc"]  if edit_row else now.strftime("%H:%M")

    prefills = {k: (edit_row[k] or "" if edit_row else "") for k, *_ in FORM_FIELDS}
    values: dict[str, str] = {}
    idx = 0

    while True:
        _draw_form(stdscr, rows, fy, fx, form_h, form_w, label_w, input_w,
                   auto_date, auto_utc, values, prefills, idx, edit_row)

        row_y = fy + 3 + idx
        raw, action = _form_input(
            stdscr, row_y, fx+2+label_w+2, input_w,
            prefill=values.get(FORM_FIELDS[idx][0], prefills.get(FORM_FIELDS[idx][0], ""))
        )

        # Normalise the value
        key = FORM_FIELDS[idx][0]
        if key in ("callsign", "mode"):
            raw = raw.upper()
        values[key] = raw

        if action == _ACT_CANCEL:
            return None
        elif action == _ACT_SAVE:
            # Require callsign before saving
            cs_val = values.get("callsign", prefills.get("callsign", "")).strip()
            if not cs_val or not any(c.isdigit() for c in cs_val):
                flash(stdscr, " ⚠  Callsign is required (must contain a digit) ", "warn")
                idx = FORM_FIELDS.index(next(f for f in FORM_FIELDS if f[0] == "callsign"))
                continue
            # Fill any untouched fields with their prefills then save
            for k, *_ in FORM_FIELDS:
                if k not in values:
                    values[k] = prefills.get(k, "")
                    if k in ("callsign", "mode"):
                        values[k] = values[k].upper()
            values = _maybe_pick_location(stdscr, values,
                                          values.get("callsign", ""))
            return {"date": auto_date, "utc": auto_utc, **values}
        elif action == _ACT_PREV:
            idx = max(0, idx - 1)
        else:  # _ACT_NEXT
            # Require callsign before leaving the callsign field
            if key == "callsign":
                cs_val = raw.strip()
                if not cs_val or not any(c.isdigit() for c in cs_val):
                    flash(stdscr, " ⚠  Enter a callsign first (must contain a digit) ", "warn")
                    continue
            if idx < len(FORM_FIELDS) - 1:
                idx += 1
            else:
                # Last field + Enter = implicit save
                for k, *_ in FORM_FIELDS:
                    if k not in values:
                        values[k] = prefills.get(k, "")
                        if k in ("callsign", "mode"):
                            values[k] = values[k].upper()
                values = _maybe_pick_location(stdscr, values,
                                              values.get("callsign", ""))
                return {"date": auto_date, "utc": auto_utc, **values}

# ── Search / filter form ──────────────────────────────────────────────────────
SEARCH_FIELDS: list[tuple[str, str]] = [
    ("callsign",  "Callsign contains"),
    ("mode",      "Mode contains"),
    ("band",      "Band (exact, e.g. 20m)"),
    ("freq",      "Frequency contains"),
    ("qth_country","Country contains"),
    ("qth_state", "State (2-letter, e.g. AR)"),
    ("date_from", "Date from (YYYY-MM-DD)"),
    ("date_to",   "Date to   (YYYY-MM-DD)"),
]

def search_form(stdscr, current: dict) -> dict | None:
    max_y, max_x = stdscr.getmaxyx()
    form_h = len(SEARCH_FIELDS) + 7
    form_w = min(58, max_x - 4)
    fy = max(0, (max_y - form_h) // 2)
    fx = max(0, (max_x - form_w) // 2)
    label_w = 24
    input_w = form_w - label_w - 5
    idx = 0
    values = dict(current)

    while True:
        stdscr.clear()
        draw_box(stdscr, fy, fx, form_h, form_w, fill=True)
        safe_add(stdscr, fy, fx + (form_w - 10) // 2, " SEARCH / FILTER ", cp("title", bold=True))

        for i, (key, label) in enumerate(SEARCH_FIELDS):
            row_y = fy + 2 + i
            is_cur = (i == idx)
            lab_attr = cp("highlight", bold=True) if is_cur else cp("field")
            safe_add(stdscr, row_y, fx+2, f"  {label:<{label_w}}", lab_attr)
            val = values.get(key, "")
            inp_attr = cp("input") if is_cur else cp("odd")
            safe_add(stdscr, row_y, fx+2+label_w+1, val[:input_w].ljust(input_w), inp_attr)

        hint_y = fy + 2 + len(SEARCH_FIELDS) + 1
        safe_add(stdscr, hint_y,   fx+2, " ENTER=next  ESC=apply  C=clear all ".ljust(form_w-4), cp("status"))
        stdscr.refresh()

        # Handle nav outside get_input for C key
        curses.curs_set(1)
        row_y = fy + 2 + idx
        inp_x = fx + 2 + label_w + 1
        buf = list(values.get(SEARCH_FIELDS[idx][0], ""))
        pos = len(buf)

        while True:
            display = ("".join(buf))[:input_w].ljust(input_w)
            safe_add(stdscr, row_y, inp_x, display, cp("input"))
            try:
                stdscr.move(row_y, min(inp_x + pos, inp_x + input_w - 1))
            except curses.error:
                pass
            stdscr.refresh()
            ch = stdscr.getch()

            if ch in (curses.KEY_ENTER, 10, 13):
                values[SEARCH_FIELDS[idx][0]] = "".join(buf).strip()
                idx = (idx + 1) % len(SEARCH_FIELDS)
                break
            elif ch == 27:
                values[SEARCH_FIELDS[idx][0]] = "".join(buf).strip()
                curses.curs_set(0)
                return {k: v for k, v in values.items() if v}
            elif ch in (ord('c'), ord('C')):
                values = {}
                break
            elif ch == curses.KEY_UP:
                values[SEARCH_FIELDS[idx][0]] = "".join(buf).strip()
                idx = (idx - 1) % len(SEARCH_FIELDS)
                break
            elif ch == curses.KEY_DOWN:
                values[SEARCH_FIELDS[idx][0]] = "".join(buf).strip()
                idx = (idx + 1) % len(SEARCH_FIELDS)
                break
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if pos > 0: buf.pop(pos-1); pos -= 1
            elif ch == curses.KEY_DC:
                if pos < len(buf): buf.pop(pos)
            elif ch == curses.KEY_LEFT:  pos = max(0, pos-1)
            elif ch == curses.KEY_RIGHT: pos = min(len(buf), pos+1)
            elif 32 <= ch <= 126 and len(buf) < input_w - 1:
                buf.insert(pos, chr(ch)); pos += 1

        curses.curs_set(0)

# ── Path input (single-line, full path editable) ──────────────────────────────
def pick_path(stdscr, prompt: str, default: str) -> str | None:
    """Show a single-line path editor. Returns path string or None if cancelled."""
    max_y, max_x = stdscr.getmaxyx()
    bw = min(max_x - 4, 80)
    bh = 5
    by = (max_y - bh) // 2
    bx = (max_x - bw) // 2

    stdscr.clear()
    draw_box(stdscr, by, bx, bh, bw, fill=True)
    safe_add(stdscr, by,   bx + (bw - len(prompt) - 2) // 2, f" {prompt} ", cp("title", bold=True))
    safe_add(stdscr, by+1, bx+2, "Edit path below. ENTER=confirm  ESC=cancel", cp("dim"))
    safe_add(stdscr, by+3, bx+2, "Path: ", cp("field"))
    stdscr.refresh()

    result = get_input(stdscr, by+3, bx+8, bw - 10, prefill=default)
    return result  # None if ESC


# ── Export dialog ─────────────────────────────────────────────────────────────
def export_dialog(stdscr, conn: sqlite3.Connection, filters: dict):
    rows = db_fetch(conn, filters)
    if not rows:
        flash(stdscr, " No contacts match current filter! ", "highlight")
        return

    fmt_choices = ["ADIF (.adi)", "CSV (.csv)", "JSON (.json)", "All three", "Cancel"]
    sel = 0
    dw, dh = 46, len(fmt_choices) + 6
    max_y, max_x = stdscr.getmaxyx()
    dy = (max_y - dh) // 2
    dx = (max_x - dw) // 2

    while True:
        stdscr.clear()
        draw_box(stdscr, dy, dx, dh, dw, fill=True)
        safe_add(stdscr, dy, dx + (dw-14)//2, " EXPORT LOG ", cp("title", bold=True))
        safe_add(stdscr, dy+1, dx+3, f"  {len(rows)} contact(s)  |  filter {'ON' if filters else 'OFF'}", cp("field"))
        safe_add(stdscr, dy+2, dx+3, "─" * (dw-6), cp("border"))

        for i, ch in enumerate(fmt_choices):
            attr = cp("highlight", bold=True) if i == sel else cp("odd")
            safe_add(stdscr, dy+4+i, dx+4, f"  {ch:<36}  ", attr)

        safe_add(stdscr, dy+dh-2, dx+3,
                 " ↑↓=select  ENTER=choose  ESC=cancel ", cp("status"))
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == curses.KEY_UP:     sel = (sel-1) % len(fmt_choices)
        elif ch == curses.KEY_DOWN: sel = (sel+1) % len(fmt_choices)
        elif ch in (curses.KEY_ENTER, 10, 13): break
        elif ch == 27: return

    if sel == len(fmt_choices) - 1:   # Cancel
        return

    # Ask user where to save
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = str(Path.home() / "Desktop")
    if not Path(base).exists():
        base = str(DB_DIR)

    # Build list of (ext, label) pairs based on selection
    exports_needed: list[tuple[str, str]] = []
    if sel in (0, 3): exports_needed.append(("adi",  "ADIF"))
    if sel in (1, 3): exports_needed.append(("csv",  "CSV"))
    if sel in (2, 3): exports_needed.append(("json", "JSON"))

    # Let user confirm/edit the save directory once
    chosen_dir = pick_path(stdscr, "Save to directory", base)
    if chosen_dir is None:
        return
    chosen_dir = Path(chosen_dir).expanduser()
    try:
        chosen_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        flash(stdscr, f" Could not create directory: {e} ", "highlight")
        return

    msgs: list[str] = []
    for ext, label in exports_needed:
        p = chosen_dir / f"shackradlog_{ts}.{ext}"
        if ext == "adi":  export_adif(rows, p)
        elif ext == "csv": export_csv(rows, p)
        elif ext == "json": export_json(rows, p)
        msgs.append(f"{label:5} → {p}")

    # Result screen
    rw = min(max_x - 4, max(60, max(len(m) for m in msgs) + 6))
    rh = len(msgs) + 6
    ry = (max_y - rh) // 2
    rx = (max_x - rw) // 2
    stdscr.clear()
    draw_box(stdscr, ry, rx, rh, rw, fill=True)
    safe_add(stdscr, ry, rx + (rw-18)//2, " EXPORT COMPLETE ", cp("status", bold=True))
    for i, m in enumerate(msgs):
        safe_add(stdscr, ry+2+i, rx+3, m[:rw-4], cp("key"))
    safe_add(stdscr, ry+rh-2, rx+3, " Press any key… ", cp("field"))
    stdscr.refresh()
    stdscr.getch()


def import_dialog(stdscr, conn: sqlite3.Connection) -> int:
    """
    Import contacts from ADIF, CSV, or JSON file.
    Returns number of contacts imported.
    """
    fmt_choices = ["ADIF (.adi)", "CSV (.csv)", "JSON (.json)", "Cancel"]
    sel = 0
    dw, dh = 46, len(fmt_choices) + 6
    max_y, max_x = stdscr.getmaxyx()
    dy = (max_y - dh) // 2
    dx = (max_x - dw) // 2

    while True:
        stdscr.clear()
        draw_box(stdscr, dy, dx, dh, dw, fill=True)
        safe_add(stdscr, dy, dx + (dw-14)//2, " IMPORT LOG ", cp("title", bold=True))
        safe_add(stdscr, dy+1, dx+3, "  Select file format to import", cp("field"))
        safe_add(stdscr, dy+2, dx+3, "─" * (dw-6), cp("border"))

        for i, ch in enumerate(fmt_choices):
            attr = cp("highlight", bold=True) if i == sel else cp("odd")
            safe_add(stdscr, dy+4+i, dx+4, f"  {ch:<36}  ", attr)

        safe_add(stdscr, dy+dh-2, dx+3,
                 " ↑↓=select  ENTER=choose  ESC=cancel ", cp("status"))
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == curses.KEY_UP:     sel = (sel-1) % len(fmt_choices)
        elif ch == curses.KEY_DOWN: sel = (sel+1) % len(fmt_choices)
        elif ch in (curses.KEY_ENTER, 10, 13): break
        elif ch == 27: return 0

    if sel == len(fmt_choices) - 1:   # Cancel
        return 0

    # Map selection to extension
    ext_map = {0: "adi", 1: "csv", 2: "json"}
    ext = ext_map[sel]
    
    # Default search path
    base = str(Path.home() / "Desktop")
    if not Path(base).exists():
        base = str(Path.home())

    # Ask for file path
    filepath = pick_path(stdscr, f"Import {ext.upper()} file", base)
    if filepath is None:
        return 0
    
    filepath = Path(filepath).expanduser()
    if not filepath.exists():
        flash(stdscr, f" File not found: {filepath} ", "warn")
        return 0

    # Import based on format
    try:
        if ext == "adi":
            contacts = import_adif(filepath)
        elif ext == "csv":
            contacts = import_csv(filepath)
        elif ext == "json":
            contacts = import_json(filepath)
        else:
            contacts = []
    except Exception as e:
        flash(stdscr, f" Import error: {e} ", "warn")
        return 0

    if not contacts:
        flash(stdscr, " No contacts found in file ", "warn")
        return 0

    # Ask about duplicates
    dup_choices = ["Skip duplicates", "Import all (may create duplicates)", "Cancel"]
    sel = 0
    dh = len(dup_choices) + 6
    dy = (max_y - dh) // 2

    while True:
        stdscr.clear()
        draw_box(stdscr, dy, dx, dh, dw, fill=True)
        safe_add(stdscr, dy, dx + (dw-20)//2, " DUPLICATE HANDLING ", cp("title", bold=True))
        safe_add(stdscr, dy+1, dx+3, f"  Found {len(contacts)} contact(s) to import", cp("field"))
        safe_add(stdscr, dy+2, dx+3, "─" * (dw-6), cp("border"))

        for i, ch in enumerate(dup_choices):
            attr = cp("highlight", bold=True) if i == sel else cp("odd")
            safe_add(stdscr, dy+4+i, dx+4, f"  {ch:<36}  ", attr)

        safe_add(stdscr, dy+dh-2, dx+3,
                 " ↑↓=select  ENTER=choose  ESC=cancel ", cp("status"))
        stdscr.refresh()
        ch = stdscr.getch()
        if ch == curses.KEY_UP:     sel = (sel-1) % len(dup_choices)
        elif ch == curses.KEY_DOWN: sel = (sel+1) % len(dup_choices)
        elif ch in (curses.KEY_ENTER, 10, 13): break
        elif ch == 27: return 0

    if sel == 2:  # Cancel
        return 0

    skip_dups = (sel == 0)

    # Import contacts
    imported = 0
    skipped = 0
    
    for contact in contacts:
        # Check for duplicate if requested
        if skip_dups and check_duplicate(conn, contact):
            skipped += 1
            continue
        
        # Insert the contact
        try:
            db_insert(conn, contact)
            imported += 1
        except Exception:
            skipped += 1

    # Result screen
    msgs = [
        f"Imported: {imported} contact(s)",
        f"Skipped:  {skipped} (duplicates or errors)",
        f"From:     {filepath.name}",
    ]
    rw = min(max_x - 4, max(50, max(len(m) for m in msgs) + 6))
    rh = len(msgs) + 6
    ry = (max_y - rh) // 2
    rx = (max_x - rw) // 2
    stdscr.clear()
    draw_box(stdscr, ry, rx, rh, rw, fill=True)
    safe_add(stdscr, ry, rx + (rw-18)//2, " IMPORT COMPLETE ", cp("status", bold=True))
    for i, m in enumerate(msgs):
        safe_add(stdscr, ry+2+i, rx+3, m[:rw-4], cp("key"))
    safe_add(stdscr, ry+rh-2, rx+3, " Press any key… ", cp("field"))
    stdscr.refresh()
    stdscr.getch()
    
    return imported


# ── Stats screen ──────────────────────────────────────────────────────────────
def stats_screen(stdscr, conn: sqlite3.Connection):
    s = db_stats(conn)
    if not s:
        flash(stdscr, " No contacts logged yet! ", "highlight")
        return

    max_y, max_x = stdscr.getmaxyx()
    sw = min(70, max_x - 4)

    # Build all content lines up front as (text, color) tuples
    # so we know exactly how tall the box needs to be.
    lines: list[tuple[str, str]] = []

    def add(text, color="odd"):
        lines.append((text, color))

    add(f"{'Total QSOs':<22}{s['total']}", "odd")
    add(f"{'Unique callsigns':<22}{s['unique_calls']}", "odd")
    add(f"{'First QSO':<22}{s['first_qso']}", "odd")
    add(f"{'Last QSO':<22}{s['last_qso']}", "odd")
    if s.get("unresolved"):
        add(f"{'⚠ Unresolved locations':<22}{s['unresolved']}", "warn")
    add("", "odd")

    bar_w = sw - 32   # characters available for bars

    def scaled_bar(cnt, max_cnt):
        if not max_cnt:
            return ""
        return "█" * max(1, round(cnt / max_cnt * bar_w))

    add("── Modes " + "─" * (sw - 14), "header")
    max_mode = s["modes"][0][1] if s["modes"] else 1
    for mode, cnt in s["modes"]:
        bar = scaled_bar(cnt, max_mode)
        add(f"  {mode:<10} {cnt:>5}  {bar}", "odd")
    add("", "odd")
    add("── Bands " + "─" * (sw - 14), "header")
    max_band = s["bands"][0][1] if s["bands"] else 1
    for band, cnt in s["bands"]:
        bar = scaled_bar(cnt, max_band)
        add(f"  {band:<10} {cnt:>5}  {bar}", "even")
    add("", "odd")
    add("── Countries " + "─" * (sw - 18), "header")
    max_ctry = s["top_countries"][0][1] if s.get("top_countries") else 1
    for country, cnt in s.get("top_countries", []):
        bar = scaled_bar(cnt, max_ctry)
        add(f"  {country:<20} {cnt:>5}  {bar}", "odd")
    add("", "odd")
    add("── Top Callsigns " + "─" * (sw - 22), "header")
    for call, cnt in s["top_calls"]:
        add(f"  {call:<14} {cnt} QSOs", "odd")

    # Box height = content + top border + title + blank + bottom border + hint
    content_h = len(lines)
    box_h     = content_h + 4          # title row + blank + content + hint
    visible_h = min(box_h, max_y - 2)  # clamp to terminal
    sx        = (max_x - sw) // 2
    sy        = (max_y - visible_h) // 2
    viewport  = visible_h - 4          # lines visible at once (minus title+hint)
    offset    = 0                       # scroll offset into lines[]

    while True:
        stdscr.clear()
        draw_box(stdscr, sy, sx, visible_h, sw, fill=True)
        safe_add(stdscr, sy, sx + (sw - 15) // 2,
                 " LOGBOOK STATS ", cp("title", bold=True))

        # Render visible slice of lines
        for i, (text, color) in enumerate(lines[offset: offset + viewport]):
            safe_add(stdscr, sy + 2 + i, sx + 3, text[:sw - 4], cp(color))

        # Scroll indicators
        hint = " ↑↓=scroll  any other key=return "
        if content_h <= viewport:
            hint = " Any key to return "
        safe_add(stdscr, sy + visible_h - 2, sx + 3,
                 hint.ljust(sw - 6), cp("status"))
        if offset > 0:
            safe_add(stdscr, sy + 1, sx + sw - 5, " ▲ ", cp("key", bold=True))
        if offset + viewport < content_h:
            safe_add(stdscr, sy + visible_h - 3, sx + sw - 5, " ▼ ", cp("key", bold=True))

        stdscr.refresh()
        ch = stdscr.getch()

        if ch == curses.KEY_UP:
            offset = max(0, offset - 1)
        elif ch == curses.KEY_DOWN:
            offset = min(max(0, content_h - viewport), offset + 1)
        elif ch == curses.KEY_PPAGE:
            offset = max(0, offset - viewport)
        elif ch == curses.KEY_NPAGE:
            offset = min(max(0, content_h - viewport), offset + viewport)
        else:
            break

def _unresolved_flash(stdscr, saved_row: sqlite3.Row | None,
                      contact: dict) -> None:
    """
    Show the 'location not recognized' warning if applicable.
    Call after any insert or update when the user entered a QTH value.
    """
    if (saved_row and not saved_row["qth_resolved"]
            and (contact.get("qth") or "").strip()):
        flash(stdscr,
              " ⚠  Location not recognized — stored as free text. Edit to fix. ",
              "warn")


# ── Flash message ─────────────────────────────────────────────────────────────
def flash(stdscr, msg: str, color: str = "status", wait: bool = True):
    max_y, max_x = stdscr.getmaxyx()
    x = max(0, (max_x - len(msg)) // 2)
    safe_add(stdscr, max_y-2, x, msg, cp(color, bold=True))
    stdscr.refresh()
    if wait:
        stdscr.getch()

# ── Table columns ─────────────────────────────────────────────────────────────
COLS: list[tuple[str, str, int]] = [
    # (key, header, min_width)
    ("date",        "Date",     10),
    ("utc",         "UTC",       5),
    ("callsign",    "Callsign",  9),
    ("freq",        "Freq",      7),
    ("band",        "Band",      7),
    ("mode",        "Mode",      6),
    ("rst_sent",    "RST↑",      5),
    ("rst_rcvd",    "RST↓",      5),
    ("qth_display", "Location", 28),
    ("power",       "PWR",       5),
    ("notes",       "Notes",     0),   # 0 = fills remainder
]

def col_widths(max_x: int) -> list[int]:
    """
    Return a list of column widths that fit within max_x characters.
    Each column occupies its width + 1 separator space.
    Optional columns are collapsed to 0 on narrow terminals (zero-width cols
    are skipped by draw_table_screen).  If we still can't fit after dropping
    all optional cols, the Location column is shrunk proportionally.
    """
    widths = [w for _, _, w in COLS[:-1]]  # all fixed cols except notes

    # Drop columns in priority order: power(9), RST↓(7), RST↑(6)
    OPTIONAL_INDICES = [9, 7, 6]
    for idx in OPTIONAL_INDICES:
        used = sum(w + 1 for w in widths if w > 0)
        if used + 5 <= max_x:   # 5 = notes minimum
            break
        widths[idx] = 0

    # If we still overflow, shrink the Location column (index 8, min 10)
    used = sum(w + 1 for w in widths if w > 0)
    if used + 5 > max_x:
        loc_idx = 8   # qth_display
        excess  = (used + 5) - max_x
        widths[loc_idx] = max(10, widths[loc_idx] - excess)

    used = sum(w + 1 for w in widths if w > 0)
    last = max(5, max_x - used)
    return widths + [last]

def draw_table_screen(stdscr, rows: list,
                      offset: int = 0, selected: int = 0,
                      filters: dict | None = None,
                      worked_counts: dict | None = None):
    max_y, max_x = stdscr.getmaxyx()
    widths = col_widths(max_x)
    table_h = max_y - 5   # title + keybar + header + statusbar + filter indicator

    # Title
    my_call = get_my_callsigns()
    if my_call:
        title = f"── SHACKRADLOG  {my_call}  Ham Radio Contact Logger  ──"
    else:
        title = "── SHACKRADLOG  Ham Radio Contact Logger  ──"
    safe_add(stdscr, 0, 0, f" {title}".ljust(max_x), cp("title", bold=True))
    count = f" {len(rows)} QSO{'s' if len(rows)!=1 else ''} "
    safe_add(stdscr, 0, max_x - len(count) - 1, count, cp("title", bold=True))

    # Key bar — fill entire row first, then write labels over it
    safe_add(stdscr, 1, 0, " " * max_x, cp("border"))
    keys = [("N","New"),("L","Quick"),("E","Edit"),("D","Del"),
            ("S","Search"),("I","Import"),("X","Export"),("F","Freqs"),("/","Stats"),("Q","Quit")]
    kx = 1
    for k, lbl in keys:
        if kx + len(lbl) + 6 >= max_x:
            break
        safe_add(stdscr, 1, kx, f"[{k}]", cp("key", bold=True))
        safe_add(stdscr, 1, kx+3, f"{lbl}  ", cp("border"))
        kx += len(lbl) + 6

    # Filter indicator
    filter_row = 2
    if filters:
        parts = [f"{k}={v}" for k, v in filters.items() if v]
        fstr = "  FILTER: " + "  ·  ".join(parts)
        safe_add(stdscr, filter_row, 0, fstr[:max_x].ljust(max_x), cp("highlight", bold=True))
    else:
        safe_add(stdscr, filter_row, 0, " " * max_x, cp("border"))

    # Column header — skip collapsed (width=0) columns
    hdr = "".join(h[:w].ljust(w) + " " for (_, h, _), w in zip(COLS, widths) if w > 0)
    safe_add(stdscr, 3, 0, hdr[:max_x].ljust(max_x),
             cp("header", bold=True) | curses.A_UNDERLINE)

    # Find callsign column x-offset for ×N overlay
    cs_col_x = 0
    cs_col_w  = 9
    for (key, _, _), w in zip(COLS, widths):
        if key == "callsign":
            cs_col_w = w
            break
        if w > 0:
            cs_col_x += w + 1

    # Rows — skip collapsed (width=0) columns
    for i, row in enumerate(rows[offset: offset + table_h]):
        abs_i      = offset + i
        unresolved = not row["qth_resolved"] and (row["qth"] or row["qth_raw"])
        cells = "".join(
            (row[key] or "")[:w].ljust(w) + " "
            for (key, _, _), w in zip(COLS, widths)
            if w > 0
        )
        if abs_i == selected:
            attr = cp("highlight", bold=True)
        elif unresolved:
            attr = cp("warn")
        elif i % 2 == 0:
            attr = cp("odd")
        else:
            attr = cp("even")
        safe_add(stdscr, 4 + i, 0, cells[:max_x].ljust(max_x), attr)

        # ×N worked counter — overlaid at right edge of callsign column
        if worked_counts:
            cs    = row["callsign"] or ""
            n     = worked_counts.get(cs, 1)
            if n > 1:
                badge      = f"×{n}"
                badge_x    = cs_col_x + cs_col_w - len(badge)
                badge_attr = (cp("title", bold=True) if abs_i == selected
                              else cp("key", bold=True))
                safe_add(stdscr, 4 + i, badge_x, badge, badge_attr)

    for i in range(len(rows[offset: offset + table_h]), table_h):
        safe_add(stdscr, 4 + i, 0, " " * max_x, cp("odd"))

    # Status bar
    safe_add(stdscr, max_y-1, 0,
             f"  DB: {DB_PATH}   Exports: {Path.home() / 'Desktop'}  ".ljust(max_x), cp("status"))

# ── Geo module (optional — degrades gracefully if missing) ───────────────────
try:
    import shackradlog_geo as _geo
    GEO_AVAILABLE = True
except ImportError:
    _geo = None
    GEO_AVAILABLE = False

# ── Contact detail view ───────────────────────────────────────────────────────
def detail_view(stdscr, row: sqlite3.Row, conn: sqlite3.Connection,
                all_rows: list) -> str:
    """
    Full-screen detail view for a single contact.
    Shows every field with no truncation, grouped logically.

    Returns:
        "edit"   — caller should open edit form
        "delete" — caller should confirm delete
        "close"  — just close and return to table
    """
    max_y, max_x = stdscr.getmaxyx()

    worked_count = conn.execute(
        "SELECT count(*) FROM contacts WHERE callsign = ?",
        (row["callsign"],)
    ).fetchone()[0]

    while True:
        stdscr.clear()
        draw_table_screen(stdscr, all_rows)

        bw = min(62, max_x - 4)
        bh = 20
        by = max(1, (max_y - bh) // 2)
        bx = max(1, (max_x - bw) // 2)
        iw = bw - 4

        draw_box(stdscr, by, bx, bh, bw, fill=True)

        # ── Title ─────────────────────────────────────────────────────────────
        cs    = row["callsign"] or "?"
        times = f"  ×{worked_count}" if worked_count > 1 else ""
        title = f"  {cs}{times}  —  {row['date']}  {row['utc']} UTC  "
        safe_add(stdscr, by, bx + max(1, (bw - len(title)) // 2),
                 title[:bw-2], cp("title", bold=True))

        def ry(n): return by + 1 + n

        def sep(n):
            safe_add(stdscr, ry(n), bx+1, "─" * (bw-2), cp("border"))

        def pair(n, label, value, val_color="odd"):
            safe_add(stdscr, ry(n), bx+2, f"  {label:<14}", cp("field"))
            safe_add(stdscr, ry(n), bx+2+16,
                     (str(value) if value else "—")[:iw-16], cp(val_color))

        # ── Radio ─────────────────────────────────────────────────────────────
        sep(0)
        freq_band = (f"{row['freq'] or '—'}  [{row['band']}]"
                     if row["band"] else row["freq"] or "—")
        mode_pwr  = (f"{row['mode'] or '—'}   {row['power']+' W' if row['power'] else '—'}")
        rst       = f"Sent {row['rst_sent'] or '—'}   Rcvd {row['rst_rcvd'] or '—'}"

        safe_add(stdscr, ry(1), bx+2,        "  Frequency",    cp("field"))
        safe_add(stdscr, ry(1), bx+16,        freq_band[:iw//2], cp("key", bold=True))
        safe_add(stdscr, ry(1), bx+2+iw//2,  "  Mode / Power", cp("field"))
        safe_add(stdscr, ry(1), bx+2+iw//2+16, mode_pwr[:iw//2-2], cp("key", bold=True))
        safe_add(stdscr, ry(2), bx+2,        "  RST",          cp("field"))
        safe_add(stdscr, ry(2), bx+16,        rst[:iw],         cp("odd"))

        # ── Location ──────────────────────────────────────────────────────────
        sep(3)
        loc_display = row["qth_display"] or row["qth"] or "—"
        if not row["qth_resolved"] and (row["qth"] or row["qth_raw"]):
            loc_display = f"⚠ {row['qth_raw'] or row['qth']}  (unresolved)"

        pair(4, "Location",   loc_display,  "odd")
        pair(5, "Entered as", row["qth_raw"] or row["qth"] or "—", "dim")

        grid_str = row["qth_grid"] or "—"
        cq_itu   = ""
        if row["qth_cq"]:  cq_itu += f"CQ {row['qth_cq']}"
        if row["qth_itu"]: cq_itu += f"   ITU {row['qth_itu']}"

        safe_add(stdscr, ry(6), bx+2,       "  Grid",  cp("field"))
        safe_add(stdscr, ry(6), bx+16,       grid_str, cp("key", bold=True))
        if cq_itu:
            safe_add(stdscr, ry(6), bx+2+iw//2, cq_itu, cp("dim"))

        # ── Notes ─────────────────────────────────────────────────────────────
        sep(7)
        notes = row["notes"] or ""
        if notes:
            words    = notes.split()
            lines_n: list[str] = []
            cur_line = ""
            for w in words:
                if len(cur_line) + len(w) + 1 <= iw - 18:
                    cur_line = cur_line + (" " if cur_line else "") + w
                else:
                    if cur_line: lines_n.append(cur_line)
                    cur_line = w
            if cur_line: lines_n.append(cur_line)
            for li, line in enumerate(lines_n[:3]):
                pair(8 + li, "Notes" if li == 0 else "", line, "odd")
            note_rows = min(3, len(lines_n))
        else:
            pair(8, "Notes", "—", "dim")
            note_rows = 1

        # ── Metadata ──────────────────────────────────────────────────────────
        meta_y = 8 + note_rows
        sep(meta_y)
        created  = row["created"] or "—"
        meta_str = f"Logged {created} UTC   ID #{row['id']}"
        if worked_count > 1:
            meta_str += f"   ({worked_count} QSOs with {row['callsign']})"
        safe_add(stdscr, ry(meta_y + 1), bx+3, meta_str[:iw], cp("dim"))

        # ── Action bar ────────────────────────────────────────────────────────
        sep(bh - 3)
        actions = "  [E] Edit    [D] Delete    ESC / Enter = Close  "
        safe_add(stdscr, ry(bh - 2),
                 bx + max(1, (bw - len(actions)) // 2),
                 actions[:bw-2], cp("status"))

        stdscr.refresh()
        ch = stdscr.getch()

        if ch in (ord('e'), ord('E')):
            return "edit"
        elif ch in (ord('d'), ord('D')):
            return "delete"
        elif ch in (27, curses.KEY_ENTER, 10, 13, ord('q'), ord('Q')):
            return "close"


# ── Geo database startup check ────────────────────────────────────────────────
def geo_startup_check():
    """Check if geo database needs refresh and update with progress display."""
    if not GEO_AVAILABLE:
        return
    if not _geo._needs_refresh():
        return

    # ANSI codes
    GREEN  = "\033[0;32m"
    CYAN   = "\033[0;36m"
    YELLOW = "\033[1;33m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    print(f"{BOLD}{CYAN}Updating city/location database from GeoNames...{RESET}")
    print("(This happens once a month — takes about 1-2 minutes)")
    print("Press Ctrl+C to skip.")
    print()

    _last_stage = [""]

    def progress_cb(stage, pct, speed):
        labels = {
            "download_cities": "Downloading cities",
            "download_meta":   "Downloading metadata",
            "build":           "Building database"
        }
        label = labels.get(stage, stage)

        # Stage changed — print new stage header on its own line
        if label != _last_stage[0]:
            if _last_stage[0]:
                # Finish previous progress line
                sys.stdout.write("\n")
            print(f"  {label}:")
            _last_stage[0] = label

        # Build short progress bar (30 chars)
        filled = int(pct * 30 / 100)
        bar = "#" * filled + "-" * (30 - filled)
        spd = f"{speed:4.0f} KB/s" if speed else "        "

        # Fixed-width: "    [######-------] 100.0%  1234 KB/s"  (~50 chars)
        sys.stdout.write(f"\r    [{bar}] {pct:5.1f}%  {spd}")
        sys.stdout.flush()

    try:
        ok, msg = _geo.ensure_geo_db(progress_cb)
        print()  # Finish final progress line
        print()
        if ok:
            print(f"{GREEN}✓ Location database ready.{RESET}")
        else:
            print(f"{YELLOW}⚠ {msg}{RESET}")
        print()
    except KeyboardInterrupt:
        print("\n")
        print("  Skipped — opening shackradlog now.\n")


# ══════════════════════════════════════════════════════════════════════════════
# FREQUENCIES / REPEATERS SCREEN
# ══════════════════════════════════════════════════════════════════════════════

FREQ_TYPE_LABELS = {
    "simplex":        "Simplex Frequency",
    "fm_repeater":    "FM Repeater",
    "gmrs_repeater":  "GMRS Repeater",
    "dmr_repeater":   "DMR Repeater",
    "dstar_repeater": "D-STAR Repeater",
    "fusion_repeater":"Fusion Repeater",
    "p25":            "P25",
}

SERVICE_OPTIONS = ["HAM", "GMRS", "FRS", "MURS", "CB", "Business", "Other"]
TONE_TYPES = ["None", "CTCSS", "DCS"]
BANDWIDTH_OPTIONS = ["Wide (25kHz)", "Narrow (12.5kHz)"]
POWER_OPTIONS = ["High", "Medium", "Low", "Custom"]
OFFSET_DIR_OPTIONS = ["+", "-", "Simplex"]
DMR_TIMESLOTS = ["1", "2"]
FUSION_MODES = ["Auto", "DN", "VW", "FR"]

# Define which fields are shown for each entry type
FREQ_FIELDS_BY_TYPE = {
    "simplex": [
        ("name",         "Name",          "Label for this frequency"),
        ("service",      "Service",       "HAM, GMRS, FRS, etc."),
        ("rx_freq",      "Frequency",     "e.g. 146.520"),
        ("tx_tone_type", "Tone Type",     "CTCSS, DCS, or None"),
        ("tx_tone",      "Tone",          "e.g. 141.3 or D023"),
        ("power",        "Power",         "High, Med, Low"),
        ("bandwidth",    "Bandwidth",     "Wide or Narrow"),
        ("city",         "City",          "Location"),
        ("state",        "State",         "2-letter code"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    "e.g. Local, Travel"),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "fm_repeater": [
        ("name",         "Name",          "Label for this repeater"),
        ("callsign",     "Repeater Call", "e.g. W5ANR"),
        ("service",      "Service",       "HAM, GMRS, etc."),
        ("rx_freq",      "RX Freq",       "Output freq you listen on"),
        ("tx_freq",      "TX Freq",       "Input freq (or leave blank)"),
        ("offset",       "Offset",        "e.g. -0.600 or +5.0"),
        ("offset_dir",   "Offset Dir",    "+, -, or Simplex"),
        ("tx_tone_type", "TX Tone Type",  "What you send"),
        ("tx_tone",      "TX Tone",       "e.g. 141.3 or D023"),
        ("rx_tone_type", "RX Tone Type",  "What opens squelch"),
        ("rx_tone",      "RX Tone",       "Usually same as TX"),
        ("power",        "Power",         "High, Med, Low"),
        ("bandwidth",    "Bandwidth",     "Wide or Narrow"),
        ("city",         "City",          "Repeater location"),
        ("state",        "State",         "2-letter code"),
        ("owner",        "Owner/Club",    "Who runs it"),
        ("net_schedule", "Net Schedule",  "e.g. Sun 8pm ARES"),
        ("echolink",     "EchoLink/IRLP", "Node number"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    "e.g. Local, Travel"),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "gmrs_repeater": [
        ("name",         "Name",          "Label for this repeater"),
        ("callsign",     "Repeater Call", "GMRS call"),
        ("rx_freq",      "RX Freq",       "462.xxx output"),
        ("tx_freq",      "TX Freq",       "467.xxx input"),
        ("tx_tone_type", "TX Tone Type",  "CTCSS or DCS"),
        ("tx_tone",      "TX Tone",       "e.g. 141.3"),
        ("rx_tone_type", "RX Tone Type",  "Usually same as TX"),
        ("rx_tone",      "RX Tone",       ""),
        ("power",        "Power",         "High, Med, Low"),
        ("city",         "City",          "Repeater location"),
        ("state",        "State",         "2-letter code"),
        ("owner",        "Owner",         "Who runs it"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    "e.g. Local, Travel"),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "dmr_repeater": [
        ("name",         "Name",          "Label for this repeater"),
        ("callsign",     "Repeater Call", "e.g. W5ANR"),
        ("service",      "Service",       "HAM"),
        ("rx_freq",      "RX Freq",       "Output freq"),
        ("tx_freq",      "TX Freq",       "Input freq"),
        ("offset",       "Offset",        "e.g. +5.0"),
        ("color_code",   "Color Code",    "1-15"),
        ("time_slot",    "Time Slot",     "1 or 2"),
        ("talk_group",   "Talk Group",    "e.g. 91, 3100"),
        ("power",        "Power",         "High, Med, Low"),
        ("city",         "City",          "Location"),
        ("state",        "State",         "2-letter code"),
        ("owner",        "Owner/Network", "e.g. BrandMeister"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    ""),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "dstar_repeater": [
        ("name",         "Name",          "Label for this repeater"),
        ("callsign",     "Repeater Call", "e.g. W5ANR"),
        ("service",      "Service",       "HAM"),
        ("rx_freq",      "RX Freq",       "Output freq"),
        ("tx_freq",      "TX Freq",       "Input freq"),
        ("offset",       "Offset",        "e.g. -0.600"),
        ("reflector",    "Reflector",     "e.g. REF001C"),
        ("ur_call",      "UR",            "Destination call"),
        ("rpt1",         "RPT1",          "Repeater 1"),
        ("rpt2",         "RPT2",          "Repeater 2 (gateway)"),
        ("city",         "City",          "Location"),
        ("state",        "State",         "2-letter code"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    ""),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "fusion_repeater": [
        ("name",         "Name",          "Label for this repeater"),
        ("callsign",     "Repeater Call", "e.g. W5ANR"),
        ("service",      "Service",       "HAM"),
        ("rx_freq",      "RX Freq",       "Output freq"),
        ("tx_freq",      "TX Freq",       "Input freq"),
        ("offset",       "Offset",        "e.g. -0.600"),
        ("dg_id",        "DG-ID",         "00-99"),
        ("fusion_mode",  "Mode",          "Auto, DN, VW, FR"),
        ("power",        "Power",         "High, Med, Low"),
        ("city",         "City",          "Location"),
        ("state",        "State",         "2-letter code"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    ""),
        ("notes",        "Notes",         "Any extra info"),
    ],
    "p25": [
        ("name",         "Name",          "Label for this frequency"),
        ("service",      "Service",       "HAM, Business"),
        ("rx_freq",      "RX Freq",       "Frequency"),
        ("tx_freq",      "TX Freq",       "If different"),
        ("nac",          "NAC",           "Network Access Code"),
        ("power",        "Power",         "High, Med, Low"),
        ("city",         "City",          "Location"),
        ("state",        "State",         "2-letter code"),
        ("channel_num",  "Channel #",     "Memory position"),
        ("bank",         "Bank/Group",    ""),
        ("notes",        "Notes",         "Any extra info"),
    ],
}


def _freq_type_picker(stdscr) -> str | None:
    """Show a picker to select frequency/repeater type. Returns type key or None."""
    max_y, max_x = stdscr.getmaxyx()
    types = list(FREQ_TYPE_LABELS.items())
    
    bw, bh = 35, len(types) + 6
    bx = (max_x - bw) // 2
    by = (max_y - bh) // 2
    
    sel = 0
    
    while True:
        # Draw box
        for row in range(bh):
            safe_add(stdscr, by + row, bx, " " * bw, cp("input"))
        
        # Border
        safe_add(stdscr, by, bx, "┌" + "─" * (bw - 2) + "┐", cp("input"))
        for row in range(1, bh - 1):
            safe_add(stdscr, by + row, bx, "│", cp("input"))
            safe_add(stdscr, by + row, bx + bw - 1, "│", cp("input"))
        safe_add(stdscr, by + bh - 1, bx, "└" + "─" * (bw - 2) + "┘", cp("input"))
        
        # Title
        title = " SELECT TYPE "
        safe_add(stdscr, by, bx + (bw - len(title)) // 2, title, cp("title", bold=True))
        
        # Options
        for i, (key, label) in enumerate(types):
            attr = cp("highlight") if i == sel else cp("input")
            safe_add(stdscr, by + 2 + i, bx + 2, f" {i+1}. {label:<25}", attr)
        
        # Hint
        safe_add(stdscr, by + bh - 2, bx + 2, "↑↓=select  Enter=OK  Esc=cancel", cp("dim"))
        
        stdscr.refresh()
        ch = stdscr.getch()
        
        if ch == 27:  # Esc
            return None
        elif ch in (curses.KEY_ENTER, 10, 13):
            return types[sel][0]
        elif ch == curses.KEY_UP:
            sel = (sel - 1) % len(types)
        elif ch == curses.KEY_DOWN:
            sel = (sel + 1) % len(types)
        elif ord('1') <= ch <= ord('7'):
            idx = ch - ord('1')
            if idx < len(types):
                return types[idx][0]


def _freq_form(stdscr, entry_type: str, edit_row: sqlite3.Row | None = None) -> dict | None:
    """Show a form for adding/editing a frequency entry."""
    max_y, max_x = stdscr.getmaxyx()
    fields = FREQ_FIELDS_BY_TYPE.get(entry_type, FREQ_FIELDS_BY_TYPE["simplex"])
    
    form_h = min(len(fields) + 8, max_y - 4)
    form_w = min(70, max_x - 4)
    fy = max(0, (max_y - form_h) // 2)
    fx = max(0, (max_x - form_w) // 2)
    label_w = 16
    input_w = form_w - label_w - 6
    
    # Initialize values
    values: dict[str, str] = {}
    if edit_row:
        for key, _, _ in fields:
            values[key] = str(edit_row[key] or "")
    
    # Set service default for GMRS repeater
    if entry_type == "gmrs_repeater" and not values.get("service"):
        values["service"] = "GMRS"
    
    idx = 0
    scroll = 0
    visible_fields = form_h - 6
    
    while True:
        # Clear form area
        for row in range(form_h):
            safe_add(stdscr, fy + row, fx, " " * form_w, cp("input"))
        
        # Border
        safe_add(stdscr, fy, fx, "┌" + "─" * (form_w - 2) + "┐", cp("border"))
        for row in range(1, form_h - 1):
            safe_add(stdscr, fy + row, fx, "│", cp("border"))
            safe_add(stdscr, fy + row, fx + form_w - 1, "│", cp("border"))
        safe_add(stdscr, fy + form_h - 1, fx, "└" + "─" * (form_w - 2) + "┘", cp("border"))
        
        # Title
        title = f" {'EDIT' if edit_row else 'NEW'} {FREQ_TYPE_LABELS[entry_type].upper()} "
        safe_add(stdscr, fy, fx + (form_w - len(title)) // 2, title, cp("title", bold=True))
        
        # Fields
        for i, (key, label, hint) in enumerate(fields[scroll:scroll + visible_fields]):
            row_y = fy + 2 + i
            actual_idx = scroll + i
            is_selected = (actual_idx == idx)
            
            # Label
            label_attr = cp("highlight") if is_selected else cp("field")
            safe_add(stdscr, row_y, fx + 2, f"{label:>{label_w}}", label_attr)
            
            # Value
            val = values.get(key, "")
            val_display = val[:input_w] if val else ""
            input_attr = cp("input") if is_selected else cp("odd")
            safe_add(stdscr, row_y, fx + 2 + label_w + 2, val_display.ljust(input_w), input_attr)
        
        # Hint bar
        current_field = fields[idx]
        safe_add(stdscr, fy + form_h - 3, fx + 2,
                 f"↑↓=navigate  Enter=next  ^S=SAVE  Esc=cancel".ljust(form_w - 4), cp("status"))
        safe_add(stdscr, fy + form_h - 2, fx + 2,
                 current_field[2][:form_w - 4].ljust(form_w - 4), cp("dim"))
        
        stdscr.refresh()
        
        # Get input for current field
        row_y = fy + 2 + (idx - scroll)
        key = fields[idx][0]
        
        raw, action = _form_input(
            stdscr, row_y, fx + 2 + label_w + 2, input_w,
            prefill=values.get(key, "")
        )
        
        values[key] = raw
        
        if action == _ACT_CANCEL:
            return None
        elif action == _ACT_SAVE:
            # Validate name is required
            if not values.get("name", "").strip():
                flash(stdscr, " ⚠  Name is required ", "warn")
                idx = 0
                continue
            values["entry_type"] = entry_type
            return values
        elif action == _ACT_PREV:
            if idx > 0:
                idx -= 1
                if idx < scroll:
                    scroll = idx
        else:  # _ACT_NEXT
            if idx < len(fields) - 1:
                idx += 1
                if idx >= scroll + visible_fields:
                    scroll = idx - visible_fields + 1
            else:
                # Last field — wrap to first or save
                values["entry_type"] = entry_type
                if not values.get("name", "").strip():
                    flash(stdscr, " ⚠  Name is required ", "warn")
                    idx = 0
                    scroll = 0
                    continue
                return values


# ── Frequency Import/Export ──────────────────────────────────────────────────

def _freq_export_csv(conn: sqlite3.Connection, filepath: str) -> int:
    """Export frequencies to CSV. Returns count exported."""
    import csv
    rows = freq_db_fetch(conn, None)
    if not rows:
        return 0
    
    # Define columns to export
    columns = [
        "name", "entry_type", "callsign", "service",
        "rx_freq", "tx_freq", "offset", "offset_dir", "band",
        "tx_tone_type", "tx_tone", "rx_tone_type", "rx_tone",
        "power", "bandwidth",
        "color_code", "time_slot", "talk_group",
        "reflector", "ur_call", "rpt1", "rpt2",
        "dg_id", "fusion_mode", "nac",
        "city", "state", "county", "grid",
        "owner", "net_schedule", "echolink",
        "channel_num", "bank", "notes"
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] or "" for col in columns})
    
    return len(rows)


def _freq_export_chirp(conn: sqlite3.Connection, filepath: str) -> int:
    """Export frequencies to CHIRP CSV format. Returns count exported."""
    import csv
    rows = freq_db_fetch(conn, None)
    if not rows:
        return 0
    
    # CHIRP CSV columns
    chirp_cols = [
        "Location", "Name", "Frequency", "Duplex", "Offset", "Tone",
        "rToneFreq", "cToneFreq", "DtcsCode", "DtcsPolarity", "Mode",
        "TStep", "Skip", "Comment", "URCALL", "RPT1CALL", "RPT2CALL"
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=chirp_cols)
        writer.writeheader()
        
        for i, row in enumerate(rows):
            # Map our format to CHIRP format
            duplex = ""
            if row["offset_dir"] == "+":
                duplex = "+"
            elif row["offset_dir"] == "-":
                duplex = "-"
            elif row["tx_freq"] and row["rx_freq"] and row["tx_freq"] != row["rx_freq"]:
                # Calculate duplex from frequencies
                try:
                    rx = float(row["rx_freq"])
                    tx = float(row["tx_freq"])
                    duplex = "+" if tx > rx else "-"
                except:
                    pass
            
            # Tone mode
            tone_mode = ""
            if row["tx_tone_type"] == "CTCSS":
                tone_mode = "Tone" if row["rx_tone_type"] != "CTCSS" else "TSQL"
            elif row["tx_tone_type"] == "DCS":
                tone_mode = "DTCS"
            
            # DCS code formatting
            dtcs_code = ""
            if row["tx_tone_type"] == "DCS" and row["tx_tone"]:
                dtcs_code = row["tx_tone"].replace("D", "").replace("N", "").replace("I", "")
            
            chirp_row = {
                "Location": row["channel_num"] or str(i),
                "Name": (row["name"] or "")[:8],  # CHIRP limits to 8 chars typically
                "Frequency": row["rx_freq"] or "",
                "Duplex": duplex,
                "Offset": row["offset"] or "",
                "Tone": tone_mode,
                "rToneFreq": row["rx_tone"] if row["rx_tone_type"] == "CTCSS" else "88.5",
                "cToneFreq": row["tx_tone"] if row["tx_tone_type"] == "CTCSS" else "88.5",
                "DtcsCode": dtcs_code or "023",
                "DtcsPolarity": "NN",
                "Mode": "NFM" if row["bandwidth"] == "Narrow (12.5kHz)" else "FM",
                "TStep": "5.00",
                "Skip": "S" if row.get("skip") else "",
                "Comment": row["notes"] or "",
                "URCALL": row["ur_call"] or "",
                "RPT1CALL": row["rpt1"] or "",
                "RPT2CALL": row["rpt2"] or "",
            }
            writer.writerow(chirp_row)
    
    return len(rows)


def _freq_import_csv(conn: sqlite3.Connection, filepath: str) -> tuple[int, int]:
    """Import frequencies from CSV. Returns (imported_count, skipped_count)."""
    import csv
    
    imported = 0
    skipped = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        # Detect if it's CHIRP format or our format
        first_line = f.readline()
        f.seek(0)
        
        is_chirp = "Location" in first_line and "Frequency" in first_line and "Duplex" in first_line
        
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                if is_chirp:
                    # Convert CHIRP format to our format
                    data = _convert_chirp_row(row)
                else:
                    # Our native format
                    data = dict(row)
                    if not data.get("entry_type"):
                        # Try to guess entry type
                        data["entry_type"] = _guess_entry_type(data)
                
                if data.get("name") or data.get("rx_freq"):
                    if not data.get("name"):
                        data["name"] = data.get("rx_freq", "Unnamed")
                    freq_db_insert(conn, data)
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                skipped += 1
    
    return imported, skipped


def _convert_chirp_row(row: dict) -> dict:
    """Convert a CHIRP CSV row to our format."""
    # Determine entry type based on content
    entry_type = "simplex"
    duplex = row.get("Duplex", "")
    if duplex in ("+", "-", "split"):
        entry_type = "fm_repeater"
    if row.get("URCALL") or row.get("RPT1CALL"):
        entry_type = "dstar_repeater"
    
    # Parse tone info
    tx_tone_type = ""
    tx_tone = ""
    rx_tone_type = ""
    rx_tone = ""
    
    tone_mode = row.get("Tone", "")
    if tone_mode in ("Tone", "TSQL"):
        tx_tone_type = "CTCSS"
        tx_tone = row.get("cToneFreq", "")
        if tone_mode == "TSQL":
            rx_tone_type = "CTCSS"
            rx_tone = row.get("rToneFreq", "")
    elif tone_mode == "DTCS":
        tx_tone_type = "DCS"
        tx_tone = f"D{row.get('DtcsCode', '023')}"
    
    # Parse offset
    offset = row.get("Offset", "")
    offset_dir = duplex if duplex in ("+", "-") else "Simplex"
    
    # Calculate TX freq if we have offset
    rx_freq = row.get("Frequency", "")
    tx_freq = ""
    if rx_freq and offset and duplex in ("+", "-"):
        try:
            rx = float(rx_freq)
            off = float(offset)
            tx = rx + off if duplex == "+" else rx - off
            tx_freq = f"{tx:.4f}".rstrip('0').rstrip('.')
        except:
            pass
    
    return {
        "entry_type": entry_type,
        "name": row.get("Name", ""),
        "rx_freq": rx_freq,
        "tx_freq": tx_freq,
        "offset": offset,
        "offset_dir": offset_dir,
        "tx_tone_type": tx_tone_type,
        "tx_tone": tx_tone,
        "rx_tone_type": rx_tone_type,
        "rx_tone": rx_tone,
        "bandwidth": "Narrow (12.5kHz)" if row.get("Mode") == "NFM" else "Wide (25kHz)",
        "channel_num": row.get("Location", ""),
        "notes": row.get("Comment", ""),
        "ur_call": row.get("URCALL", ""),
        "rpt1": row.get("RPT1CALL", ""),
        "rpt2": row.get("RPT2CALL", ""),
        "skip": 1 if row.get("Skip") == "S" else 0,
    }


def _guess_entry_type(data: dict) -> str:
    """Guess entry type from data fields."""
    if data.get("color_code") or data.get("talk_group"):
        return "dmr_repeater"
    if data.get("reflector") or data.get("ur_call"):
        return "dstar_repeater"
    if data.get("dg_id") or data.get("fusion_mode"):
        return "fusion_repeater"
    if data.get("nac"):
        return "p25"
    if data.get("offset") or data.get("tx_freq"):
        service = (data.get("service") or "").upper()
        if service == "GMRS":
            return "gmrs_repeater"
        return "fm_repeater"
    return "simplex"


def _freq_import_export_dialog(stdscr, conn: sqlite3.Connection, is_import: bool) -> str | None:
    """Show import/export dialog. Returns status message or None if cancelled."""
    max_y, max_x = stdscr.getmaxyx()
    
    bw, bh = 50, 12
    bx = (max_x - bw) // 2
    by = (max_y - bh) // 2
    
    action = "Import" if is_import else "Export"
    
    # Format selection
    formats = [
        ("csv", "shackradlog CSV (full data)"),
        ("chirp", "CHIRP CSV (radio programming)"),
    ]
    
    sel = 0
    
    while True:
        # Draw box
        for row in range(bh):
            safe_add(stdscr, by + row, bx, " " * bw, cp("input"))
        
        # Border
        safe_add(stdscr, by, bx, "┌" + "─" * (bw - 2) + "┐", cp("border"))
        for row in range(1, bh - 1):
            safe_add(stdscr, by + row, bx, "│", cp("border"))
            safe_add(stdscr, by + row, bx + bw - 1, "│", cp("border"))
        safe_add(stdscr, by + bh - 1, bx, "└" + "─" * (bw - 2) + "┘", cp("border"))
        
        # Title
        title = f" {action.upper()} FREQUENCIES "
        safe_add(stdscr, by, bx + (bw - len(title)) // 2, title, cp("title", bold=True))
        
        # Instructions
        safe_add(stdscr, by + 2, bx + 2, "Select format:", cp("field"))
        
        # Format options
        for i, (key, label) in enumerate(formats):
            attr = cp("highlight") if i == sel else cp("input")
            safe_add(stdscr, by + 4 + i, bx + 4, f" {i+1}. {label:<35}", attr)
        
        # Path info
        if is_import:
            safe_add(stdscr, by + 7, bx + 2, "File: ~/Desktop/frequencies.csv", cp("dim"))
        else:
            safe_add(stdscr, by + 7, bx + 2, "Saves to: ~/Desktop/", cp("dim"))
        
        # Hints
        safe_add(stdscr, by + bh - 2, bx + 2, "↑↓=select  Enter=OK  Esc=cancel", cp("dim"))
        
        stdscr.refresh()
        ch = stdscr.getch()
        
        if ch == 27:  # Esc
            return None
        elif ch in (curses.KEY_ENTER, 10, 13):
            break
        elif ch == curses.KEY_UP:
            sel = (sel - 1) % len(formats)
        elif ch == curses.KEY_DOWN:
            sel = (sel + 1) % len(formats)
        elif ch in (ord('1'), ord('2')):
            sel = ch - ord('1')
            break
    
    fmt = formats[sel][0]
    
    # Determine paths
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / ".shackradlog"
    
    if is_import:
        # Get filename from user
        flash(stdscr, " Filename (in ~/Desktop/): ", "field", wait=False)
        curses.echo()
        curses.curs_set(1)
        try:
            filename = stdscr.getstr(stdscr.getyx()[0], stdscr.getyx()[1], 40).decode().strip()
        except:
            filename = ""
        curses.noecho()
        curses.curs_set(0)
        
        if not filename:
            filename = "frequencies.csv"
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        filepath = desktop / filename
        if not filepath.exists():
            return f"File not found: {filepath}"
        
        imported, skipped = _freq_import_csv(conn, str(filepath))
        return f"Imported {imported} frequencies ({skipped} skipped)"
    
    else:
        # Export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "chirp":
            filename = f"frequencies_chirp_{timestamp}.csv"
            filepath = desktop / filename
            count = _freq_export_chirp(conn, str(filepath))
        else:
            filename = f"frequencies_{timestamp}.csv"
            filepath = desktop / filename
            count = _freq_export_csv(conn, str(filepath))
        
        if count:
            return f"Exported {count} frequencies to {filepath}"
        else:
            return "No frequencies to export"


def _draw_freq_list(stdscr, rows, offset, sel, filters):
    """Draw the frequencies list screen."""
    max_y, max_x = stdscr.getmaxyx()
    table_h = max_y - 5
    
    # Title
    title = "── MY FREQUENCIES ──"
    safe_add(stdscr, 0, 0, f" {title}".ljust(max_x), cp("title", bold=True))
    count = f" {len(rows)} saved "
    safe_add(stdscr, 0, max_x - len(count) - 1, count, cp("title", bold=True))
    
    # Key bar
    safe_add(stdscr, 1, 0, " " * max_x, cp("border"))
    keys = [("N","New"),("E","Edit"),("D","Del"),("S","Search"),("I","Import"),("X","Export"),("Q","Back")]
    kx = 1
    for k, lbl in keys:
        if kx + len(lbl) + 6 >= max_x:
            break
        safe_add(stdscr, 1, kx, f"[{k}]", cp("key", bold=True))
        safe_add(stdscr, 1, kx+3, f"{lbl}  ", cp("border"))
        kx += len(lbl) + 6
    
    # Filter indicator
    if filters:
        parts = [f"{k}={v}" for k, v in filters.items() if v]
        filter_text = f" Filter: {', '.join(parts)} "[:max_x - 2]
        safe_add(stdscr, 2, 0, filter_text.ljust(max_x), cp("warn"))
        header_row = 3
    else:
        header_row = 2
    
    # Column headers
    # Name | Type | Freq | Tone | Location
    col_widths = [20, 16, 10, 8, max(10, max_x - 58)]
    headers = ["Name", "Type", "Freq", "Tone", "Location"]
    hx = 0
    for header, w in zip(headers, col_widths):
        safe_add(stdscr, header_row, hx, header[:w].ljust(w), cp("header", bold=True) | curses.A_UNDERLINE)
        hx += w + 1
    
    # Rows
    data_start = header_row + 1
    visible = min(table_h, len(rows) - offset)
    
    for i in range(visible):
        row_idx = offset + i
        row = rows[row_idx]
        ry = data_start + i
        
        is_selected = (row_idx == sel)
        attr = cp("highlight") if is_selected else (cp("even") if i % 2 else cp("odd"))
        
        # Build row content
        name = (row["name"] or "")[:col_widths[0]]
        ftype = FREQ_TYPE_LABELS.get(row["entry_type"], row["entry_type"] or "")[:col_widths[1]]
        freq = (row["rx_freq"] or "")[:col_widths[2]]
        tone = (row["tx_tone"] or "")[:col_widths[3]]
        loc = f"{row['city'] or ''}, {row['state'] or ''}"[:col_widths[4]] if row["city"] else (row["state"] or "")[:col_widths[4]]
        
        line = f"{name:<{col_widths[0]}} {ftype:<{col_widths[1]}} {freq:<{col_widths[2]}} {tone:<{col_widths[3]}} {loc:<{col_widths[4]}}"
        safe_add(stdscr, ry, 0, line[:max_x].ljust(max_x), attr)
    
    # Status bar
    safe_add(stdscr, max_y - 1, 0,
             f"  Press N to add new frequency  ".ljust(max_x), cp("status"))


def frequencies_screen(stdscr, conn: sqlite3.Connection):
    """Main frequencies/repeaters management screen."""
    filters: dict = {}
    rows = freq_db_fetch(conn, filters)
    sel = 0
    offset = 0
    
    while True:
        max_y, max_x = stdscr.getmaxyx()
        table_h = max_y - 6
        
        stdscr.clear()
        _draw_freq_list(stdscr, rows, offset, sel, filters)
        stdscr.refresh()
        
        ch = stdscr.getch()
        
        if ch in (ord('q'), ord('Q'), 27):  # Q or Esc
            break
        
        elif ch in (ord('n'), ord('N')):
            entry_type = _freq_type_picker(stdscr)
            if entry_type:
                data = _freq_form(stdscr, entry_type)
                if data:
                    freq_db_insert(conn, data)
                    rows = freq_db_fetch(conn, filters)
                    sel = 0
        
        elif ch in (ord('e'), ord('E')):
            if rows:
                row = rows[sel]
                data = _freq_form(stdscr, row["entry_type"], edit_row=row)
                if data:
                    freq_db_update(conn, row["id"], data)
                    rows = freq_db_fetch(conn, filters)
        
        elif ch in (ord('d'), ord('D')):
            if rows:
                row = rows[sel]
                flash(stdscr, f" Delete '{row['name']}'? [y/N] ", "highlight", wait=False)
                if stdscr.getch() in (ord('y'), ord('Y')):
                    freq_db_delete(conn, row["id"])
                    rows = freq_db_fetch(conn, filters)
                    sel = max(0, min(sel, len(rows) - 1))
        
        elif ch in (ord('s'), ord('S')):
            # Simple filter by name for now
            flash(stdscr, " Search name: ", "field", wait=False)
            curses.echo()
            curses.curs_set(1)
            try:
                search = stdscr.getstr(stdscr.getyx()[0], stdscr.getyx()[1], 30).decode()
            except:
                search = ""
            curses.noecho()
            curses.curs_set(0)
            
            if search:
                filters = {"name": search}
            else:
                filters = {}
            rows = freq_db_fetch(conn, filters)
            sel = 0
            offset = 0
        
        elif ch in (ord('i'), ord('I')):
            result = _freq_import_export_dialog(stdscr, conn, is_import=True)
            if result:
                flash(stdscr, f" {result} ", "status")
                rows = freq_db_fetch(conn, filters)
                sel = 0
                offset = 0
        
        elif ch in (ord('x'), ord('X')):
            result = _freq_import_export_dialog(stdscr, conn, is_import=False)
            if result:
                flash(stdscr, f" {result} ", "status")
        
        # Navigation
        elif ch == curses.KEY_UP:
            if sel > 0:
                sel -= 1
                if sel < offset:
                    offset = sel
        
        elif ch == curses.KEY_DOWN:
            if sel < len(rows) - 1:
                sel += 1
                if sel >= offset + table_h:
                    offset = sel - table_h + 1
        
        elif ch == curses.KEY_PPAGE:
            sel = max(0, sel - table_h)
            offset = max(0, offset - table_h)
        
        elif ch == curses.KEY_NPAGE:
            sel = min(len(rows) - 1, sel + table_h)
            offset = min(max(0, len(rows) - table_h), offset + table_h)
        
        elif ch in (curses.KEY_ENTER, 10, 13):
            # View/Edit on enter
            if rows:
                row = rows[sel]
                data = _freq_form(stdscr, row["entry_type"], edit_row=row)
                if data:
                    freq_db_update(conn, row["id"], data)
                    rows = freq_db_fetch(conn, filters)


def main(stdscr):
    init_colors()
    curses.curs_set(0)
    # Disable XON/XOFF flow control so Ctrl+S (chr 19) is not swallowed
    try:
        import termios, tty
        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[0] &= ~(termios.IXON | termios.IXOFF)  # clear flow control flags
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        pass  # Windows or other platforms — skip silently
    conn    = db_connect(DB_PATH)
    freq_db_init(conn)  # Initialize frequencies table

    # ── Monthly geo DB refresh (before main loop, on main thread) ─────────


    filters: dict = {}
    rows          = db_fetch(conn, filters)
    worked_counts = db_worked_counts(conn)
    sel           = 0
    offset        = 0

    def refresh_rows():
        nonlocal rows, sel, offset, worked_counts
        rows          = db_fetch(conn, filters)
        worked_counts = db_worked_counts(conn)
        sel    = min(sel, max(0, len(rows)-1))
        offset = min(offset, max(0, len(rows) - (stdscr.getmaxyx()[0] - 5)))

    while True:
        max_y, max_x = stdscr.getmaxyx()
        table_h = max_y - 5
        stdscr.clear()
        draw_table_screen(stdscr, rows, offset, sel, filters, worked_counts)
        stdscr.refresh()

        ch = stdscr.getch()

        if ch in (ord('q'), ord('Q')):
            break

        elif ch in (curses.KEY_ENTER, 10, 13):
            if rows:
                action = detail_view(stdscr, rows[sel], conn, rows)
                if action == "edit":
                    edit_row = rows[sel]
                    contact  = contact_form(stdscr, rows, edit_row=edit_row)
                    if contact:
                        band_ok = db_update(conn, edit_row["id"], contact)
                        refresh_rows()
                        updated = conn.execute(
                            "SELECT * FROM contacts WHERE id=?", (edit_row["id"],)
                        ).fetchone()
                        _unresolved_flash(stdscr, updated, contact)
                        if not band_ok:
                            flash(stdscr,
                                  " ⚠  Frequency not in a known amateur band — band field left empty. ",
                                  "warn")
                elif action == "delete":
                    c = rows[sel]
                    flash(stdscr,
                          f" Delete {c['callsign']} on {c['date']}? [y/N] ",
                          "highlight", wait=False)
                    if stdscr.getch() in (ord('y'), ord('Y')):
                        db_delete(conn, c["id"])
                        refresh_rows()
                        sel = max(0, sel - 1)

        elif ch in (ord('l'), ord('L')):
            contact = quick_log_form(stdscr, conn, rows)
            if contact:
                new_id, band_ok = db_insert(conn, contact)
                refresh_rows()
                _post_to_dashboard(contact)
                sel     = 0
                new_row = conn.execute(
                    "SELECT * FROM contacts WHERE id=?", (new_id,)
                ).fetchone()
                _unresolved_flash(stdscr, new_row, contact)
                if not band_ok:
                    flash(stdscr,
                          " ⚠  Frequency not in a known amateur band — band field left empty. ",
                          "warn")

        elif ch in (ord('n'), ord('N')):
            contact = contact_form(stdscr, rows)
            if contact:
                new_id, band_ok = db_insert(conn, contact)
                refresh_rows()
                _post_to_dashboard(contact)
                sel     = 0
                new_row = conn.execute(
                    "SELECT * FROM contacts WHERE id=?", (new_id,)
                ).fetchone()
                _unresolved_flash(stdscr, new_row, contact)
                if not band_ok:
                    flash(stdscr,
                          " ⚠  Frequency not in a known amateur band — band field left empty. ",
                          "warn")

        elif ch in (ord('e'), ord('E')):
            if rows:
                edit_row = rows[sel]
                contact  = contact_form(stdscr, rows, edit_row=edit_row)
                if contact:
                    band_ok = db_update(conn, edit_row["id"], contact)
                    refresh_rows()
                    updated = conn.execute(
                        "SELECT * FROM contacts WHERE id=?", (edit_row["id"],)
                    ).fetchone()
                    _unresolved_flash(stdscr, updated, contact)
                    if not band_ok:
                        flash(stdscr,
                              " ⚠  Frequency not in a known amateur band — band field left empty. ",
                              "warn")

        elif ch in (ord('d'), ord('D')):
            if rows:
                c = rows[sel]
                flash(stdscr,
                      f" Delete {c['callsign']} on {c['date']}? [y/N] ",
                      "highlight", wait=False)
                if stdscr.getch() in (ord('y'), ord('Y')):
                    db_delete(conn, c["id"])
                    refresh_rows()

        elif ch in (ord('s'), ord('S')):
            result = search_form(stdscr, filters)
            if result is not None:
                filters = result
                refresh_rows()
                sel = 0; offset = 0

        elif ch in (ord('x'), ord('X')):
            export_dialog(stdscr, conn, filters)

        elif ch in (ord('i'), ord('I')):
            imported = import_dialog(stdscr, conn)
            if imported > 0:
                refresh_rows()
                sel = 0
                offset = 0

        elif ch in (ord('/'), ord('?')):
            stats_screen(stdscr, conn)

        elif ch in (ord('f'), ord('F')):
            frequencies_screen(stdscr, conn)

        # Navigation
        elif ch == curses.KEY_UP:
            if sel > 0:
                sel -= 1
                if sel < offset: offset = sel

        elif ch == curses.KEY_DOWN:
            if sel < len(rows) - 1:
                sel += 1
                if sel >= offset + table_h:
                    offset = sel - table_h + 1

        elif ch == curses.KEY_PPAGE:
            sel    = max(0, sel - table_h)
            offset = max(0, offset - table_h)

        elif ch == curses.KEY_NPAGE:
            sel    = min(len(rows)-1, sel + table_h)
            offset = min(max(0, len(rows)-table_h), offset + table_h)

        elif ch == curses.KEY_HOME:
            sel = 0; offset = 0

        elif ch == curses.KEY_END:
            sel    = max(0, len(rows)-1)
            offset = max(0, len(rows) - table_h)

    conn.close()

VERSION = "1.1.0"

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Restore terminal to sane state immediately — in case a previous curses
    # session left it in raw/noecho mode, which would corrupt all output below.
    os.system("stty sane 2>/dev/null || true")

    if len(sys.argv) > 1:
        arg = " ".join(sys.argv[1:]).strip().lower()
        if arg in ("--version", "-v", "version"):
            print(f"shackradlog {VERSION}")
            sys.exit(0)
        elif arg in ("--help", "-h", "help"):
            print(f"shackradlog {VERSION}  —  Ham Radio Contact Logger")
            print()
            print("Usage:")
            print("  shackradlog              start the logger")
            print("  shackradlog --version    show version")
            print("  shackradlog --help       show this help")
            print("  shackradlog 'show w'     warranty disclaimer (GPL)")
            print("  shackradlog 'show c'     redistribution conditions (GPL)")
            print()
            print(f"Database : {DB_PATH}")
            print(f"Exports  : {Path.home() / 'Desktop'}  (default)")
            sys.exit(0)
        elif arg == "show w":
            print(_GPL_WARRANTY)
            sys.exit(0)
        elif arg == "show c":
            print(_GPL_CONDITIONS)
            sys.exit(0)
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Run 'shackradlog --help' for usage.")
            sys.exit(1)

    # Print GPL startup notice (required by GPL section 5c)
    print(_GPL_NOTICE)
    print()

    geo_startup_check()

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass

    # Reset terminal — curses leaves raw/noecho state; stty sane restores it
    os.system("stty sane 2>/dev/null || true")

    print(f"\nshackradlog exited. Database: {DB_PATH}")
