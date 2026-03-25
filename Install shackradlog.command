#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# shackradlog — installer for Apple Silicon Macs (M1 / M2 / M3 / M4)
#
# Double-click this file in Finder to install shackradlog.
#
# To uninstall, open Terminal and run:
#   ~/.shackradlog/app/install_shackradlog.sh --uninstall
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Ensure this file is executable — macOS may strip the bit on download/unzip
chmod +x "$0" 2>/dev/null || true

# .command files launched from Finder start in ~, not the file's directory.
# This moves us to the folder containing this script so we can find shackradlog.py.
cd "$(dirname "$0")"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m';  GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m';     RESET='\033[0m'

ok()     { echo -e "${GREEN}  ✓  ${RESET}$*"; }
info()   { echo -e "${CYAN}  →  ${RESET}$*"; }
warn()   { echo -e "${YELLOW}  ⚠  ${RESET}$*"; }
die()    { echo -e "${RED}  ✗  ${RESET}$*" >&2; exit 1; }
banner() { echo -e "\n${BOLD}$*${RESET}\n"; }

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_DIR="$HOME/.shackradlog/app"     # where all shackradlog .py files + shackradlog_dxcc.csv live
BIN_DIR="$HOME/bin"             # launcher lives here — no sudo required
LAUNCHER="$BIN_DIR/shackradlog"
SHELL_RC="$HOME/.zshrc"         # zsh is the default shell on all modern Macs

# .command lives in the top-level folder; source files are in app/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/app"

# ─────────────────────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
    banner "Uninstalling shackradlog"

    if [[ -L "$LAUNCHER" || -f "$LAUNCHER" ]]; then
        rm "$LAUNCHER"
        ok "Removed launcher:  $LAUNCHER"
    else
        warn "Launcher not found at $LAUNCHER — skipping"
    fi

    if [[ -d "$APP_DIR" ]]; then
        rm -rf "$APP_DIR"
        ok "Removed app files: $APP_DIR"
    else
        warn "App directory not found at $APP_DIR — skipping"
    fi

    echo
    warn "Your log data at ~/.shackradlog/shackradlog.db was NOT touched."
    warn "Delete ~/.shackradlog manually if you want to remove everything."
    echo
    ok "shackradlog uninstalled."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────────────────────────────────────────
banner "shackradlog installer"

# ── 1. Confirm Apple Silicon ──────────────────────────────────────────────────
info "Checking hardware..."

ARCH="$(uname -m)"
OS="$(uname -s)"

[[ "$OS" == "Darwin" ]] \
    || die "This installer is for macOS only. Got: $OS"
[[ "$ARCH" == "arm64" ]] \
    || die "This installer requires Apple Silicon (arm64). Got: $ARCH
       Running on Intel? Run shackradlog directly: python3 shackradlog.py"

ok "Apple Silicon Mac confirmed (${ARCH})"

# ── 2. Find Python 3.11+ ─────────────────────────────────────────────────────
info "Looking for Python 3.11+..."

PYTHON3=""

# Search order: Homebrew arm64 prefix first, then Xcode CLT python3, then PATH
CANDIDATES=(
    "/opt/homebrew/bin/python3"
    "/opt/homebrew/bin/python3.13"
    "/opt/homebrew/bin/python3.12"
    "/opt/homebrew/bin/python3.11"
    "/usr/bin/python3"
    "$(command -v python3 2>/dev/null || true)"
)

for candidate in "${CANDIDATES[@]}"; do
    [[ -z "$candidate" ]] && continue
    [[ -x "$candidate" ]] || continue

    major="$("$candidate" -c 'import sys; print(sys.version_info[0])' 2>/dev/null || true)"
    minor="$("$candidate" -c 'import sys; print(sys.version_info[1])' 2>/dev/null || true)"

    if [[ "$major" == "3" && "$minor" -ge 11 ]]; then
        PYTHON3="$candidate"
        break
    fi
done

if [[ -z "$PYTHON3" ]]; then
    die "Python 3.11 or newer not found.

       Install it with Homebrew:
         brew install python@3.12

       Or download from: https://www.python.org/downloads/macos/
       Then re-run this installer."
fi

PY_VERSION="$("$PYTHON3" -c 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}.{v.micro}")')"
ok "Found Python ${PY_VERSION} at ${PYTHON3}"

# ── 3. Confirm source files exist ─────────────────────────────────────────────
info "Checking source files..."

for _required in shackradlog.py shackradlog_geo.py shackradlog_db.py shackradlog_export.py \
                  shackradlog_freq.py shackradlog_location.py shackradlog_dxcc.csv; do
    [[ -f "$SRC_DIR/$_required" ]] \
        || die "$_required not found in $SCRIPT_DIR
       Make sure all shackradlog files are in the same folder as this installer."
done
ok "Source files found"

