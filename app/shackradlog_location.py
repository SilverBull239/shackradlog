"""
shackradlog_location.py — Location parsing for shackradlog.

Provides:
  parse_grid(text)         → Maidenhead grid square string or ''
  parse_us_state(text)     → 2-letter US state abbreviation or ''
  callsign_to_dxcc(cs)     → (entity, itu_zone, cq_zone) or ('', 0, 0)
  parse_location(qth, cs)  → dict of qth_* fields
  _fmt_location(...)       → human-readable location string

The DXCC prefix table is loaded from shackradlog_dxcc.csv at import time.
"""

# ── License ───────────────────────────────────────────────────────────────────
# Copyright (C) 2026  Aron Tkachuk  |  silverbull239@proton.me
# GNU General Public License v3 or later — see <https://www.gnu.org/licenses/>


import re
from pathlib import Path

# ── Optional geo module (shackradlog_geo.py) ───────────────────────────────────────
try:
    import shackradlog_geo as _geo
    GEO_AVAILABLE = True
except ImportError:
    _geo = None
    GEO_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# ── Location parsing ──────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# ── Maidenhead grid square ────────────────────────────────────────────────────
_GRID_RE = re.compile(r'^[A-Ra-r]{2}[0-9]{2}([A-Xa-x]{2}([0-9]{2})?)?$')

def parse_grid(text: str) -> str:
    """Return uppercase grid square if text looks like one, else ''."""
    t = text.strip()
    if _GRID_RE.match(t):
        return t.upper()
    # Also accept grid embedded in text like "Grid: EM35ab"
    m = re.search(r'\b([A-Ra-r]{2}[0-9]{2}(?:[A-Xa-x]{2}(?:[0-9]{2})?)?)\b', t)
    return m.group(1).upper() if m else ""

# ── US states ─────────────────────────────────────────────────────────────────
_STATES: dict[str, str] = {
    # abbreviation → full name
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas",
    "CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware",
    "FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho",
    "IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas",
    "KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada",
    "NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York",
    "NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma",
    "OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina",
    "SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah",
    "VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia",
    "WI":"Wisconsin","WY":"Wyoming",
    # DC + territories
    "DC":"District of Columbia","PR":"Puerto Rico","VI":"US Virgin Islands",
    "GU":"Guam","AS":"American Samoa","MP":"Northern Mariana Islands",
}
# Reverse map: lowercase full name → abbreviation
_STATE_NAME_TO_ABBR: dict[str, str] = {v.lower(): k for k, v in _STATES.items()}
# Common informal abbreviations / misspellings
_STATE_ALIASES: dict[str, str] = {
    "calif":"CA","cali":"CA","cal":"CA","tex":"TX","tenn":"TN","tenn.":"TN",
    "fla":"FL","fla.":"FL","ariz":"AZ","ariz.":"AZ","mich":"MI","mich.":"MI",
    "minn":"MN","minn.":"MN","miss":"MS","miss.":"MS","mont":"MT","mont.":"MT",
    "nebr":"NE","nebr.":"NE","okla":"OK","okla.":"OK","oreg":"OR","oreg.":"OR",
    "penn":"PA","penn.":"PA","ark.":"AR","colo":"CO","colo.":"CO",
    "conn":"CT","conn.":"CT","dela":"DE","dela.":"DE","geo":"GA","geo.":"GA",
    "ill":"IL","ill.":"IL","ind":"IN","ind.":"IN","kan":"KS","kan.":"KS",
    "kans":"KS","kans.":"KS","ken":"KY","ken.":"KY","mass":"MA","mass.":"MA",
    "wash":"WA","wash.":"WA","wis":"WI","wis.":"WI","wyo":"WY","wyo.":"WY",
    "nev":"NV","nev.":"NV","ore":"OR","ore.":"OR",
}

