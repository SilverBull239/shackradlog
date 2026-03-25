#!/usr/bin/env python3
"""
shackradlog_geo.py — Location resolution for shackradlog.py

Self-contained module. No third-party dependencies.
Handles:
  - GeoNames cities500 download, processing, monthly refresh
  - City / province / country lookup from free text
  - Maidenhead grid square calculation from lat/lon
  - Trash/recycle bin handling cross-platform
  - Progress display for downloads (only shown when actually downloading)

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

import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ─────────────────────────────────────────────────────────────────────
GEO_DIR   = Path.home() / ".shackradlog"
GEO_DB    = GEO_DIR / "shackradlog_geo.db"
GEO_META  = GEO_DIR / "shackradlog_geo_meta.json"
GEO_DIR.mkdir(parents=True, exist_ok=True)

GEONAMES_URL   = "https://download.geonames.org/export/dump/cities500.zip"
COUNTRY_URL    = "https://download.geonames.org/export/dump/countryInfo.txt"
ADMIN1_URL     = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
REFRESH_DAYS   = 30

# ── Maidenhead grid square from lat/lon ───────────────────────────────────────
def latlon_to_grid(lat: float, lon: float, precision: int = 4) -> str:
    """
    Convert lat/lon to Maidenhead grid square.
    precision=4 → 4-char (e.g. EM35), precision=6 → 6-char (e.g. EM35ab)

    Field letters are clamped to A-R (indices 0-17) so that boundary
    coordinates (lon=180, lat=90) produce valid grid squares.
    """
    lon += 180.0
    lat  += 90.0
    field_lon = min(int(lon / 20), 17)   # clamp to A–R (0–17)
    field_lat = min(int(lat / 10), 17)   # clamp to A–R (0–17)
    sq_lon    = int((lon % 20) / 2)
    sq_lat    = int(lat % 10)
    grid = (
        chr(ord('A') + field_lon) +
        chr(ord('A') + field_lat) +
        str(sq_lon) +
        str(sq_lat)
    )
    if precision >= 6:
        sub_lon = int(((lon % 20) % 2) / (2/24))
        sub_lat = int(((lat % 10) % 1) / (1/24))
        grid += chr(ord('a') + sub_lon) + chr(ord('a') + sub_lat)
    return grid


# ── Trash / recycle bin ───────────────────────────────────────────────────────
def move_to_trash(path: Path) -> tuple[bool, str]:
    """
    Attempt to move a file to the system trash/recycle bin.
    Returns (success, message).
    Falls back to permanent delete if trash unavailable.
    If neither works, retains the file and returns an error message with path.
    """
    p = Path(path)
    if not p.exists():
        return (True, "File not found — nothing to remove.")

    # ── macOS ──────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 f'tell application "Finder" to delete POSIX file "{p.resolve()}"'],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                return (True, f"Moved to Trash: {p.name}")
        except Exception:
            pass
        # Fallback: move to ~/.Trash manually
        try:
            trash = Path.home() / ".Trash"
            trash.mkdir(exist_ok=True)
            dest = trash / p.name
            # Avoid collision
            if dest.exists():
                dest = trash / f"{p.stem}_{int(time.time())}{p.suffix}"
            shutil.move(str(p), str(dest))
            return (True, f"Moved to Trash: {p.name}")
        except Exception as e:
            pass

    # ── Windows ────────────────────────────────────────────────────────────
    elif sys.platform == "win32":
        try:
            import ctypes
            # SHFileOperation with FO_DELETE + FOF_ALLOWUNDO = recycle
            class SHFILEOPSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hwnd",   ctypes.c_void_p),
                    ("wFunc",  ctypes.c_uint),
                    ("pFrom",  ctypes.c_wchar_p),
                    ("pTo",    ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", ctypes.c_bool),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p),
                ]
            FO_DELETE   = 3
            FOF_ALLOWUNDO     = 0x0040
            FOF_NOCONFIRMATION= 0x0010
            FOF_SILENT        = 0x0004
            op = SHFILEOPSTRUCT()
            op.wFunc  = FO_DELETE
            op.pFrom  = str(p.resolve()) + "\0\0"
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
            ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if ret == 0:
                return (True, f"Moved to Recycle Bin: {p.name}")
        except Exception:
            pass

    # ── Linux — try common trash implementations ───────────────────────────
    else:
        # XDG trash spec
        try:
            import subprocess
            # gio trash (GNOME)
            result = subprocess.run(
                ["gio", "trash", str(p.resolve())],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                return (True, f"Moved to Trash: {p.name}")
        except Exception:
            pass
        try:
            import subprocess
            # trash-put (trash-cli package)
            result = subprocess.run(
                ["trash-put", str(p.resolve())],
                capture_output=True, timeout=10
            )
            if result.returncode == 0:
                return (True, f"Moved to Trash: {p.name}")
        except Exception:
            pass
        # Manual XDG trash
        try:
            xdg_trash = Path.home() / ".local" / "share" / "Trash"
            files_dir = xdg_trash / "files"
            info_dir  = xdg_trash / "info"
            files_dir.mkdir(parents=True, exist_ok=True)
            info_dir.mkdir(parents=True, exist_ok=True)
            dest = files_dir / p.name
            if dest.exists():
                dest = files_dir / f"{p.stem}_{int(time.time())}{p.suffix}"
            shutil.move(str(p), str(dest))
            info = info_dir / f"{dest.name}.trashinfo"
            info.write_text(
                f"[Trash Info]\nPath={p.resolve()}\n"
                f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
            )
            return (True, f"Moved to Trash: {p.name}")
        except Exception:
            pass

    # ── Universal fallback: permanent delete ───────────────────────────────
    try:
        p.unlink()
        return (True, f"Deleted (trash unavailable): {p.name}")
    except Exception as e:
        return (False,
                f"Could not delete or trash the file.\n"
                f"Please remove it manually: {p.resolve()}\n"
                f"Error: {e}")


# ── Metadata helpers ──────────────────────────────────────────────────────────
def _read_meta() -> dict:
    try:
        return json.loads(GEO_META.read_text())
    except Exception:
        return {}

def _write_meta(data: dict):
    GEO_META.write_text(json.dumps(data, indent=2))

def _needs_refresh() -> bool:
    if not GEO_DB.exists():
        return True
    meta = _read_meta()
    last = meta.get("last_updated")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        now_dt  = datetime.now(timezone.utc)
        # Make both offset-aware for comparison
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        age = (now_dt - last_dt).days
        return age >= REFRESH_DAYS
    except Exception:
        return True


# ── Download with progress ────────────────────────────────────────────────────
def _download(url: str, dest: Path, label: str,
              progress_cb=None) -> bool:
    """
    Download url → dest, calling progress_cb(pct, speed_kbps) periodically.
    Returns True on success.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "shackradlog/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            chunk  = 65536
            received = 0
            t_start  = time.time()
            with open(dest, "wb") as f:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    received += len(data)
                    if progress_cb and total:
                        pct   = received / total * 100
                        elapsed = max(0.001, time.time() - t_start)
                        speed   = received / elapsed / 1024
                        progress_cb(pct, speed)
        return True
    except Exception as e:
        if dest.exists():
            dest.unlink()
        return False


