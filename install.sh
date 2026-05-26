#!/usr/bin/env bash
set -e

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
# 3. Build Wisper.app bundle
# ---------------------------------------------------------------------------
echo "Building Wisper.app bundle…"

MACOS_DIR="$APP_BUNDLE/Contents/MacOS"
RES_DIR="$APP_BUNDLE/Contents/Resources"

mkdir -p "$MACOS_DIR"
mkdir -p "$RES_DIR"

# Launcher shell script
LAUNCHER="$MACOS_DIR/Wisper"
cat > "$LAUNCHER" <<'LAUNCHER_EOF'
#!/bin/bash
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$REPO/.venv/bin/activate"
exec python3 "$REPO/app.py"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

# Copy resources
cp "$ICNS" "$RES_DIR/wisper.icns"
cp "$SCRIPT_DIR/assets/Info.plist" "$APP_BUNDLE/Contents/Info.plist"

echo "Wisper.app bundle built at $APP_BUNDLE"

# ---------------------------------------------------------------------------
# 4. Write launchd plist pointing at the shell launcher (not python directly)
# ---------------------------------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.wisper"

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
    <string>$LAUNCHER</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardErrorPath</key>
  <string>$HOME/.wisper/wisper.log</string>
  <key>StandardOutPath</key>
  <string>$HOME/.wisper/wisper.log</string>
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
echo "Two permissions required (macOS will prompt on first use):"
echo "   1. Accessibility -- System Settings -> Privacy & Security -> Accessibility"
echo "   2. Microphone    -- System Settings -> Privacy & Security -> Microphone"
echo ""
echo "If the Globe/fn key opens the emoji picker instead of recording:"
echo "   System Settings -> Keyboard -> 'Press Globe key to' -> set to 'Do Nothing'"
echo ""
echo "Logs: ~/.wisper/wisper.log"
