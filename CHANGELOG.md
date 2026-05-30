# Changelog

All notable changes to Wisper are documented here.

## [1.0.0] — 2026-05-29

Initial production release.

### Features
- Hold `fn` to record, release to transcribe and paste
- Five Whisper model sizes: tiny.en, base.en, small.en, medium.en, distil-large-v3
- Three text cleanup modes: None, Basic (regex), AI (MLX on Apple Silicon)
- Clipboard-safe paste: snapshots and restores clipboard contents including images
- Transcription history with model name and latency; click any entry to re-copy
- Floating waveform overlay follows the cursor across multiple screens
- Auto-update via `git fetch` with remote URL verification
- Structured rotating log at `~/.wisper/wisper.log`

### Security
- Remote URL verification before applying git updates
- Clipboard error handling with notification on restore failure
- Runtime Accessibility and Microphone permission checks on launch
- `install.sh` uses `set -euo pipefail` and XML-escapes paths in plist
- Config fields validated on load (model, cleanup_mode, history_limit)

### Testing
- 100% branch coverage across all modules
- 276 tests covering unit, integration, and benchmark cases
- CI runs on Linux (all tests) with coverage enforcement