# ── 4. Install app files ──────────────────────────────────────────────────────
info "Installing app files to ${APP_DIR}..."

mkdir -p "$APP_DIR"
for _f in shackradlog.py shackradlog_geo.py shackradlog_db.py shackradlog_export.py \
           shackradlog_freq.py shackradlog_location.py shackradlog_dxcc.csv; do
    cp "$SRC_DIR/$_f" "$APP_DIR/$_f"
done
chmod 644 "$APP_DIR/"*.py "$APP_DIR/"*.csv

ok "App files installed"

# ── 5. Create launcher ────────────────────────────────────────────────────────
info "Creating launcher at ${LAUNCHER}..."

mkdir -p "$BIN_DIR"

# Write the launcher — bake in the exact python3 path found above
# so it works even if PATH changes later
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# shackradlog launcher — generated by install_shackradlog.sh
exec "${PYTHON3}" "${APP_DIR}/shackradlog.py" "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"
ok "Launcher created"

# ── 6. Ensure ~/bin is in PATH ────────────────────────────────────────────────
PATH_BLOCK='
# Added by shackradlog installer
export PATH="$HOME/bin:$PATH"'

if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    ok "~/bin already in PATH"
else
    info "Adding ~/bin to PATH in ${SHELL_RC}..."

    # Don't add a duplicate block if we already patched this file
    if ! grep -qF "Added by shackradlog installer" "$SHELL_RC" 2>/dev/null; then
        echo "$PATH_BLOCK" >> "$SHELL_RC"
        ok "PATH updated in ${SHELL_RC}"
    else
        ok "PATH block already present in ${SHELL_RC}"
    fi

    # Make it work right now in this session too
    export PATH="$BIN_DIR:$PATH"
    warn "Open a new terminal (or run 'source ~/.zshrc') for PATH to persist."
fi

# ── 7. Smoke test ─────────────────────────────────────────────────────────────
info "Running smoke test..."

SMOKE_RESULT="$(SHACKRADLOG_PY="$APP_DIR/shackradlog.py" \
                SHACKRADLOG_GEO="$APP_DIR/shackradlog_geo.py" \
                SHACKRADLOG_DIR="$APP_DIR" \
                SHACKRADLOG_DXCC="$APP_DIR/shackradlog_dxcc.csv" \
                "$PYTHON3" - <<'PYEOF' 2>&1
import sys, ast, types, os

shackradlog_dir  = os.environ["SHACKRADLOG_DIR"]
shackradlog_dxcc = os.environ["SHACKRADLOG_DXCC"]

# Parse all Python source files — catches syntax errors
py_files = ["shackradlog.py","shackradlog_geo.py","shackradlog_db.py",
             "shackradlog_export.py","shackradlog_freq.py","shackradlog_location.py"]
for fname in py_files:
    fpath = os.path.join(shackradlog_dir, fname)
    try:
        ast.parse(open(fpath).read())
    except SyntaxError as e:
        print(f"SYNTAX ERROR in {fname}: {e}")
        sys.exit(1)

# Verify shackradlog_dxcc.csv is present and non-empty
if not os.path.exists(shackradlog_dxcc) or os.path.getsize(shackradlog_dxcc) == 0:
    print("MISSING: shackradlog_dxcc.csv")
    sys.exit(1)

# Import shackradlog without launching curses
fake_curses = types.ModuleType("curses")
fake_curses.error = Exception
sys.modules["curses"] = fake_curses
sys.path.insert(0, shackradlog_dir)

try:
    import shackradlog
    for fn in ("db_connect", "db_insert", "db_fetch", "export_adif",
               "parse_location", "_fmt_location", "normalize_freq",
               "freq_to_band", "BAND_MAP"):
        assert hasattr(shackradlog, fn), f"missing: {fn}"
    print("ok")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)
PYEOF
)"

if [[ "$SMOKE_RESULT" == "ok" ]]; then
    ok "Smoke test passed"
else
    warn "Smoke test warning: $SMOKE_RESULT"
    warn "Try running 'shackradlog' — it may still work fine."
fi

# ── 8. Check for updates to existing log DB ───────────────────────────────────
# If the user is upgrading, their DB schema may need migration.
# shackradlog handles this automatically on first connect — nothing to do here.
if [[ -f "$HOME/.shackradlog/shackradlog.db" ]]; then
    ok "Existing log database found — will be used as-is"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║   shackradlog installed successfully.     ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════╝${RESET}"
echo
echo -e "  Start:       ${CYAN}shackradlog${RESET}"
echo -e "  Your log:    ${CYAN}~/.shackradlog/shackradlog.db${RESET}"
echo -e "  Uninstall:   ${CYAN}./install_shackradlog.sh --uninstall${RESET}"
echo
echo -e "  ${YELLOW}First run downloads the city database (~50 MB).${RESET}"
echo -e "  After that, shackradlog works completely offline."
echo
