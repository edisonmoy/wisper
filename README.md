# Wisper

macOS menu bar dictation app. Tap `fn` to start recording, tap again to transcribe and paste into the focused app.

## Setup

```bash
git clone https://github.com/edisonmoy/wisper.git
cd wisper
bash install.sh
```

`install.sh` creates a virtual environment, installs dependencies, generates the app icon, builds `Wisper.app`, and registers a login item so Wisper starts automatically on login.

## First run

Two permissions required — macOS will prompt for microphone automatically; Accessibility must be added manually:

**System Settings → Privacy & Security → Accessibility → add Terminal**

If the fn key opens the emoji picker instead of recording:

**System Settings → Keyboard → Press 🌐 key to → Do Nothing**

The Whisper model downloads on first use and is cached at `~/.cache/huggingface/`. Transcription runs entirely on your CPU — no audio or text ever leaves your machine.

On startup, the Hugging Face library makes a lightweight version-check request (no audio, just a metadata header). To disable that after the model has been downloaded once:

```bash
echo 'export HF_HUB_OFFLINE=1' >> ~/.zshrc
```

## Usage

| Action | Result |
|---|---|
| Tap `fn` | Start recording (icon → 🔴) |
| Tap `fn` again | Transcribe + auto-paste (icon → ⏳ → 🎤) |
| Click menu bar icon | Open menu |
| History submenu | Shows recent transcriptions with model and latency — click any to re-copy |
| Model submenu | Switch models |

## Running manually

```bash
source .venv/bin/activate
./Wisper.app/Contents/MacOS/Wisper
```

To stop the login item:
```bash
launchctl unload ~/Library/LaunchAgents/com.wisper.app.plist
```

## Models

| Model | Size | Speed | Notes |
|---|---|---|---|
| `tiny.en` | 75 MB | ~0.3s | fastest, rough accuracy |
| `base.en` | 145 MB | ~0.8s | good balance (default) |
| `small.en` | 465 MB | ~2s | better accuracy |
| `medium.en` | 1.5 GB | ~5s | noticeably better |
| `distil-large-v3` | 1.5 GB | ~4s | near large-v3 quality, best accuracy/speed tradeoff |

Switch models from the menu bar — the new model downloads on first use and is cached.

Config and history are stored in `~/.wisper/`.
