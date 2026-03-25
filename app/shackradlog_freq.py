"""
shackradlog_freq.py — Frequency normalisation and band mapping for shackradlog.

Provides:
  BAND_MAP             — list of (lo_mhz, hi_mhz, band_name) tuples
  normalize_freq(raw)  → canonical MHz string
  freq_to_band(freq)   → band name string (e.g. "20m") or ""
"""

# ── License ───────────────────────────────────────────────────────────────────
# Copyright (C) 2026  Aron Tkachuk  |  silverbull239@proton.me
# GNU General Public License v3 or later — see <https://www.gnu.org/licenses/>


import re

# ── Frequency → Band helper ───────────────────────────────────────────────────
BAND_MAP: list[tuple[float, float, str]] = [
    # ── Amateur bands ─────────────────────────────────────────────────────────
    (0.1357, 0.1378, "2200m"),   # 135.7–137.8 kHz
    (0.4720, 0.4790, "630m"),    # 472–479 kHz
    (1.800,  2.000,  "160m"),
    (3.500,  4.000,  "80m"),
    (5.332,  5.405,  "60m"),
    (7.000,  7.300,  "40m"),
    (10.100, 10.150, "30m"),
    (14.000, 14.350, "20m"),
    (18.068, 18.168, "17m"),
    (21.000, 21.450, "15m"),
    (24.890, 24.990, "12m"),
    (28.000, 29.700, "10m"),
    (50.000, 54.000, "6m"),
    (144.00, 148.00, "2m"),
    (219.00, 225.00, "1.25m"),
    (420.00, 450.00, "70cm"),
    (902.00, 928.00, "33cm"),
    (1240.0, 1300.0, "23cm"),
    (2300.0, 2450.0, "13cm"),
    # ── Citizens Band (11m) ───────────────────────────────────────────────────
    (26.965, 27.405, "CB"),
    # ── MURS (Multi-Use Radio Service) ────────────────────────────────────────
    (151.820, 151.880, "MURS"),   # Ch 1-2
    (151.940, 151.940, "MURS"),   # Ch 3
    (154.570, 154.570, "MURS"),   # Ch 4
    (154.600, 154.600, "MURS"),   # Ch 5
    # ── GMRS 462 MHz (Simplex Ch 1-7 + High Power/Repeater Output Ch 15-22) ───
    (462.5500, 462.5500, "GMRS"),   # Ch 15
    (462.5625, 462.5625, "GMRS"),   # Ch 1
    (462.5750, 462.5750, "GMRS"),   # Ch 16
    (462.5875, 462.5875, "GMRS"),   # Ch 2
    (462.6000, 462.6000, "GMRS"),   # Ch 17
    (462.6125, 462.6125, "GMRS"),   # Ch 3
    (462.6250, 462.6250, "GMRS"),   # Ch 18
    (462.6375, 462.6375, "GMRS"),   # Ch 4
    (462.6500, 462.6500, "GMRS"),   # Ch 19
    (462.6625, 462.6625, "GMRS"),   # Ch 5
    (462.6750, 462.6750, "GMRS"),   # Ch 20
    (462.6875, 462.6875, "GMRS"),   # Ch 6
    (462.7000, 462.7000, "GMRS"),   # Ch 21
    (462.7125, 462.7125, "GMRS"),   # Ch 7
    (462.7250, 462.7250, "GMRS"),   # Ch 22
    # ── GMRS Repeater Input 467 MHz (Ch 15R-22R) ──────────────────────────────
    (467.5500, 467.5500, "GMRS-R"),  # Ch 15R
    (467.5750, 467.5750, "GMRS-R"),  # Ch 16R
    (467.6000, 467.6000, "GMRS-R"),  # Ch 17R
    (467.6250, 467.6250, "GMRS-R"),  # Ch 18R
    (467.6500, 467.6500, "GMRS-R"),  # Ch 19R
    (467.6750, 467.6750, "GMRS-R"),  # Ch 20R
    (467.7000, 467.7000, "GMRS-R"),  # Ch 21R
    (467.7250, 467.7250, "GMRS-R"),  # Ch 22R
    # ── FRS Only 467 MHz (Ch 8-14, 0.5W max) ──────────────────────────────────
    (467.5625, 467.5625, "FRS"),    # Ch 8
    (467.5875, 467.5875, "FRS"),    # Ch 9
    (467.6125, 467.6125, "FRS"),    # Ch 10
    (467.6375, 467.6375, "FRS"),    # Ch 11
    (467.6625, 467.6625, "FRS"),    # Ch 12
    (467.6875, 467.6875, "FRS"),    # Ch 13
    (467.7125, 467.7125, "FRS"),    # Ch 14
]

