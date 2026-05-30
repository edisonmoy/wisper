#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wisper.app.plist"

echo "Stopping Wisper…"
launchctl unload "$PLIST" 2>/dev/null || true

echo "Removing launchd plist…"
rm -f "$PLIST"

# Optional: remove app data
read -r -p "Remove app data (~/.wisper/)? This deletes history and config. [y/N] " REMOVE_DATA
if [[ "${REMOVE_DATA,,}" == "y" ]]; then
    rm -rf "$HOME/.wisper/"
    echo "Removed ~/.wisper/"
fi

# Optional: remove cached models
read -r -p "Remove cached Whisper/MLX models (~/.cache/huggingface/)? This frees 75 MB – 2 GB. [y/N] " REMOVE_MODELS
if [[ "${REMOVE_MODELS,,}" == "y" ]]; then
    rm -rf "$HOME/.cache/huggingface/"
    echo "Removed ~/.cache/huggingface/"
fi

echo ""
echo "Wisper uninstalled."
echo ""
echo "The app bundle and source files remain at: $SCRIPT_DIR"
echo "To fully remove them: rm -rf \"$SCRIPT_DIR\""
