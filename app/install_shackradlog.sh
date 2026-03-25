#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# shackradlog — cross-platform installer (macOS & Linux)
#
# Usage (one-liner from anywhere):
#   curl -sL https://raw.githubusercontent.com/SilverBull239/shackradlog/main/app/install_shackradlog.sh | bash
#
# Or download and run locally:
#   chmod +x install_shackradlog.sh
#   ./install_shackradlog.sh
#
# To uninstall:
#   ~/.shackradlog/app/install_shackradlog.sh --uninstall
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── GitHub repo info ──────────────────────────────────────────────────────────
GITHUB_USER="SilverBull239"
GITHUB_REPO="shackradlog"
GITHUB_BRANCH="main"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/${GITHUB_BRANCH}"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m';  GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m';     RESET='\033[0m'

ok()     { echo -e "${GREEN}  ✓  ${RESET}$*"; }
info()   { echo -e "${CYAN}  →  ${RESET}$*"; }
warn()   { echo -e "${YELLOW}  ⚠  ${RESET}$*"; }
die()    { echo -e "${RED}  ✗  ${RESET}$*" >&2; exit 1; }
banner() { echo -e "\n${BOLD}$*${RESET}\n"; }

# ── Detect OS and Architecture ───────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      die "Unsupported OS: $OS (only macOS and Linux are supported)" ;;
esac

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_DIR="$HOME/.shackradlog/app"
BIN_DIR="$HOME/bin"
LAUNCHER="$BIN_DIR/shackradlog"

# Detect shell RC file
if [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == */zsh ]]; then
    SHELL_RC="$HOME/.zshrc"
elif [[ -n "${BASH_VERSION:-}" ]] || [[ "$SHELL" == */bash ]]; then
    SHELL_RC="$HOME/.bashrc"
else
    # Fallback: use .profile for other shells
    SHELL_RC="$HOME/.profile"
fi

# Detect if running from local files or via curl (piped)
if [[ -t 0 ]] && [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    INSTALL_MODE="local"
else
    SCRIPT_DIR=""
    INSTALL_MODE="remote"
fi

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

# ── 1. Show detected platform ────────────────────────────────────────────────
info "Checking system..."

case "$PLATFORM" in
    macos)
        if [[ "$ARCH" == "arm64" ]]; then
            ok "macOS on Apple Silicon (${ARCH})"
        else
            ok "macOS on Intel (${ARCH})"
        fi
        ;;
    linux)
        # Check for Raspberry Pi
        if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
            PI_MODEL="$(tr -d '\0' < /proc/device-tree/model)"
            ok "Linux on ${PI_MODEL}"
        else
            ok "Linux on ${ARCH}"
        fi
        ;;
esac

# ── 2. Find Python 3.11+ ─────────────────────────────────────────────────────
info "Looking for Python 3.11+..."

PYTHON3=""

# Build search candidates based on platform
CANDIDATES=()

if [[ "$PLATFORM" == "macos" ]]; then
    CANDIDATES=(
        "/opt/homebrew/bin/python3"
        "/opt/homebrew/bin/python3.13"
        "/opt/homebrew/bin/python3.12"
        "/opt/homebrew/bin/python3.11"
        "/usr/local/bin/python3"
        "/usr/bin/python3"
    )
else
    # Linux
    CANDIDATES=(
        "/usr/bin/python3"
        "/usr/bin/python3.13"
        "/usr/bin/python3.12"
        "/usr/bin/python3.11"
        "/usr/local/bin/python3"
    )
fi

# Also check whatever is in PATH
CANDIDATES+=("$(command -v python3 2>/dev/null || true)")

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
    if [[ "$PLATFORM" == "macos" ]]; then
        die "Python 3.11 or newer not found.

       Install it with Homebrew:
         brew install python@3.12

       Or download from: https://www.python.org/downloads/macos/
       Then re-run this installer."
    else
        die "Python 3.11 or newer not found.

       Install it with:
         sudo apt update && sudo apt install python3

       If your distro's Python is too old, try:
         sudo apt install python3.11

       Then re-run this installer."
    fi
fi

PY_VERSION="$("$PYTHON3" -c 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}.{v.micro}")')"
ok "Found Python ${PY_VERSION} at ${PYTHON3}"

# ── 3. Get source files ──────────────────────────────────────────────────────
info "Preparing source files..."

SOURCE_FILES=(
    shackradlog.py
    shackradlog_geo.py
    shackradlog_db.py
    shackradlog_export.py
    shackradlog_freq.py
    shackradlog_location.py
    shackradlog_dxcc.csv
)

mkdir -p "$APP_DIR"

if [[ "$INSTALL_MODE" == "local" ]]; then
    # Local install — copy from script directory
    for _required in "${SOURCE_FILES[@]}"; do
        [[ -f "$SCRIPT_DIR/$_required" ]] \
            || die "$_required not found in $SCRIPT_DIR
       Make sure all shackradlog files are in the same folder as this installer."
    done
    ok "Source files found locally"
    
    for _f in "${SOURCE_FILES[@]}"; do
        cp "$SCRIPT_DIR/$_f" "$APP_DIR/$_f"
    done
