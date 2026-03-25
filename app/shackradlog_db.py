"""
shackradlog_db.py — SQLite database layer for shackradlog.

Provides:
  db_connect()                    → sqlite3.Connection
  db_insert(conn, contact)        → (row_id, band_recognised)
  db_update(conn, row_id, contact)→ band_recognised
  db_delete(conn, row_id)
  db_fetch(conn, filters)         → list[sqlite3.Row]
  db_worked_counts(conn)          → dict[callsign, count]
  db_stats(conn)                  → dict of aggregate statistics
"""

# ── License ───────────────────────────────────────────────────────────────────
# Copyright (C) 2026  Aron Tkachuk  |  silverbull239@proton.me
# GNU General Public License v3 or later — see <https://www.gnu.org/licenses/>


import sqlite3
from pathlib import Path

from shackradlog_freq import normalize_freq, freq_to_band
from shackradlog_location import parse_location

# ── Database ──────────────────────────────────────────────────────────────────
def db_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            utc         TEXT NOT NULL,
            callsign    TEXT NOT NULL,
            freq        TEXT,
            band        TEXT,
            mode        TEXT,
            rst_sent    TEXT,
            rst_rcvd    TEXT,
            qth         TEXT,
            qth_raw     TEXT,
            qth_grid    TEXT,
            qth_state   TEXT,
            qth_country TEXT,
            qth_dxcc    TEXT,
            qth_itu     INTEGER,
            qth_cq      INTEGER,
            qth_display TEXT,
            qth_resolved INTEGER DEFAULT 0,
            power       TEXT,
            notes       TEXT,
            created     TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # ── Auto-migrate older DBs that are missing the new location columns ───────
    existing = {row[1] for row in conn.execute("PRAGMA table_info(contacts)")}
    new_cols = {
        "qth_raw":      "TEXT",
        "qth_grid":     "TEXT",
        "qth_state":    "TEXT",
        "qth_country":  "TEXT",
        "qth_dxcc":     "TEXT",
        "qth_itu":      "INTEGER",
        "qth_cq":       "INTEGER",
        "qth_display":  "TEXT",
        "qth_resolved": "INTEGER DEFAULT 0",
    }
    for col, col_type in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} {col_type}")
    conn.commit()

    # Add indexes for common filter/search columns
    for col in ("callsign", "date", "band", "mode", "qth_country", "qth_state"):
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{col} ON contacts({col})"
        )
    conn.commit()

    return conn

def db_insert(conn: sqlite3.Connection, c: dict) -> tuple[int, bool]:
    """
    Insert a contact. Returns (new_row_id, band_recognised).
    band_recognised is False when the frequency is non-empty but outside
    all known amateur allocations — the caller should warn the user.
    """
    c["freq"] = normalize_freq(c.get("freq", ""))
    c["band"] = freq_to_band(c.get("freq", ""))
    band_ok   = bool(c["band"]) or not c["freq"]   # ok if band found, or no freq given
    loc = parse_location(c.get("qth", ""), c.get("callsign", ""))
    c.update(loc)
    cur = conn.execute("""
        INSERT INTO contacts
            (date, utc, callsign, freq, band, mode, rst_sent, rst_rcvd,
             qth, qth_raw, qth_grid, qth_state, qth_country, qth_dxcc,
             qth_itu, qth_cq, qth_display, qth_resolved,
             power, notes)
        VALUES
            (:date,:utc,:callsign,:freq,:band,:mode,:rst_sent,:rst_rcvd,
             :qth,:qth_raw,:qth_grid,:qth_state,:qth_country,:qth_dxcc,
             :qth_itu,:qth_cq,:qth_display,:qth_resolved,
             :power,:notes)
    """, c)
    conn.commit()
    return cur.lastrowid, band_ok