def parse_us_state(text: str) -> str:
    """
    Return 2-letter US state abbreviation if found anywhere in text, else ''.
    Checks abbreviations, full names, and common aliases.

    2-letter abbreviation matching requires UPPERCASE to prevent false positives
    on common English words ('or' → OR/Oregon, 'in' → IN/Indiana, etc.).
    Full-name and alias matches are case-insensitive.
    """
    t = text.strip()

    # Check for bare 2-letter abbreviation (word boundary) — UPPERCASE only.
    # Lowercase 'or', 'in', 'me', 'hi', 'ok', etc. are English words, not states.
    for word in re.findall(r'\b[A-Z]{2}\b', t):
        if word in _STATES:
            return word

    tl = t.lower()

    # Full name match (case-insensitive)
    for name, abbr in _STATE_NAME_TO_ABBR.items():
        if name in tl:
            return abbr

    # Alias match (case-insensitive)
    for alias, abbr in _STATE_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', tl):
            return abbr

    return ""

# ── DXCC prefix table ─────────────────────────────────────────────────────────
# Data lives in shackradlog_dxcc.csv (prefix, entity, itu_zone, cq_zone).
# Loaded at import time; sorted longest-prefix-first for greedy callsign matching.
def _load_dxcc_csv() -> tuple[list, dict]:
    import csv as _csv
    raw: list[tuple[str, str, int, int]] = []
    _path = Path(__file__).with_name("shackradlog_dxcc.csv")
    try:
        with open(_path, newline="", encoding="utf-8") as _f:
            for row in _csv.DictReader(_f):
                raw.append((row["prefix"], row["entity"], int(row["itu_zone"]), int(row["cq_zone"])))
    except FileNotFoundError:
        import sys
        msg = ("ERROR: shackradlog_dxcc.csv not found. "
               "Expected it next to: " + str(_path) + ". "
               "Make sure shackradlog_dxcc.csv is in the same folder as the other shackradlog files.")
        sys.exit(msg)
    except Exception as e:
        import sys
        sys.exit("ERROR: Could not load shackradlog_dxcc.csv: " + str(e))
    lookup: dict[str, tuple[str, int, int]] = {}
    for pfx, entity, itu, cq in sorted(raw, key=lambda x: -len(x[0])):
        if pfx not in lookup:
            lookup[pfx] = (entity, itu, cq)
    return raw, lookup

_DXCC_RAW, _DXCC = _load_dxcc_csv()

# Pre-built frozenset of all DXCC entity names for O(1) lookup in parse_location
_ENTITY_NAMES: frozenset = frozenset(ent.lower() for _, (ent, _, _) in _DXCC.items())

# ── Module-level derived tables (built once at import, used by parse_location) ─

# Fast O(1) set of all DXCC entity names in lowercase.
# Used by the geo-lookup guard to detect pure country-name inputs.
_ENTITY_NAMES: frozenset[str] = frozenset(
    ent.lower() for _, (ent, _, _) in _DXCC.items()
)

# Unique DXCC entities sorted longest-name-first.
# Used for QTH text scanning so that "Romania" beats "Oman",
# "South Sudan" beats "Sudan", "Northern Ireland" beats "Ireland", etc.
_DXCC_ENTITY_LIST: list[tuple[str, int, int]] = []
_seen_entities: set[str] = set()
for _pfx, (_ent, _itu, _cq) in sorted(
        _DXCC.items(), key=lambda kv: -len(kv[1][0])):
    if _ent not in _seen_entities:
        _seen_entities.add(_ent)
        _DXCC_ENTITY_LIST.append((_ent, _itu, _cq))
del _seen_entities, _pfx, _ent, _itu, _cq  # clean up loop variables


