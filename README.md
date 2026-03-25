# shackradlog

**A terminal-based radio contact logger for Ham, GMRS, MURS, FRS, and CB.**

Works on macOS (Apple Silicon & Intel) and Linux (including Raspberry Pi).

No internet connection required to log. No accounts. No subscriptions. Your log is a plain SQLite file on your own machine — back it up like any other file.

---

## Quick Install

```bash
curl -sL https://raw.githubusercontent.com/SilverBull239/shackradlog/main/app/install_shackradlog.sh | bash
```

Then run:
```bash
source ~/.zshrc   # or ~/.bashrc on Linux
shackradlog
```

---

## Requirements

- **macOS:** Apple Silicon (M1/M2/M3/M4) or Intel Mac
- **Linux:** Raspberry Pi, Debian, Ubuntu, or similar
- **Python 3.11+** — check with `python3 --version`
- Internet connection on first run only — shackradlog downloads a city database (~50 MB) to enable location lookup. After that it works completely offline.

---

## Manual Installation

1. Download and unzip `shackradlog.zip`
2. Run the installer:
   - **macOS:** Double-click **Install shackradlog.command**
   - **Linux:** `bash shackradlog/app/install_shackradlog.sh`
3. Open a new terminal and type `shackradlog`

> **First run:** shackradlog downloads the GeoNames city database (~50 MB). This takes 1–2 minutes and only happens once.

To uninstall:
```bash
~/.shackradlog/app/install_shackradlog.sh --uninstall
```

Your log data is **never touched** by uninstall — only the app files and launcher are removed. Delete `~/.shackradlog` manually if you want to remove everything including your log.

---

## Files

```
shackradlog/
├── app/
│   ├── shackradlog.py           main TUI application
│   ├── shackradlog_db.py        database layer (SQLite)
│   ├── shackradlog_export.py    ADIF / CSV / JSON export & import
│   ├── shackradlog_freq.py      frequency normalisation and band mapping
│   ├── shackradlog_location.py  location parsing (states, DXCC, grid squares)
│   ├── shackradlog_dxcc.csv     DXCC prefix table (514 prefixes, 319 entities)
│   ├── shackradlog_geo.py       GeoNames city lookup (auto-downloads DB on first run)
│   └── install_shackradlog.sh   cross-platform installer
├── Install shackradlog.command  macOS double-click installer
├── README.md
└── LICENSE                      GNU GPL v3
```

All files must stay in the same folder — the app will not start if any are missing.

Your data lives separately in `~/.shackradlog/` and is never affected by updates or reinstalls.

---

## What it looks like

```
╔══ SHACKRADLOG ══╗  Ham Radio Contact Logger                        12 QSOs
──────────────────────────────────────────────────────────────────────────────
[N]New  [L]Quick  [E]Edit  [D]Del  [S]Search  [X]Export  [/]Stats  [Q]Quit
──────────────────────────────────────────────────────────────────────────────
Date         UTC    Callsign    Freq      Band  Mode  RST↑  RST↓  Location
2026-03-11   14:32  W1AW        14.225    20m   SSB   59    57    Newington, Connecticut
2026-03-11   03:15  JA1XYZ      14.074    20m   FT8   -10   -12   Tokyo, Japan
2026-03-10   22:45  K5XYZ ×3   146.520    2m    FM    59    59    Fayetteville, Arkansas
```

The `×3` badge means you've worked that station 3 times. Press **Enter** on any row for a full detail view.

---

## Logging a contact

### Full form — `N`

Opens an 8-field form. Navigate with arrow keys or Enter.

| Field | Notes |
|-------|-------|
| Callsign | Auto-uppercased |
| Frequency | MHz, kHz, or bare integer — band auto-detected (see formats below) |
| Mode | SSB USB LSB CW · FT8 FT4 JS8 WSPR JT65 JT9 · FM AM RTTY SSTV PSK31 PSK63 · Olivia THOR CONTESTIA MFSK and more |
| RST Sent | Standard RST (59, 599) or dBm for digital modes (-10) |
| RST Rcvd | Same |
| QTH | City, state, country, grid square, or any combination — resolved automatically |
| Power | Watts |
| Notes | Free text |

**Ctrl+S** saves from any field. **ESC** cancels without saving.

### Quick log — `L`

A compact 5-field overlay designed for fast entries during a pileup or contest. Only asks for callsign, frequency, mode, RST sent, and RST received.

As you type a callsign, shackradlog searches your previous QSOs and shows an autofill suggestion. Press **Tab** to accept — frequency and mode pre-fill from your last QSO with that station. RST fields default to 59 so you can press Enter straight through.

