"""
shackradlog_export.py — ADIF, CSV, and JSON export for shackradlog.

Provides:
  adif_field(tag, val)    → ADIF field string
  adif_fmt_freq(freq_str) → ADIF-spec frequency string
  adif_fmt_time(utc_str)  → ADIF HHMMSS time string
  export_adif(rows, path) → write .adi file
  export_csv(rows, path)  → write .csv file
  export_json(rows, path) → write .json file

  _ADIF_MODE_MAP          — shackradlog mode → (ADIF MODE, ADIF SUBMODE)
"""

# ── License ───────────────────────────────────────────────────────────────────
# Copyright (C) 2026  Aron Tkachuk  |  silverbull239@proton.me
# GNU General Public License v3 or later — see <https://www.gnu.org/licenses/>


import csv
import json
import datetime
from pathlib import Path

from shackradlog_freq import normalize_freq

# ── Export ────────────────────────────────────────────────────────────────────
# ── ADIF helpers (module-level so they're testable directly) ─────────────────
def adif_field(tag: str, val: str) -> str:
    """Return <TAG:BYTECOUNT>value, or '' if val is empty. Byte-safe for Unicode."""
    if not val:
        return ""
    return f"<{tag}:{len(val.encode('utf-8'))}>{val}"


def adif_fmt_freq(freq_str: str) -> str:
    """Format frequency as MHz string with 3–6 significant decimal places."""
    try:
        f = float(freq_str)
        s = f"{f:.6f}".rstrip("0")
        if "." in s and len(s.split(".")[1]) < 3:
            s = f"{f:.3f}"
        return s
    except (ValueError, TypeError):
        return freq_str or ""


def adif_fmt_time(utc_str: str) -> str:
    """Format HH:MM or HHMM as HHMMSS (ADIF TIME_ON format).
    Always returns a 6-character string; empty/None input → '000000'."""
    t = (utc_str or "").replace(":", "")
    if not t:
        return "000000"
    if len(t) == 4:
        t += "00"
    return t[:6]


# shackradlog mode → (ADIF MODE, ADIF SUBMODE)
_ADIF_MODE_MAP: dict[str, tuple[str, str]] = {
    "FT8":       ("MFSK",      "FT8"),
    "FT4":       ("MFSK",      "FT4"),
    "JS8":       ("MFSK",      "JS8"),
    "WSPR":      ("WSPR",      ""),
    "JT65":      ("JT65",      ""),
    "JT9":       ("JT9",       ""),
    "PSK31":     ("PSK31",     ""),
    "PSK63":     ("PSK63",     ""),
    "RTTY":      ("RTTY",      ""),
    "SSTV":      ("SSTV",      ""),
    "AM":        ("AM",        ""),
    "FM":        ("FM",        ""),
    "SSB":       ("SSB",       ""),
    "USB":       ("SSB",       "USB"),
    "LSB":       ("SSB",       "LSB"),
    "CW":        ("CW",        ""),
    "PHONE":     ("SSB",       ""),
    "DIGI":      ("MFSK",      ""),
    # Digital modes commonly used on HF
    "OLIVIA":    ("OLIVIA",    ""),
    "OLIVIA4":   ("OLIVIA",    "OLIVIA 4/250"),
    "OLIVIA8":   ("OLIVIA",    "OLIVIA 8/250"),
    "OLIVIA16":  ("OLIVIA",    "OLIVIA 16/500"),
    "THOR":      ("THOR",      ""),
    "THOR4":     ("THOR",      "THOR 4"),
    "THOR8":     ("THOR",      "THOR 8"),
    "THOR16":    ("THOR",      "THOR 16"),
    "CONTESTIA": ("CONTESTIA", ""),
    "MFSK8":     ("MFSK",      "MFSK8"),
    "MFSK16":    ("MFSK",      "MFSK16"),
    "HELL":      ("HELL",      ""),
    "FMHELL":    ("HELL",      "FMHELL"),
    "DOMINO":    ("DOMINO",    ""),
    "DOMINOEX":  ("DOMINO",    "DOMINOEX"),
}