else
    # Remote install — download from GitHub
    info "Downloading from GitHub..."
    
    # Check for curl or wget
    if command -v curl &>/dev/null; then
        DOWNLOAD="curl -fsSL"
    elif command -v wget &>/dev/null; then
        DOWNLOAD="wget -qO-"
    else
        die "Neither curl nor wget found. Please install one and retry."
    fi
    
    for _f in "${SOURCE_FILES[@]}"; do
        info "  Fetching $_f..."
        if ! $DOWNLOAD "${GITHUB_RAW}/app/$_f" > "$APP_DIR/$_f"; then
            die "Failed to download $_f from GitHub"
        fi
    done
    
    # Also save the installer itself for future uninstall
    $DOWNLOAD "${GITHUB_RAW}/app/install_shackradlog.sh" > "$APP_DIR/install_shackradlog.sh"
    chmod +x "$APP_DIR/install_shackradlog.sh"
    
    ok "Downloaded from GitHub"
fi

chmod 644 "$APP_DIR/"*.py "$APP_DIR/"*.csv
ok "App files installed to $APP_DIR"

# ── 5. Create launcher ────────────────────────────────────────────────────────
info "Creating launcher at ${LAUNCHER}..."

mkdir -p "$BIN_DIR"

cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# shackradlog launcher — generated by install_shackradlog.sh
exec "${PYTHON3}" "${APP_DIR}/shackradlog.py" "\$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"
ok "Launcher created"

# ── 6. Ensure ~/bin is in PATH ────────────────────────────────────────────────
PATH_LINE='export PATH="$HOME/bin:$PATH"'
PATH_COMMENT='# Added by shackradlog installer'

add_to_rc() {
    local rc_file="$1"
    if [[ -f "$rc_file" ]] || [[ "$rc_file" == "$SHELL_RC" ]]; then
        touch "$rc_file"
        if ! grep -qF "Added by shackradlog installer" "$rc_file" 2>/dev/null; then
            echo "" >> "$rc_file"
            echo "$PATH_COMMENT" >> "$rc_file"
            echo "$PATH_LINE" >> "$rc_file"
            ok "PATH added to ${rc_file}"
        fi
    fi
}

if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    ok "~/bin already in PATH"
else
    info "Adding ~/bin to PATH..."
    
    # Add to both .bashrc and .zshrc to cover all cases
    add_to_rc "$HOME/.bashrc"
    add_to_rc "$HOME/.zshrc"
    
    export PATH="$BIN_DIR:$PATH"
    echo ""
    echo -e "  ${YELLOW}To use 'shackradlog' command immediately, run:${RESET}"
    echo -e "  ${CYAN}source ~/.zshrc${RESET}   (if using zsh)"
    echo -e "  ${CYAN}source ~/.bashrc${RESET}  (if using bash)"
    echo -e "  ${YELLOW}Or just run:${RESET} ${CYAN}~/bin/shackradlog${RESET}"
    echo ""
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

# ── 8. Check for existing log DB ──────────────────────────────────────────────
if [[ -f "$HOME/.shackradlog/shackradlog.db" ]]; then
    ok "Existing log database found — will be used as-is"
fi

# ── 9. Prompt for operator callsign(s) ────────────────────────────────────────
MYCALL_FILE="$HOME/.shackradlog/mycall"

if [[ -f "$MYCALL_FILE" ]]; then
    existing_calls="$(cat "$MYCALL_FILE")"
    ok "Callsign(s) already configured: $existing_calls"
elif [[ -t 0 ]]; then
    # Only prompt if stdin is a terminal (not piped)
    echo
    info "Enter your callsign(s) to display in the title bar."
    echo -e "       ${CYAN}Examples: HAM:KJ5PEJ, GMRS:WRYS604${RESET}"
    echo -e "       ${CYAN}     or just: KJ5PEJ${RESET}"
    echo -e "       (Press Enter to skip — you can add later by editing ~/.shackradlog/mycall)"
    echo
    read -rp "  Callsign(s): " user_calls

    if [[ -n "$user_calls" ]]; then
        # Uppercase and save
        echo "$user_calls" | tr '[:lower:]' '[:upper:]' > "$MYCALL_FILE"
        ok "Saved callsign(s) to $MYCALL_FILE"
    else
        warn "Skipped — you can add callsigns later with:"
        echo -e "       ${CYAN}echo \"HAM:YOURCALL, GMRS:YOURCALL\" > ~/.shackradlog/mycall${RESET}"
    fi
else
    # Piped install — skip prompt, show instructions
    info "To set your callsign, run:"
    echo -e "       ${CYAN}echo \"HAM:YOURCALL, GMRS:YOURCALL\" > ~/.shackradlog/mycall${RESET}"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║  shackradlog installed successfully  ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════╝${RESET}"
echo
echo -e "  Your log:    ${CYAN}~/.shackradlog/shackradlog.db${RESET}"
echo -e "  Uninstall:   ${CYAN}~/.shackradlog/app/install_shackradlog.sh --uninstall${RESET}"
echo
echo -e "  ${YELLOW}First run downloads the city database (~50 MB).${RESET}"
echo -e "  After that, shackradlog works completely offline."
echo

# Auto-launch shackradlog with proper terminal connection
echo -e "  ${CYAN}Launching shackradlog...${RESET}"
echo -e "  ${CYAN}(Next time, just type: shackradlog)${RESET}"
echo
exec "$LAUNCHER" </dev/tty