def callsign_to_dxcc(callsign: str) -> tuple[str, int, int]:
    """
    Return (entity_name, itu_zone, cq_zone) for a callsign, or ('', 0, 0).
    Strips portable suffixes (/P /M /MM /QRP /R and /digit) before matching.
    Validates basic callsign structure (must contain at least one digit)
    to avoid resolving random strings via greedy prefix matching.
    """
    if not callsign:
        return ("", 0, 0)

    cs = callsign.upper().strip()

    # Strip common portable/mobile suffixes: /P /M /MM /QRP /R and /digit
    # But first, check for slash-prefix DX entities (e.g. VP8/G, FR/E) before
    # stripping, so we match them correctly.
    if "/" in cs:
        slash_idx = cs.index("/")
        potential_prefix = cs[:slash_idx + 2]  # e.g. "VP8/G"
        if potential_prefix in _DXCC:
            return _DXCC[potential_prefix]

    cs = re.sub(r'/(P|M{1,2}|QRP|R|[0-9]+)$', '', cs)

    # Basic sanity check: a valid amateur callsign must contain at least one digit.
    # This prevents "ZZZZZZ" from being resolved to Brazil via the "ZZ" prefix.
    if not any(c.isdigit() for c in cs):
        return ("", 0, 0)

    # Try progressively shorter prefixes
    for length in range(len(cs), 0, -1):
        prefix = cs[:length]
        if prefix in _DXCC:
            return _DXCC[prefix]

    return ("", 0, 0)


# ── Master location parser ────────────────────────────────────────────────────
# ── Countries with common short forms used in display ────────────────────────
_COUNTRY_SHORT: dict[str, str] = {
    "United States":              "USA",
    "United Kingdom":             "UK",
    "United Arab Emirates":       "UAE",
    "Democratic Republic of Congo": "DR Congo",
    "Central African Republic":   "CAR",
    "Bosnia-Herzegovina":         "Bosnia",
    "Trinidad & Tobago":          "T&T",
    "Antigua & Barbuda":          "Antigua",
    "St. Pierre & Miquelon":      "St-Pierre",
    "Turks & Caicos Islands":     "Turks & Caicos",
    "Saint Barthelemy":           "St. Barths",
    "Sint Eustatius & Saba":      "St. Eustatius",
    "Northern Mariana Islands":   "N. Marianas",
    "Auckland & Campbell Islands":"Auckland Is.",
    "Peter 1 Island":             "Peter 1 Is.",
    "Heard Island":               "Heard Is.",
    "Cocos (Keeling) Islands":    "Cocos Is.",
    "Chagos Islands":             "Chagos",
    "Falkland Islands":           "Falklands",
    "South Georgia Island":       "S. Georgia",
    "South Sandwich Islands":     "S. Sandwich Is.",
    "South Shetland Islands":     "S. Shetland Is.",
    "South Orkney Islands":       "S. Orkney Is.",
    "Kerguelen Islands":          "Kerguelen",
    "Amsterdam & St. Paul Islands": "Amsterdam Is.",
    "Andaman & Nicobar Islands":  "Andaman Is.",
    "Lakshadweep Islands":        "Lakshadweep",
    "Pitcairn Island":            "Pitcairn",
    "Tokelau Islands":            "Tokelau",
    "Wallis & Futuna Islands":    "Wallis & Futuna",
    "Papua New Guinea":           "PNG",
}

def _fmt_location(city: str = "", admin1: str = "",
                  country: str = "", unresolved_raw: str = "") -> str:
    """
    Build a clean, compact location display string.

    Rules:
    - Drop country when it's "United States" and we have a state (state implies it)
    - Shorten long country names via _COUNTRY_SHORT
    - Skip admin1 (state/province) when it exactly matches the city name (e.g. Moscow, Moscow)
    - Skip admin1 when it exactly matches the country name
    - Format: "City, State" / "City, Country" / "State, Country" / "Country"
    - Unresolved: "⚠ <raw text>"
    """
    if not country and not city and not admin1:
        raw = unresolved_raw.strip()
        return f"⚠ {raw}" if raw else "⚠ unknown"

    short_country = _COUNTRY_SHORT.get(country, country)
    is_usa        = country == "United States"

    # Deduplicate: skip admin1 if it duplicates city or country (full or short)
    show_admin1 = (
        admin1
        and admin1.lower() != city.lower()
        and admin1.lower() != country.lower()
        and admin1.lower() != short_country.lower()
    )

    # Special case: UK constituent countries (England, Scotland, Wales,
    # Northern Ireland) are implied by "UK" — no need to show both
    _UK_CONSTITUENTS = {"england", "scotland", "wales", "northern ireland",
                        "isle of man", "jersey", "guernsey"}
    if is_usa is False and country == "United Kingdom":
        if admin1.lower() in _UK_CONSTITUENTS:
            show_admin1 = False

    parts: list[str] = []
    if city:
        parts.append(city)
    if show_admin1:
        parts.append(admin1)
    # Drop country if it duplicates the city (e.g. Singapore, Singapore)
    # or if it's USA and we already have a state
    show_country = short_country and (
        short_country.lower() != city.lower()
        and not (is_usa and show_admin1)
    )
    if show_country:
        parts.append(short_country)

    return ", ".join(parts) if parts else country or unresolved_raw or "⚠ unknown"