def db_update(conn: sqlite3.Connection, row_id: int, c: dict) -> bool:
    """
    Update a contact. Returns band_recognised (False when freq is set but
    outside known amateur allocations).
    """
    c["freq"] = normalize_freq(c.get("freq", ""))
    c["band"] = freq_to_band(c.get("freq", ""))
    band_ok   = bool(c["band"]) or not c["freq"]
    loc = parse_location(c.get("qth", ""), c.get("callsign", ""))
    c.update(loc)
    conn.execute("""
        UPDATE contacts SET
            date=:date, utc=:utc, callsign=:callsign, freq=:freq, band=:band,
            mode=:mode, rst_sent=:rst_sent, rst_rcvd=:rst_rcvd,
            qth=:qth, qth_raw=:qth_raw, qth_grid=:qth_grid,
            qth_state=:qth_state, qth_country=:qth_country, qth_dxcc=:qth_dxcc,
            qth_itu=:qth_itu, qth_cq=:qth_cq,
            qth_display=:qth_display, qth_resolved=:qth_resolved,
            power=:power, notes=:notes
        WHERE id=:id
    """, {**c, "id": row_id})
    conn.commit()
    return band_ok

def db_delete(conn: sqlite3.Connection, row_id: int):
    conn.execute("DELETE FROM contacts WHERE id=?", (row_id,))
    conn.commit()

def db_fetch(conn: sqlite3.Connection, filters: dict | None = None) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params:  list      = []

    if filters:
        if cs := filters.get("callsign"):
            clauses.append("callsign LIKE ?")
            params.append(f"%{cs.upper()}%")
        if mode := filters.get("mode"):
            clauses.append("mode LIKE ?")
            params.append(f"%{mode.upper()}%")
        if band := filters.get("band"):
            clauses.append("band = ?")
            params.append(band)
        if freq := filters.get("freq"):
            clauses.append("freq LIKE ?")
            params.append(f"%{freq}%")
        if country := filters.get("qth_country"):
            clauses.append("qth_country LIKE ?")
            params.append(f"%{country}%")
        if state := filters.get("qth_state"):
            clauses.append("qth_state = ?")
            params.append(state.upper())
        if date_from := filters.get("date_from"):
            clauses.append("date >= ?")
            params.append(date_from)
        if date_to := filters.get("date_to"):
            clauses.append("date <= ?")
            params.append(date_to)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return conn.execute(
        f"SELECT * FROM contacts {where} ORDER BY date DESC, utc DESC", params
    ).fetchall()