# ── Build geo DB from downloaded files ────────────────────────────────────────
def _build_db(zip_path: Path, country_path: Path, admin1_path: Path,
              progress_cb=None) -> tuple[bool, str]:
    """
    Parse GeoNames files and build shackradlog_geo.db.
    Returns (success, message).
    """
    tmp_db = GEO_DB.with_suffix(".tmp")
    try:
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # ── Country table ──────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE countries (
                iso2        TEXT PRIMARY KEY,
                iso3        TEXT,
                name        TEXT,
                continent   TEXT,
                capital     TEXT,
                population  INTEGER
            )
        """)
        country_map: dict[str, str] = {}   # iso2 → name
        if country_path.exists():
            with open(country_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) < 5:
                        continue
                    iso2, iso3 = parts[0], parts[1]
                    name = parts[4]
                    continent = parts[8] if len(parts) > 8 else ""
                    capital   = parts[5] if len(parts) > 5 else ""
                    try:
                        pop = int(parts[7]) if len(parts) > 7 else 0
                    except ValueError:
                        pop = 0
                    country_map[iso2] = name
                    conn.execute(
                        "INSERT OR IGNORE INTO countries VALUES (?,?,?,?,?,?)",
                        (iso2, iso3, name, continent, capital, pop)
                    )
        conn.commit()

        # ── Admin1 (state/province) table ──────────────────────────────────
        conn.execute("""
            CREATE TABLE admin1 (
                code        TEXT PRIMARY KEY,
                name        TEXT,
                name_ascii  TEXT
            )
        """)
        admin1_map: dict[str, str] = {}   # "US.AR" → "Arkansas"
        if admin1_path.exists():
            with open(admin1_path, encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) < 2:
                        continue
                    code, name = parts[0], parts[1]
                    ascii_name = parts[2] if len(parts) > 2 else name
                    admin1_map[code] = name
                    conn.execute(
                        "INSERT OR IGNORE INTO admin1 VALUES (?,?,?)",
                        (code, name, ascii_name)
                    )
        conn.commit()

        # ── Cities table ───────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE cities (
                geonameid   INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                name_ascii  TEXT,
                alt_names   TEXT,
                lat         REAL,
                lon         REAL,
                country     TEXT,
                admin1_code TEXT,
                admin1_name TEXT,
                population  INTEGER,
                grid4       TEXT,
                grid6       TEXT
            )
        """)

        # GeoNames cities500.txt columns (tab-separated):
        # 0:geonameid 1:name 2:asciiname 3:alternatenames
        # 4:latitude 5:longitude 6:feature_class 7:feature_code
        # 8:country_code 9:cc2 10:admin1_code 11:admin2_code
        # 12:admin3_code 13:admin4_code 14:population 15:elevation
        # 16:dem 17:timezone 18:modification_date

        batch = []
        batch_size = 5000
        total_lines = 0

        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if n.endswith(".txt")]
            if not names:
                return (False, "No .txt file found in ZIP")
            txt_name = names[0]

            # Count lines for progress
            if progress_cb:
                with zf.open(txt_name) as f:
                    total_lines = sum(1 for _ in f)

            with zf.open(txt_name) as raw:
                reader = io.TextIOWrapper(raw, encoding="utf-8")
                processed = 0
                for line in reader:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 15:
                        continue
                    try:
                        gid   = int(parts[0])
                        name  = parts[1]
                        ascii_name = parts[2]
                        alts  = parts[3]
                        lat   = float(parts[4])
                        lon   = float(parts[5])
                        cc    = parts[8]
                        a1    = parts[10]
                        pop   = int(parts[14]) if parts[14] else 0
                    except (ValueError, IndexError):
                        continue

                    a1_name = admin1_map.get(f"{cc}.{a1}", "")
                    grid4   = latlon_to_grid(lat, lon, 4)
                    grid6   = latlon_to_grid(lat, lon, 6)

                    batch.append((gid, name, ascii_name, alts,
                                  lat, lon, cc, a1, a1_name,
                                  pop, grid4, grid6))
                    processed += 1

                    if len(batch) >= batch_size:
                        conn.executemany(
                            "INSERT OR IGNORE INTO cities VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?)", batch
                        )
                        conn.commit()
                        batch.clear()
                        if progress_cb and total_lines:
                            progress_cb(processed / total_lines * 100)

        if batch:
            conn.executemany(
                "INSERT OR IGNORE INTO cities VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?)", batch
            )
            conn.commit()

        # ── Indexes ────────────────────────────────────────────────────────
        if progress_cb:
            progress_cb(95)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_city_name    ON cities(name_ascii)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_city_country ON cities(country)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_city_admin1  ON cities(admin1_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_city_grid4   ON cities(grid4)")
        conn.commit()
        conn.close()

        # Atomically replace the old DB
        if GEO_DB.exists():
            GEO_DB.unlink()
        tmp_db.rename(GEO_DB)

        if progress_cb:
            progress_cb(100)

        return (True, "Geo database built successfully.")

    except Exception as e:
        conn.close()
        if tmp_db.exists():
            tmp_db.unlink()
        return (False, f"Error building geo database: {e}")


# ── Main refresh entry point ──────────────────────────────────────────────────
def ensure_geo_db(progress_cb=None) -> tuple[bool, str]:
    """
    Check if geo DB needs refreshing. If so, download and rebuild.
    progress_cb(stage: str, pct: float, speed_kbps: float | None)
    Returns (success, message).
    Only downloads if needed — silent otherwise.
    """
    if not _needs_refresh():
        return (True, "Geo database is current.")

    # We need to download — start showing progress from here
    zip_path     = GEO_DIR / "cities500.zip"
    country_path = GEO_DIR / "countryInfo.txt"
    admin1_path  = GEO_DIR / "admin1CodesASCII.txt"

    try:
        # Download cities500.zip
        def cities_progress(pct, speed=None):
            if progress_cb:
                progress_cb("download_cities", pct, speed)

        if progress_cb:
            progress_cb("download_cities", 0, None)

        ok = _download(GEONAMES_URL, zip_path, "cities500.zip", cities_progress)
        if not ok:
            return (False, "Failed to download cities500.zip — check internet connection.")

        # Download country info
        if progress_cb:
            progress_cb("download_meta", 0, None)
        _download(COUNTRY_URL, country_path, "countryInfo.txt")
        _download(ADMIN1_URL,  admin1_path,  "admin1CodesASCII.txt")

        # Build DB
        def build_progress(pct, speed=None):
            if progress_cb:
                progress_cb("build", pct, None)

        if progress_cb:
            progress_cb("build", 0, None)

        success, msg = _build_db(zip_path, country_path, admin1_path, build_progress)

        # Clean up downloaded files
        for f in [country_path, admin1_path]:
            if f.exists():
                f.unlink()

        # Trash / delete the zip
        trash_ok, trash_msg = move_to_trash(zip_path)
        if not trash_ok:
            msg += f"\n\n{trash_msg}"

        if success:
            _write_meta({
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source": GEONAMES_URL,
                "trash_result": trash_msg,
            })

        return (success, msg)

    except Exception as e:
        # Clean up any partial downloads
        for f in [zip_path, country_path, admin1_path]:
            try:
                if Path(f).exists():
                    Path(f).unlink()
            except Exception:
                pass
        return (False, f"Geo update failed: {e}")


# ── Lookup API ────────────────────────────────────────────────────────────────
def _geo_conn() -> sqlite3.Connection | None:
    if not GEO_DB.exists():
        return None
    try:
        conn = sqlite3.connect(GEO_DB)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _row_to_city(row, country_name: str) -> dict:
    """Convert a DB row + resolved country name to a city dict."""
    return {
        "city":         row["name"],
        "admin1_code":  row["admin1_code"],
        "admin1_name":  row["admin1_name"] or "",
        "country_iso2": row["country"],
        "country":      country_name,
        "lat":          row["lat"],
        "lon":          row["lon"],
        "grid4":        row["grid4"],
        "grid6":        row["grid6"],
        "population":   row["population"],
    }


def _query_cities(conn, name: str, country_hint: str = "",
                  admin1_hint: str = "") -> list:
    """Raw city rows for name, ordered by population desc."""
    results = []
    if admin1_hint:
        rows = conn.execute(
            "SELECT * FROM cities WHERE name_ascii = ? COLLATE NOCASE "
            "AND admin1_code = ? ORDER BY population DESC LIMIT 10",
            (name, admin1_hint.upper())
        ).fetchall()
        if rows:
            results.extend(rows)
    if country_hint and not results:
        rows = conn.execute(
            "SELECT * FROM cities WHERE name_ascii = ? COLLATE NOCASE "
            "AND country = ? ORDER BY population DESC LIMIT 10",
            (name, country_hint.upper())
        ).fetchall()
        if rows:
            results.extend(rows)
    if not results:
        rows = conn.execute(
            "SELECT * FROM cities WHERE name_ascii = ? COLLATE NOCASE "
            "ORDER BY population DESC LIMIT 50", (name,)
        ).fetchall()
        results.extend(rows)
    if not results:
        rows = conn.execute(
            "SELECT * FROM cities WHERE alt_names LIKE ? "
            "ORDER BY population DESC LIMIT 50", (f"%{name}%",)
        ).fetchall()
        results.extend(rows)
    return results


def _best_row(rows: list, country_hint: str = "", admin1_hint: str = ""):
    """Pick the single best row from a list, applying hints."""
    if not rows:
        return None
    filtered = list(rows)
    if country_hint:
        cc = [r for r in filtered if r["country"] == country_hint.upper()]
        if cc:
            filtered = cc
    if admin1_hint:
        a1 = [r for r in filtered
              if r["admin1_code"] == admin1_hint.upper() or
              (r["admin1_name"] or "").lower() == admin1_hint.lower()]
        if a1:
            filtered = a1
    return max(filtered, key=lambda r: r["population"] or 0)


def _resolve_country(conn, iso2: str) -> str:
    row = conn.execute(
        "SELECT name FROM countries WHERE iso2 = ?", (iso2,)
    ).fetchone()
    return row["name"] if row else iso2


def lookup_city(city_name: str, country_hint: str = "",
                admin1_hint: str = "") -> dict | None:
    """
    Look up a city by name. Returns best match as dict or None.
    Prefers matches in country_hint or admin1_hint if provided.
    """
    conn = _geo_conn()
    if not conn:
        return None
    try:
        name_clean = city_name.strip()
        if not name_clean:
            return None
        rows = _query_cities(conn, name_clean, country_hint, admin1_hint)
        row  = _best_row(rows, country_hint, admin1_hint)
        if not row:
            return None
        return _row_to_city(row, _resolve_country(conn, row["country"]))
    except Exception:
        return None
    finally:
        conn.close()


# Ambiguity threshold: if the top-2 cities have populations within this
# ratio of each other AND are in different admin1/country, offer a picker.
_AMBIGUITY_RATIO = 5.0   # top city must be >5× more populous to be "unambiguous"
_AMBIGUITY_MIN_POP = 5000  # ignore tiny places for ambiguity purposes


def lookup_city_candidates(city_name: str, country_hint: str = "",
                           admin1_hint: str = "",
                           max_results: int = 6) -> tuple[dict | None, list[dict], bool]:
    """
    Look up a city and return (best, candidates, is_ambiguous).

    best         — the single best match (or None if nothing found)
    candidates   — list of up to max_results dicts for disambiguation picker
                   (only populated when is_ambiguous is True)
    is_ambiguous — True when multiple plausible cities exist and no hint
                   narrows it down to one clear winner

    Ambiguity criteria:
      - 2+ results in DIFFERENT admin1 regions or countries
      - The top result is not more than _AMBIGUITY_RATIO× more populous
        than the second result (both above _AMBIGUITY_MIN_POP)
      - No admin1_hint was provided (a state hint = user already disambiguated)
    """
    conn = _geo_conn()
    if not conn:
        return None, [], False
    try:
        name_clean = city_name.strip()
        if not name_clean:
            return None, [], False

        rows = _query_cities(conn, name_clean, country_hint, admin1_hint)
        if not rows:
            return None, [], False

        best_row = _best_row(rows, country_hint, admin1_hint)
        if not best_row:
            return None, [], False

        best_city = _row_to_city(best_row, _resolve_country(conn, best_row["country"]))

        # If a state hint was given, the user already disambiguated — not ambiguous
        if admin1_hint:
            return best_city, [], False

        # Collect distinct (admin1, country) combos above minimum population
        seen: set[tuple] = set()
        distinct: list = []
        for r in rows:
            pop = r["population"] or 0
            if pop < _AMBIGUITY_MIN_POP:
                continue
            key = (r["admin1_code"], r["country"])
            if key not in seen:
                seen.add(key)
                distinct.append(r)
            if len(distinct) >= max_results:
                break

        if len(distinct) < 2:
            return best_city, [], False

        # Check population ratio between top two distinct results
        pop0 = distinct[0]["population"] or 1
        pop1 = distinct[1]["population"] or 1
        if pop0 / pop1 > _AMBIGUITY_RATIO:
            # First result is dominant — not ambiguous
            return best_city, [], False

        # Ambiguous — build candidate list
        candidates = [
            _row_to_city(r, _resolve_country(conn, r["country"]))
            for r in distinct
        ]
        return best_city, candidates, True

    except Exception:
        return None, [], False
    finally:
        conn.close()


def lookup_admin1(name: str, country_iso2: str = "") -> dict | None:
    """
    Look up a state/province by name or code.
    Returns dict with code, name, country or None.
    """
    conn = _geo_conn()
    if not conn:
        return None
    try:
        name_clean = name.strip().upper()
        if not name_clean:
            return None

        # Build search: "US.AR" style or just name match
        if country_iso2:
            # Try exact code match: US.AR
            row = conn.execute(
                "SELECT * FROM admin1 WHERE code = ?",
                (f"{country_iso2.upper()}.{name_clean}",)
            ).fetchone()
            if row:
                return {"code": row["code"], "name": row["name"]}

        # Name match
        rows = conn.execute(
            "SELECT * FROM admin1 WHERE name_ascii LIKE ? COLLATE NOCASE LIMIT 10",
            (f"%{name.strip()}%",)
        ).fetchall()

        if country_iso2:
            rows = [r for r in rows if r["code"].startswith(country_iso2.upper() + ".")]

        if rows:
            return {"code": rows[0]["code"], "name": rows[0]["name"]}
        return None
    except Exception:
        return None
    finally:
        conn.close()


def geo_available() -> bool:
    """Return True if the geo database exists and is queryable."""
    return GEO_DB.exists()


def geo_stats() -> dict:
    """Return stats about the geo database for display."""
    meta = _read_meta()
    conn = _geo_conn()
    stats = {
        "available":    geo_available(),
        "last_updated": meta.get("last_updated", "never"),
        "city_count":   0,
        "country_count":0,
    }
    if conn:
        try:
            stats["city_count"]    = conn.execute("SELECT count(*) FROM cities").fetchone()[0]
            stats["country_count"] = conn.execute("SELECT count(*) FROM countries").fetchone()[0]
        except Exception:
            pass
        conn.close()
    return stats


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    def progress(stage, pct, speed=None):
        stages = {
            "download_cities": "Downloading cities500.zip",
            "download_meta":   "Downloading country/admin data",
            "build":           "Building database",
        }
        label = stages.get(stage, stage)
        bar   = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        speed_str = f"  {speed:.0f} KB/s" if speed else ""
        print(f"\r  {label}: [{bar}] {pct:5.1f}%{speed_str}   ", end="", flush=True)
        if pct >= 100:
            print()

    print("shackradlog_geo standalone test")
    print(f"GEO_DB: {GEO_DB}")
    print()

    if "--force" in sys.argv:
        # Force refresh by removing meta
        if GEO_META.exists(): GEO_META.unlink()
        if GEO_DB.exists():   GEO_DB.unlink()

    ok, msg = ensure_geo_db(progress)
    print(f"ensure_geo_db: {'OK' if ok else 'FAILED'} — {msg}")
    print()

    if ok and geo_available():
        stats = geo_stats()
        print(f"Cities: {stats['city_count']:,}")
        print(f"Countries: {stats['country_count']}")
        print(f"Last updated: {stats['last_updated']}")
        print()

        tests = [
            ("Fayetteville", "US", "AR"),
            ("Tokyo",        "JP", ""),
            ("London",       "GB", ""),
            ("Sydney",       "AU", ""),
            ("Toronto",      "CA", ""),
            ("Berlin",       "DE", ""),
            ("Paris",        "FR", ""),
        ]
        print(f"  {'City':<16} {'Country':<20} {'Admin1':<20} {'Grid':<8} {'Lat/Lon'}")
        print("  " + "─" * 75)
        for city, cc, a1 in tests:
            r = lookup_city(city, cc, a1)
            if r:
                print(f"  {r['city']:<16} {r['country']:<20} {r['admin1_name']:<20} "
                      f"{r['grid6']:<8} {r['lat']:.2f},{r['lon']:.2f}")
            else:
                print(f"  {city:<16} NOT FOUND")