def export_adif(rows: list, path: Path):
    """
    Export contacts to ADIF format (.adi).
    Compliant with ADIF 3.1.4 spec:
      - Proper header with adif_ver, programid, created_timestamp
      - Field lengths are byte counts (not char counts) for Unicode safety
      - FREQ in MHz with up to 6 decimal places
      - TIME_ON zero-padded to 6 chars (HHMMSS)
      - COUNTRY = country name, STATE = 2-letter US state
      - DXCC tag omitted (requires numeric entity codes we don't store)
      - GRIDSQUARE included when available
      - Notes go into COMMENT field
    """
    now     = datetime.datetime.now(datetime.timezone.utc)
    created = now.strftime("%Y%m%d %H%M%S")

    with open(path, "w", encoding="utf-8") as f:
        # ── Header ────────────────────────────────────────────────────────────
        f.write(
            f"shackradlog export\n"
            f"{adif_field('adif_ver', '3.1.4')}\n"
            f"{adif_field('programid', 'shackradlog')}\n"
            f"{adif_field('programversion', '1.0')}\n"
            f"{adif_field('created_timestamp', created)}\n"
            f"<EOH>\n\n"
        )

        for r in rows:
            date         = (r["date"] or "").replace("-", "")
            time         = adif_fmt_time(r["utc"] or "")
            freq         = adif_fmt_freq(r["freq"] or "")
            mode_raw     = (r["mode"] or "").upper().strip()
            adif_mode, adif_submode = _ADIF_MODE_MAP.get(mode_raw, (mode_raw, ""))

            # STATE only for US contacts
            state = ""
            if r["qth_state"] and r["qth_country"] == "United States":
                state = r["qth_state"]

            # QTH: prefer the raw user-entered location text
            qth_val = (r["qth_raw"] or r["qth"] or "").strip()

            parts = [
                adif_field("CALL",       r["callsign"] or ""),
                adif_field("QSO_DATE",   date),
                adif_field("TIME_ON",    time),
                adif_field("FREQ",       freq),
                adif_field("BAND",       r["band"] or ""),
                adif_field("MODE",       adif_mode),
                adif_field("SUBMODE",    adif_submode),
                adif_field("RST_SENT",   r["rst_sent"] or ""),
                adif_field("RST_RCVD",   r["rst_rcvd"] or ""),
                adif_field("QTH",        qth_val),
                adif_field("STATE",      state),
                adif_field("GRIDSQUARE", r["qth_grid"] or ""),
                adif_field("COUNTRY",    r["qth_country"] or ""),
                adif_field("TX_PWR",     r["power"] or ""),
                adif_field("COMMENT",    r["notes"] or ""),
            ]
            # One record per line, EOR on same line
            f.write("".join(p for p in parts if p) + "<EOR>\n\n")

