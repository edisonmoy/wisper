#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wisper.app.plist"
VENV="$SCRIPT_DIR/.venv"
APP_BUNDLE="$SCRIPT_DIR/Wisper.app"

# ---------------------------------------------------------------------------
# 1. Create venv and install deps
# ---------------------------------------------------------------------------
echo "Creating virtual environment…"
python3 -m venv "$VENV"
echo "Installing dependencies…"
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# ---------------------------------------------------------------------------
# 2. Generate assets/wisper.icns (skip if already exists)
# ---------------------------------------------------------------------------
ICNS="$SCRIPT_DIR/assets/wisper.icns"
if [ -f "$ICNS" ]; then
    echo "Icon already exists, skipping make_icon.py"
else
    echo "Generating app icon…"
    "$VENV/bin/python3" "$SCRIPT_DIR/make_icon.py"
fi

# ---------------------------------------------------------------------------
# 3. Build Wisper.app bundle (native launcher, ad-hoc signed)
# ---------------------------------------------------------------------------
echo "Building Wisper.app bundle…"
"$SCRIPT_DIR/build_app.sh" --if-changed
LAUNCHER="$APP_BUNDLE/Contents/MacOS/Wisper"

# ---------------------------------------------------------------------------
# 4. Write launchd plist pointing at the native launcher (not python directly)
# ---------------------------------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.wisper"

# XML-escape a string for safe embedding in a plist value.
xml_escape() {
    printf '%s' "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'
}

LAUNCHER_ESC="$(xml_escape "$LAUNCHER")"
LOG_PATH_ESC="$(xml_escape "$HOME/.wisper/wisper.log")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.wisper.app</string>
  <key>ProgramArguments</key>
  <array>
    <string>${LAUNCHER_ESC}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>${LOG_PATH_ESC}</string>
  <key>StandardOutPath</key>
  <string>${LOG_PATH_ESC}</string>
</dict>
</plist>
EOF

# ---------------------------------------------------------------------------
# 5. Load launchd plist
# ---------------------------------------------------------------------------
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

# ---------------------------------------------------------------------------
# 6. Setup instructions
# ---------------------------------------------------------------------------
echo ""
echo "Wisper installed and running."
echo ""
echo "Activity Monitor will now show the process as 'Wisper' with the custom icon."
echo ""
echo "A 'Set up Wisper' checklist will open to walk you through the Microphone"
echo "and Accessibility permissions (reopen it from the menu bar: Permissions...)."
echo ""
echo "If the Globe/fn key opens the emoji picker instead of recording:"
echo "   System Settings -> Keyboard -> 'Press Globe key to' -> set to 'Do Nothing'"
echo ""
echo "Logs: ~/.wisper/wisper.log"