def db_worked_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Return {callsign: total_qso_count} for every callsign in the log.
    Single query — safe to call on every refresh.
    """
    rows = conn.execute(
        "SELECT callsign, count(*) as cnt FROM contacts GROUP BY callsign"
    ).fetchall()
    return {r["callsign"]: r["cnt"] for r in rows}


def db_stats(conn: sqlite3.Connection) -> dict:
    # Check if any contacts exist at all
    total = conn.execute("SELECT count(*) FROM contacts").fetchone()[0]
    if not total:
        return {}

    def top(query, params=()):
        return [(r[0], r[1]) for r in conn.execute(query, params).fetchall()]

    modes     = top("SELECT mode, count(*) c FROM contacts "
                    "WHERE mode IS NOT NULL AND mode != '' "
                    "GROUP BY mode ORDER BY c DESC LIMIT 8")
    bands     = top("SELECT band, count(*) c FROM contacts "
                    "WHERE band IS NOT NULL AND band != '' "
                    "GROUP BY band ORDER BY c DESC LIMIT 10")
    top_calls = top("SELECT callsign, count(*) c FROM contacts "
                    "WHERE callsign IS NOT NULL AND callsign != '' "
                    "GROUP BY callsign ORDER BY c DESC LIMIT 5")
    countries = top("SELECT qth_country, count(*) c FROM contacts "
                    "WHERE qth_country IS NOT NULL AND qth_country != '' "
                    "GROUP BY qth_country ORDER BY c DESC LIMIT 8")
    top_qths  = top("SELECT qth_display, count(*) c FROM contacts "
                    "WHERE qth_display IS NOT NULL AND qth_display != '' "
                    "GROUP BY qth_display ORDER BY c DESC LIMIT 5")

    unique_calls = conn.execute(
        "SELECT count(DISTINCT callsign) FROM contacts "
        "WHERE callsign IS NOT NULL AND callsign != ''"
    ).fetchone()[0]

    date_row = conn.execute(
        "SELECT min(date), max(date) FROM contacts WHERE date IS NOT NULL AND date != ''"
    ).fetchone()
    first_qso = date_row[0] or "—"
    last_qso  = date_row[1] or "—"

    unresolved = conn.execute(
        "SELECT count(*) FROM contacts "
        "WHERE qth_resolved = 0 AND (qth IS NOT NULL AND qth != '' "
        "OR qth_raw IS NOT NULL AND qth_raw != '')"
    ).fetchone()[0]

    return {
        "total":         total,
        "unique_calls":  unique_calls,
        "modes":         modes,
        "bands":         bands,
        "top_calls":     top_calls,
        "top_countries": countries,
        "top_qths":      top_qths,
        "first_qso":     first_qso,
        "last_qso":      last_qso,
        "unresolved":    unresolved,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FREQUENCIES / REPEATERS DATABASE
# ══════════════════════════════════════════════════════════════════════════════

FREQ_TYPES = [
    "simplex",
    "fm_repeater",
    "gmrs_repeater",
    "dmr_repeater",
    "dstar_repeater",
    "fusion_repeater",
    "p25",
]

def freq_db_init(conn: sqlite3.Connection):
    """Create the frequencies table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS frequencies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            -- Basic info
            entry_type      TEXT NOT NULL,
            name            TEXT NOT NULL,
            callsign        TEXT,
            service         TEXT,
            -- Frequency settings
            rx_freq         TEXT,
            tx_freq         TEXT,
            offset          TEXT,
            offset_dir      TEXT,
            band            TEXT,
            -- Tone settings
            tx_tone_type    TEXT,
            tx_tone         TEXT,
            rx_tone_type    TEXT,
            rx_tone         TEXT,
            -- Power & bandwidth
            power           TEXT,
            bandwidth       TEXT,
            -- Digital mode settings (DMR)
            color_code      TEXT,
            time_slot       TEXT,
            talk_group      TEXT,
            -- Digital mode settings (D-STAR)
            reflector       TEXT,
            ur_call         TEXT,
            rpt1            TEXT,
            rpt2            TEXT,
            -- Digital mode settings (Fusion)
            dg_id           TEXT,
            fusion_mode     TEXT,
            -- Digital mode settings (P25)
            nac             TEXT,
            -- Location
            city            TEXT,
            state           TEXT,
            county          TEXT,
            grid            TEXT,
            latitude        REAL,
            longitude       REAL,
            elevation       TEXT,
            coverage        TEXT,
            -- Operational info
            status          TEXT DEFAULT 'active',
            owner           TEXT,
            net_schedule    TEXT,
            linked_to       TEXT,
            echolink        TEXT,
            -- Programming/Organization
            channel_num     TEXT,
            bank            TEXT,
            scan            INTEGER DEFAULT 1,
            priority        INTEGER DEFAULT 0,
            skip            INTEGER DEFAULT 0,
            -- Notes
            notes           TEXT,
            -- Metadata
            created         TEXT DEFAULT (datetime('now')),
            updated         TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_freq_type ON frequencies(entry_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_freq_name ON frequencies(name)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_freq_service ON frequencies(service)
    """)
    conn.commit()


def freq_db_insert(conn: sqlite3.Connection, f: dict) -> int:
    """Insert a frequency entry. Returns new row ID."""
    # Auto-detect band from rx_freq if not provided
    if not f.get("band") and f.get("rx_freq"):
        f["band"] = freq_to_band(f["rx_freq"])
    
    # Normalize frequencies
    if f.get("rx_freq"):
        f["rx_freq"] = normalize_freq(f["rx_freq"])
    if f.get("tx_freq"):
        f["tx_freq"] = normalize_freq(f["tx_freq"])
    
    cols = [
        "entry_type", "name", "callsign", "service",
        "rx_freq", "tx_freq", "offset", "offset_dir", "band",
        "tx_tone_type", "tx_tone", "rx_tone_type", "rx_tone",
        "power", "bandwidth",
        "color_code", "time_slot", "talk_group",
        "reflector", "ur_call", "rpt1", "rpt2",
        "dg_id", "fusion_mode", "nac",
        "city", "state", "county", "grid", "latitude", "longitude",
        "elevation", "coverage",
        "status", "owner", "net_schedule", "linked_to", "echolink",
        "channel_num", "bank", "scan", "priority", "skip",
        "notes"
    ]
    
    # Build dict with defaults
    data = {c: f.get(c, "") for c in cols}
    data["scan"] = f.get("scan", 1)
    data["priority"] = f.get("priority", 0)
    data["skip"] = f.get("skip", 0)
    
    placeholders = ", ".join([f":{c}" for c in cols])
    col_names = ", ".join(cols)
    
    cur = conn.execute(f"""
        INSERT INTO frequencies ({col_names})
        VALUES ({placeholders})
    """, data)
    conn.commit()
    return cur.lastrowid


def freq_db_update(conn: sqlite3.Connection, row_id: int, f: dict):
    """Update a frequency entry."""
    # Auto-detect band
    if not f.get("band") and f.get("rx_freq"):
        f["band"] = freq_to_band(f["rx_freq"])
    
    # Normalize frequencies
    if f.get("rx_freq"):
        f["rx_freq"] = normalize_freq(f["rx_freq"])
    if f.get("tx_freq"):
        f["tx_freq"] = normalize_freq(f["tx_freq"])
    
    cols = [
        "entry_type", "name", "callsign", "service",
        "rx_freq", "tx_freq", "offset", "offset_dir", "band",
        "tx_tone_type", "tx_tone", "rx_tone_type", "rx_tone",
        "power", "bandwidth",
        "color_code", "time_slot", "talk_group",
        "reflector", "ur_call", "rpt1", "rpt2",
        "dg_id", "fusion_mode", "nac",
        "city", "state", "county", "grid", "latitude", "longitude",
        "elevation", "coverage",
        "status", "owner", "net_schedule", "linked_to", "echolink",
        "channel_num", "bank", "scan", "priority", "skip",
        "notes"
    ]
    
    set_clause = ", ".join([f"{c}=:{c}" for c in cols])
    f["id"] = row_id
    f["updated"] = "datetime('now')"
    
    conn.execute(f"""
        UPDATE frequencies SET {set_clause}, updated=datetime('now')
        WHERE id=:id
    """, f)
    conn.commit()


def freq_db_delete(conn: sqlite3.Connection, row_id: int):
    """Delete a frequency entry."""
    conn.execute("DELETE FROM frequencies WHERE id=?", (row_id,))
    conn.commit()


def freq_db_fetch(conn: sqlite3.Connection, filters: dict | None = None) -> list[sqlite3.Row]:
    """Fetch frequency entries with optional filters."""
    clauses: list[str] = []
    params: list = []
    
    if filters:
        if entry_type := filters.get("entry_type"):
            clauses.append("entry_type = ?")
            params.append(entry_type)
        if name := filters.get("name"):
            clauses.append("name LIKE ?")
            params.append(f"%{name}%")
        if service := filters.get("service"):
            clauses.append("service = ?")
            params.append(service)
        if band := filters.get("band"):
            clauses.append("band = ?")
            params.append(band)
        if city := filters.get("city"):
            clauses.append("city LIKE ?")
            params.append(f"%{city}%")
        if state := filters.get("state"):
            clauses.append("state = ?")
            params.append(state.upper())
    
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return conn.execute(
        f"SELECT * FROM frequencies {where} ORDER BY name ASC", params
    ).fetchall()


def freq_db_get(conn: sqlite3.Connection, row_id: int) -> sqlite3.Row | None:
    """Get a single frequency entry by ID."""
    return conn.execute(
        "SELECT * FROM frequencies WHERE id=?", (row_id,)
    ).fetchone()