def normalize_freq(raw: str) -> str:
    """
    Accept many common frequency formats and return a clean MHz string.

    Handled formats (examples):
      14.225          → 14.225      (already MHz)
      14225           → 14.225      (Hz/kHz heuristic)
      14225.0         → 14.225
      14.225.000      → 14.225      (dotted-MHz with trailing zeros)
      000.480.000     → 0.480       (dotted with leading zeros, e.g. 480 kHz)
      480             → 0.480       (bare kHz < 1800)
      1800            → 1.800       (kHz boundary)
      7074            → 7.074
      144390          → 144.390
      146520          → 146.520
    """
    if not raw:
        return raw

    s = raw.strip()

    # Remove any spaces or stray characters except digits and dots
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return raw.strip()

    # Handle leading dot (e.g., ".4735" → "0.4735")
    if s.startswith("."):
        s = "0" + s

    # Strip only trailing dots (not leading — we handled those above)
    s = s.rstrip(".")

    # Count dots
    dot_count = s.count(".")

    if dot_count == 0:
        # Pure integer — decide MHz vs kHz vs Hz by magnitude and band membership
        n = int(s)
        if n == 0:
            return "0"
        elif n < 100:
            # Treat as MHz integer (e.g. "14" → 14.0 MHz, "50" → 50.0 MHz)
            return str(float(n))
        elif n < 1_000_000:
            # Ambiguous range: could be kHz (e.g. 14225 kHz = 14.225 MHz)
            # or a bare MHz integer for VHF/UHF (e.g. 440 MHz, 144 MHz).
            # Strategy: check if the value itself (treated as MHz) falls inside
            # a known amateur band. If so, it is almost certainly a bare MHz entry.
            as_mhz = float(n)
            if any(lo <= as_mhz <= hi for lo, hi, _ in BAND_MAP):
                return str(as_mhz)
            # Otherwise treat as kHz
            return f"{n / 1000:.6g}"
        else:
            # Hz range (≥ 1 000 000 Hz) → divide by 1 000 000
            return f"{n / 1_000_000:.6g}"

    elif dot_count == 1:
        # Standard decimal — treat as MHz unless clearly in kHz or Hz range.
        # Rule: if the integer part alone is a plausible MHz value (≥ 0.1 and
        # ≤ 2400 MHz covers all amateur bands through 13cm), keep as MHz.
        # Only divide if the number is so large it can only be kHz or Hz.
        f = float(s)
        if f <= 2400:
            # Covers all ham bands from 160m (1.8 MHz) through 13cm (2.4 GHz).
            # Strip trailing zeros for a canonical form (146.520 → 146.52).
            stripped = s.rstrip("0").rstrip(".")
            return stripped if stripped else "0"
        elif f < 100_000:
            # Too large to be MHz, likely kHz with decimal
            return f"{f / 1000:.6g}"
        else:
            # Hz with decimal
            return f"{f / 1_000_000:.6g}"

    else:
        # Multiple dots — treat as dotted notation: AAA.BBB.CCC
        # Strip leading zero-groups and reconstruct
        parts = s.split(".")
        # Rejoin first two meaningful groups as MHz.kHz
        # e.g. "14.225.000" → 14.225,  "000.480.000" → 0.480
        try:
            mhz_part  = int(parts[0])
            khz_part  = int(parts[1]) if len(parts) > 1 else 0
            hz_part   = int(parts[2]) if len(parts) > 2 else 0
            total_hz  = mhz_part * 1_000_000 + khz_part * 1_000 + hz_part
            return f"{total_hz / 1_000_000:.6g}"
        except (ValueError, IndexError):
            return raw.strip()


def freq_to_band(freq_str: str) -> str:
    """
    Look up band name for a frequency string.
    Uses ±500 Hz tolerance for exact frequency matches (GMRS/FRS channels).
    """
    try:
        f = float(normalize_freq(freq_str))
        tolerance = 0.0005  # 500 Hz tolerance for exact channel matches
        for lo, hi, band in BAND_MAP:
            if lo == hi:
                # Exact frequency entry — use tolerance
                if abs(f - lo) <= tolerance:
                    return band
            else:
                # Range entry
                if lo <= f <= hi:
                    return band
        return ""
    except (ValueError, TypeError):
        return ""

