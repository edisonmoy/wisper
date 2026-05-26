# Wisper

macOS menu bar dictation app. Tap `fn` to start recording, tap again to transcribe and paste into the focused app.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Or use `install.sh` to install deps and register a login item so Wisper starts automatically.

## First run

Two permissions required — macOS will prompt for microphone automatically; Accessibility must be added manually:

**System Settings → Privacy & Security → Accessibility → add Terminal**

If the fn key opens the emoji picker instead of recording:

**System Settings → Keyboard → Press 🌐 key to → Do Nothing**

The Whisper model (~150 MB) downloads on first use and is cached at `~/.cache/huggingface/`.

## Usage

| Action | Result |
|---|---|
| Tap `fn` | Start recording (icon → 🔴) |
| Tap `fn` again | Transcribe + auto-paste (icon → ⏳ → 🎤) |
| Click menu bar icon | Open menu |
| History submenu | Click any item to re-copy |
| Model submenu | Switch between `tiny.en` / `base.en` / `small.en` |

## Models

| Model | Speed | Accuracy |
|---|---|---|
| `tiny.en` | ~0.3s | rough |
| `base.en` | ~0.8s | good (default) |
| `small.en` | ~2s | best |

Config and history are stored in `~/.wisper/`.