def export_csv(rows: list, path: Path):
    cols = ["date","utc","callsign","freq","band","mode",
            "rst_sent","rst_rcvd",
            "qth","qth_display","qth_grid","qth_state","qth_country","qth_dxcc",
            "qth_itu","qth_cq","qth_resolved",
            "power","notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows([dict(r) for r in rows])

def export_json(rows: list, path: Path):
    cols = ["id","date","utc","callsign","freq","band","mode",
            "rst_sent","rst_rcvd",
            "qth","qth_display","qth_grid","qth_state","qth_country","qth_dxcc",
            "qth_itu","qth_cq","qth_resolved",
            "power","notes","created"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{k: r[k] for k in cols} for r in rows], f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# IMPORT FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_adif_record(record: str) -> dict:
    """Parse a single ADIF record into a dict."""
    import re
    data = {}
    # Match <FIELD:LENGTH>VALUE or <FIELD:LENGTH:TYPE>VALUE
    pattern = re.compile(r'<(\w+):(\d+)(?::\w)?>', re.IGNORECASE)
    
    pos = 0
    for match in pattern.finditer(record):
        field = match.group(1).upper()
        length = int(match.group(2))
        value_start = match.end()
        value = record[value_start:value_start + length]
        data[field] = value
    
    return data


def _adif_to_contact(adif_rec: dict) -> dict:
    """Convert ADIF record to shackradlog contact dict."""
    # Parse date: YYYYMMDD → YYYY-MM-DD
    date_raw = adif_rec.get("QSO_DATE", "")
    if len(date_raw) == 8:
        date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    else:
        date = date_raw
    
    # Parse time: HHMMSS → HH:MM
    time_raw = adif_rec.get("TIME_ON", "") or adif_rec.get("TIME_OFF", "")
    if len(time_raw) >= 4:
        utc = f"{time_raw[:2]}:{time_raw[2:4]}"
    else:
        utc = time_raw
    
    # Mode: prefer SUBMODE if available, otherwise MODE
    mode = adif_rec.get("SUBMODE", "") or adif_rec.get("MODE", "")
    
    # QTH: combine available location fields
    qth_parts = []
    if adif_rec.get("QTH"):
        qth_parts.append(adif_rec["QTH"])
    if adif_rec.get("STATE") and not adif_rec.get("QTH"):
        qth_parts.append(adif_rec["STATE"])
    if adif_rec.get("COUNTRY") and not adif_rec.get("QTH"):
        qth_parts.append(adif_rec["COUNTRY"])
    qth = ", ".join(qth_parts) if qth_parts else ""
    
    return {
        "date": date,
        "utc": utc,
        "callsign": adif_rec.get("CALL", "").upper(),
        "freq": adif_rec.get("FREQ", ""),
        "band": adif_rec.get("BAND", ""),
        "mode": mode.upper(),
        "rst_sent": adif_rec.get("RST_SENT", ""),
        "rst_rcvd": adif_rec.get("RST_RCVD", ""),
        "qth": qth,
        "qth_grid": adif_rec.get("GRIDSQUARE", ""),
        "qth_state": adif_rec.get("STATE", ""),
        "qth_country": adif_rec.get("COUNTRY", ""),
        "power": adif_rec.get("TX_PWR", ""),
        "notes": adif_rec.get("COMMENT", "") or adif_rec.get("NOTES", ""),
    }


def import_adif(path: Path) -> list[dict]:
    """
    Import contacts from ADIF file.
    Returns list of contact dicts ready for db_insert.
    """
    contacts = []
    
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    # Split header and records
    # Find <EOH> (end of header)
    eoh_match = content.upper().find("<EOH>")
    if eoh_match != -1:
        content = content[eoh_match + 5:]  # Skip past <EOH>
    
    # Split by <EOR> (end of record)
    import re
    records = re.split(r'<EOR>', content, flags=re.IGNORECASE)
    
    for record in records:
        record = record.strip()
        if not record:
            continue
        
        adif_rec = _parse_adif_record(record)
        if adif_rec.get("CALL"):  # Must have a callsign
            contact = _adif_to_contact(adif_rec)
            contacts.append(contact)
    
    return contacts


def import_csv(path: Path) -> list[dict]:
    """
    Import contacts from CSV file.
    Returns list of contact dicts ready for db_insert.
    Handles both shackradlog CSV format and generic formats.
    """
    contacts = []
    
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Normalize field names (lowercase, strip)
            row = {k.lower().strip(): v for k, v in row.items()}
            
            # Map common column name variations
            contact = {
                "date": row.get("date", "") or row.get("qso_date", ""),
                "utc": row.get("utc", "") or row.get("time_on", "") or row.get("time", ""),
                "callsign": (row.get("callsign", "") or row.get("call", "")).upper(),
                "freq": row.get("freq", "") or row.get("frequency", ""),
                "band": row.get("band", ""),
                "mode": (row.get("mode", "") or row.get("submode", "")).upper(),
                "rst_sent": row.get("rst_sent", "") or row.get("rstsent", ""),
                "rst_rcvd": row.get("rst_rcvd", "") or row.get("rstrcvd", ""),
                "qth": row.get("qth", "") or row.get("qth_display", ""),
                "qth_grid": row.get("qth_grid", "") or row.get("gridsquare", "") or row.get("grid", ""),
                "qth_state": row.get("qth_state", "") or row.get("state", ""),
                "qth_country": row.get("qth_country", "") or row.get("country", ""),
                "power": row.get("power", "") or row.get("tx_pwr", ""),
                "notes": row.get("notes", "") or row.get("comment", ""),
            }
            
            # Must have callsign
            if contact["callsign"]:
                contacts.append(contact)
    
    return contacts


def import_json(path: Path) -> list[dict]:
    """
    Import contacts from JSON file.
    Returns list of contact dicts ready for db_insert.
    """
    contacts = []
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handle both array of contacts and object with "contacts" key
    if isinstance(data, dict):
        data = data.get("contacts", data.get("qsos", []))
    
    for row in data:
        if not isinstance(row, dict):
            continue
        
        # Normalize field names
        row = {k.lower().strip(): v for k, v in row.items()}
        
        contact = {
            "date": row.get("date", "") or row.get("qso_date", ""),
            "utc": row.get("utc", "") or row.get("time_on", "") or row.get("time", ""),
            "callsign": (row.get("callsign", "") or row.get("call", "")).upper(),
            "freq": str(row.get("freq", "") or row.get("frequency", "")),
            "band": row.get("band", ""),
            "mode": (row.get("mode", "") or row.get("submode", "")).upper(),
            "rst_sent": str(row.get("rst_sent", "") or row.get("rstsent", "")),
            "rst_rcvd": str(row.get("rst_rcvd", "") or row.get("rstrcvd", "")),
            "qth": row.get("qth", "") or row.get("qth_display", ""),
            "qth_grid": row.get("qth_grid", "") or row.get("gridsquare", "") or row.get("grid", ""),
            "qth_state": row.get("qth_state", "") or row.get("state", ""),
            "qth_country": row.get("qth_country", "") or row.get("country", ""),
            "power": str(row.get("power", "") or row.get("tx_pwr", "")),
            "notes": row.get("notes", "") or row.get("comment", ""),
        }
        
        if contact["callsign"]:
            contacts.append(contact)
    
    return contacts


def check_duplicate(conn, contact: dict) -> bool:
    """Check if a contact already exists (same callsign, date, time)."""
    result = conn.execute(
        "SELECT 1 FROM contacts WHERE callsign=? AND date=? AND utc=? LIMIT 1",
        (contact["callsign"], contact["date"], contact["utc"])
    ).fetchone()
    return result is not None

