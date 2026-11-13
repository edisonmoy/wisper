#!/usr/bin/env bash
# Build Wisper.app around the native launcher (launcher.c) and ad-hoc sign it.
#
# The compiled launcher spawns the venv's Python as a child process, which
# makes macOS attribute Microphone/Accessibility permissions to "Wisper"
# rather than to the Python interpreter.
#
# Usage: build_app.sh [--if-changed]
#   --if-changed  skip the rebuild when launcher.c and Info.plist haven't
#                 changed since the last build. Used by the auto-updater:
#                 every rebuild changes the code signature, and macOS may
#                 then ask for permissions again, so only rebuild when needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_BUNDLE="$SCRIPT_DIR/Wisper.app"
STAGING="$SCRIPT_DIR/.Wisper.app.build"
BUNDLE_ID="com.wisper.app"
ICNS="$SCRIPT_DIR/assets/wisper.icns"
STAMP_REL="Contents/Resources/build.stamp"

stamp="$(cat "$SCRIPT_DIR/launcher.c" "$SCRIPT_DIR/assets/Info.plist" | shasum -a 256 | cut -d' ' -f1)"

if [[ "${1:-}" == "--if-changed" ]] && [[ -f "$APP_BUNDLE/$STAMP_REL" ]] \
    && [[ "$(cat "$APP_BUNDLE/$STAMP_REL")" == "$stamp" ]]; then
    echo "Wisper.app is up to date"
    exit 0
fi

if ! command -v clang >/dev/null 2>&1; then
    echo "error: clang not found. Install the Xcode Command Line Tools:" >&2
    echo "    xcode-select --install" >&2
    exit 1
fi

# Build into a staging bundle and swap it in at the end, so a running Wisper
# never sees a half-written executable.
rm -rf "$STAGING"
mkdir -p "$STAGING/Contents/MacOS" "$STAGING/Contents/Resources"

clang -O2 -Wall -Wextra -Werror -mmacosx-version-min=11.0 \
    -o "$STAGING/Contents/MacOS/Wisper" "$SCRIPT_DIR/launcher.c"
cp "$SCRIPT_DIR/assets/Info.plist" "$STAGING/Contents/Info.plist"
if [[ -f "$ICNS" ]]; then
    cp "$ICNS" "$STAGING/Contents/Resources/wisper.icns"
fi
printf '%s' "$stamp" > "$STAGING/$STAMP_REL"

# Ad-hoc signature with a fixed identifier gives macOS a stable identity to
# attach permissions to (no Apple developer account needed).
codesign --force --sign - --identifier "$BUNDLE_ID" "$STAGING"

rm -rf "$APP_BUNDLE"
mv "$STAGING" "$APP_BUNDLE"
xattr -rd com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

echo "Wisper.app built at $APP_BUNDLE"
