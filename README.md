# Wisper

> macOS menu bar app for instant voice-to-text — hold a hotkey, speak, release, and your transcription is pasted wherever your cursor is.

Inspired by and UI-compatible with [WhisperFlow](https://github.com/ryanpaulanderson/whisperflow). If you've used WhisperFlow, Wisper will feel immediately familiar: same hotkey-to-paste workflow, same menu bar experience.

---

## Features

- **One key to dictate** — hold `fn`, speak, release. Text appears at your cursor instantly.
- **Fully offline** — transcription runs on-device via [OpenAI Whisper](https://github.com/openai/whisper). No audio or text ever leaves your machine.
- **Multiple models** — switch between tiny/base/small/medium/distil-large from the menu bar.
- **History** — recent transcriptions with model and latency, click any to re-copy.

---

## Privacy

**Your audio never leaves your device.** Transcription runs entirely on your CPU using a local Whisper model. No data is sent to any server.

The only network connections Wisper makes:

| When | What |
|---|---|
| First launch | Downloads the Whisper model from Hugging Face (~75 MB – 1.5 GB depending on model) |
| Startup (optional) | Hugging Face makes a lightweight metadata version-check — no audio involved |
| Background | Checks GitHub for app updates via `git fetch` |

To disable the Hugging Face version-check after the model is downloaded:

```bash
echo 'export HF_HUB_OFFLINE=1' >> ~/.zshrc
```

---

## Install

```bash
git clone https://github.com/edisonmoy/wisper.git
cd wisper
bash install.sh
```

That's it. The installer sets up a virtual environment, builds `Wisper.app`, and registers it as a login item so it starts automatically.

---

## First Run

macOS requires two permissions (you'll be prompted):

1. **Microphone** — granted automatically when you first record
2. **Accessibility** — add manually: **System Settings → Privacy & Security → Accessibility → add Terminal**

> If the `fn` key opens the emoji picker instead of recording:
> **System Settings → Keyboard → Press 🌐 key to → Do Nothing**

---

## Usage

| Action | Result |
|---|---|
| Hold `fn` | Start recording (icon turns 🔴) |
| Release `fn` | Transcribe + paste at cursor (icon → ⏳ → 🎤) |
| Click menu bar icon | Open menu |
| History submenu | Recent transcriptions — click any to re-copy |
| Model submenu | Switch Whisper models |

---

## Models

| Model | Size | Speed |
|---|---|---|
| `tiny.en` | 75 MB | ~0.3 s |
| `base.en` | 145 MB | ~0.8 s (default) |
| `small.en` | 465 MB | ~2 s |
| `medium.en` | 1.5 GB | ~5 s |
| `distil-large-v3` | 1.5 GB | ~4 s (best accuracy/speed) |

Models download on first use and are cached at `~/.cache/huggingface/`. Switch anytime from the menu bar.

---

## Updating

```bash
git pull
bash install.sh
```

For code-only changes (no dependency updates), you can restart without reinstalling:

```bash
launchctl stop com.wisper.app && launchctl start com.wisper.app
```

---

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.wisper.app.plist
rm ~/Library/LaunchAgents/com.wisper.app.plist
```

---

## Debugging

Run the app directly in your terminal to see live logs:

```bash
./Wisper.app/Contents/MacOS/Wisper
```

Config and history are stored in `~/.wisper/`.