Typical repeat-contact flow: type call → **Tab** → **Enter** → **Enter** → **Enter** → **Enter** → logged.

---

## Navigating your log

| Key | Action |
|-----|--------|
| ↑ / ↓ | Move selection |
| PgUp / PgDn | Scroll by page |
| Home / End | First / last contact |
| Enter | Open detail view |
| E | Edit selected contact |
| D | Delete selected (confirms y/N) |
| N | New contact (full form) |
| L | Quick log |
| S | Search / filter |
| X | Export |
| / | Stats screen |
| Q | Quit |

### Detail view

Press **Enter** on any contact to open a full-screen view with every field — complete location breakdown, grid square, CQ and ITU zones, word-wrapped notes, and log timestamp. Press **E** to edit or **D** to delete from inside the detail view without returning to the table first.

### Search — `S`

Filter by any combination of callsign, mode, band, frequency, country, state, or date range. An active filter is shown at the top of the screen. Press **C** inside search to clear all filters.

---

## Location resolution

When you save a contact, shackradlog resolves the QTH field into structured data using this priority order:

1. **Maidenhead grid square** — detected automatically (e.g. `EM36`, `EM36ab`)
2. **GeoNames city lookup** — matched against 500,000+ cities from a local database. Callsign prefix and state text are used as disambiguation hints, so `Fayetteville, AR` correctly resolves to Arkansas rather than North Carolina
3. **US state** — all 50 states, DC, territories, standard abbreviations, and common aliases
4. **DXCC entity name** — 319 entities matched by name in the QTH text
5. **Callsign prefix fallback** — 514 prefixes covering all DXCC entities; used when nothing else resolves

Contacts with unresolved locations show a `⚠` marker in the table and detail view.

---

## Stats — `/`

A scrollable stats screen showing total QSOs, unique callsigns, active date range, bar charts by band/mode/country, top callsigns and locations, and unresolved location count.

---

## Exporting your log

Press **X** to export. Choose a format, then confirm or edit the output directory.

| Format | Notes |
|--------|-------|
| **ADIF** `.adi` | ADIF 3.1.4 compliant. Imports into WSJT-X, Ham Radio Deluxe, LoTW, and most other logging software. FT8/FT4/JS8 export with correct `MODE: MFSK` + `SUBMODE` fields. Full Olivia, THOR, CONTESTIA, and MFSK submode support. Unicode-safe byte counts. US contacts include `STATE` field. |
| **CSV** `.csv` | All fields including all resolved location columns. Opens in Excel, Numbers, Google Sheets. |
| **JSON** `.json` | Complete structured export with all metadata fields. |

Exports default to `~/Desktop`. Files are timestamped so they never overwrite each other.

---

## Frequency formats

All of these are equivalent for 14.225 MHz:

```
14.225      14225       14225k      14225khz
14.225mhz   14225000    14225000hz  14.225.000
```

VHF/UHF bare integers are handled correctly — `146520` and `146.52` both resolve to `146.52 MHz [2m]`.

---

## Your data

```
~/.shackradlog/
├── shackradlog.db             your QSO log (SQLite)
├── shackradlog_geo.db         city lookup database (~25 MB, auto-downloaded)
├── shackradlog_geo_meta.json  tracks when the city database was last refreshed
└── app/                  app files (installer copies them here)
```

**`shackradlog.db`** is your log. Back this file up — it's a standard SQLite database and can be opened with any SQLite browser, queried directly, or imported into other tools.

**`shackradlog_geo.db`** is downloaded automatically from GeoNames on first run and silently refreshed once a month. It's safe to delete — shackradlog will re-download it. It has no effect on your log data.

---

## Key bindings

### Main screen

| Key | Action |
|-----|--------|
| N | New contact (full form) |
| L | Quick log |
| E | Edit selected |
| D | Delete selected |
| S | Search / filter |
| X | Export |
| / | Stats |
| Q | Quit |
| Enter | Detail view |
| ↑ ↓ PgUp PgDn Home End | Navigate |

### Contact form

| Key | Action |
|-----|--------|
| Enter / ↓ | Next field |
| ↑ | Previous field |
| Ctrl+S | Save immediately from any field |
| ESC | Cancel |
| ← → Home End | Move cursor within field |

### Quick log

| Key | Action |
|-----|--------|
| Tab | Accept callsign autofill |
| Enter | Next field / save on last field |
| Ctrl+S | Save immediately |
| ESC | Cancel |

---

## License

GNU General Public License v3 — see `LICENSE` for full terms.

Copyright (C) 2026 Aron Tkachuk — silverbull239@proton.me

73 de Aron
