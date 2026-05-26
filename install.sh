#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wisper.app.plist"
VENV="$SCRIPT_DIR/.venv"

# 1. Create venv and install deps
echo "Creating virtual environment…"
python3 -m venv "$VENV"
echo "Installing dependencies…"
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# 2. Write launchd plist for auto-start on login
PYTHON_BIN="$VENV/bin/python3"
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
    <string>$PYTHON_BIN</string>
    <string>$SCRIPT_DIR/app.py</string>
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

# 3. Load it
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo ""
echo "✅  Wisper installed and running."
echo ""
echo "⚠️  Two permissions required (macOS will prompt on first use):"
echo "   1. Accessibility — System Settings → Privacy & Security → Accessibility"
echo "   2. Microphone   — System Settings → Privacy & Security → Microphone"
echo ""
echo "⚠️  If the Globe/fn key opens the emoji picker instead of recording:"
echo "   System Settings → Keyboard → 'Press Globe key to' → set to 'Do Nothing'"
echo ""
echo "Logs: ~/.wisper/wisper.log"