def parse_location(qth_raw: str, callsign: str = "") -> dict:
    """
    Parse a free-text QTH string and callsign into structured location fields.

    Resolution order (deterministic checks first, GeoNames only when needed):
      1. Maidenhead grid square detection (pattern match)
      2. US state detection (built-in table) — "LA", "Louisiana", "AR", etc.
      3. DXCC entity name found in QTH text — "Germany", "Japan", etc.
      4. GeoNames city lookup — only if input looks like it contains a city
         (i.e. neither a bare state nor a bare country name resolved it)
      5. Country derived from callsign prefix (built-in DXCC table)
      6. Unresolved — stored as free text with ⚠ marker

    Returns a dict with:
        qth_raw      — original text as entered
        qth_grid     — Maidenhead grid square if detected, else ""
        qth_state    — 2-letter US state / province code if found, else ""
        qth_country  — resolved country name
        qth_dxcc     — DXCC entity name
        qth_itu      — ITU zone (int)
        qth_cq       — CQ zone (int)
        qth_display  — clean "City, State, Country" or "State, Country" label
        qth_resolved — True if we got at least a country
    """
    result = {
        "qth_raw":        qth_raw,
        "qth_grid":       "",
        "qth_state":      "",
        "qth_country":    "",
        "qth_dxcc":       "",
        "qth_itu":        0,
        "qth_cq":         0,
        "qth_display":    "",
        "qth_resolved":   False,
        "qth_ambiguous":  False,
        "qth_candidates": [],
    }

    text = (qth_raw or "").strip()

    # ── 1. Grid square ────────────────────────────────────────────────────────
    result["qth_grid"] = parse_grid(text)

    # ── Callsign DXCC (background — used as hint and final fallback) ──────────
    cs_entity, cs_itu, cs_cq = callsign_to_dxcc(callsign)

    if not text:
        # Nothing entered — fall through to callsign fallback below
        pass
    else:
        # Strip grid squares from text before further analysis
        clean = re.sub(r'\b[A-Ra-r]{2}[0-9]{2}(?:[A-Xa-x]{2})?\b', '', text).strip(" ,")
        clean_stripped = clean.strip(", ")
        clean_upper    = clean_stripped.upper()
        clean_lower    = clean_stripped.lower()

        # ── 2. Pure US state? ─────────────────────────────────────────────────
        # Check the whole input first (handles "LA", "Louisiana", "Arkansas")
        state = parse_us_state(text)
        result["qth_state"] = state

        is_pure_state = (
            clean_upper in _STATES or
            clean_lower in _STATE_NAME_TO_ABBR
        )
        if is_pure_state:
            result["qth_country"]  = "United States"
            result["qth_dxcc"]     = "United States"
            result["qth_resolved"] = True
            kd = _DXCC.get("K")
            if kd:
                result["qth_itu"] = kd[1]
                result["qth_cq"]  = kd[2]
            result["qth_display"] = _fmt_location(
                admin1  = _STATES.get(result["qth_state"], result["qth_state"]),
                country = "United States",
            )
            return result

        # ── 3. Pure DXCC country name? ────────────────────────────────────────
        # "Germany", "Japan", "United Kingdom", etc. — no city component
        is_pure_country = clean_lower in _ENTITY_NAMES
        if is_pure_country:
            for entity, itu, cq in _DXCC_ENTITY_LIST:
                if entity.lower() == clean_lower:
                    result["qth_country"]  = entity
                    result["qth_dxcc"]     = entity
                    result["qth_itu"]      = itu
                    result["qth_cq"]       = cq
                    result["qth_resolved"] = True
                    result["qth_display"]  = _fmt_location(country=entity)
                    return result

        # ── 4. GeoNames city lookup ───────────────────────────────────────────
        # Only runs when the input wasn't resolved by the deterministic steps.
        # Inputs like "Fayetteville, AR", "Tokyo", "Berlin, Germany" land here.
        geo_city       = None
        geo_candidates = []   # populated when result is ambiguous
        geo_ambiguous  = False
        if GEO_AVAILABLE and _geo.geo_available() and clean:
            # Build hints from what we already know
            cc_hint = ""
            if cs_entity:
                for iso2, (ent, _, _) in _DXCC.items():
                    if ent == cs_entity and len(iso2) == 2:
                        cc_hint = iso2
                        break
            a1_hint = state  # e.g. "AR" — narrows "Fayetteville" to the right one

            search_tokens = [clean] + [t.strip() for t in clean.split(",")]
            for candidate in search_tokens:
                _c = candidate.strip()
                if (len(_c) < 2
                        or _c.upper() in _STATES
                        or _c.lower() in _STATE_NAME_TO_ABBR
                        or _c.lower() in _ENTITY_NAMES):
                    continue
                best, cands, ambig = _geo.lookup_city_candidates(
                    _c, country_hint=cc_hint, admin1_hint=a1_hint)
                if best:
                    geo_city       = best
                    geo_candidates = cands
                    geo_ambiguous  = ambig
                    break

        if geo_city:
            result["qth_country"]    = geo_city["country"]
            result["qth_dxcc"]       = geo_city["country"]
            result["qth_state"]      = geo_city["admin1_code"] or state
            result["qth_resolved"]   = True
            result["qth_ambiguous"]  = geo_ambiguous
            result["qth_candidates"] = geo_candidates
            if not result["qth_grid"] and geo_city.get("grid6"):
                result["qth_grid"] = geo_city["grid6"]
            result["qth_display"] = _fmt_location(
                city    = geo_city["city"],
                admin1  = geo_city["admin1_name"] or "",
                country = geo_city["country"],
            )
            return result

        # ── 5. DXCC entity name found anywhere in QTH text ───────────────────
        # Catches "Berlin, Germany" after geo fails, and freeform like "Japan trip"
        qth_upper  = text.upper()
        qth_entity = ""
        for entity, itu, cq in _DXCC_ENTITY_LIST:
            if entity.upper() in qth_upper:
                qth_entity = entity
                result["qth_itu"] = itu
                result["qth_cq"]  = cq
                break

        if qth_entity:
            result["qth_country"]  = qth_entity
            result["qth_dxcc"]     = qth_entity
            result["qth_resolved"] = True
        elif state:
            result["qth_country"]  = "United States"
            result["qth_dxcc"]     = "United States"
            result["qth_resolved"] = True
            kd = _DXCC.get("K")
            if kd:
                result["qth_itu"] = kd[1]
                result["qth_cq"]  = kd[2]

    # ── 6. Callsign prefix fallback ───────────────────────────────────────────
    if not result["qth_resolved"] and cs_entity:
        result["qth_country"]  = cs_entity
        result["qth_dxcc"]     = cs_entity
        result["qth_itu"]      = cs_itu
        result["qth_cq"]       = cs_cq
        result["qth_resolved"] = True

    # ── 7. Build display string ───────────────────────────────────────────────
    if not result["qth_display"]:
        result["qth_display"] = _fmt_location(
            admin1         = _STATES.get(result["qth_state"], result["qth_state"]),
            country        = result["qth_country"],
            unresolved_raw = text,
        )

    return result


