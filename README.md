# Wisper

> macOS menu bar app for instant voice-to-text — hold a hotkey, speak, release, and your transcription is pasted wherever your cursor is.

Inspired by and UI-compatible with [WisperFlow](https://wisprflow.ai/). If you've used WisperFlow, Wisper will feel immediately familiar: same hotkey-to-paste workflow, same menu bar experience.

---

## Features

- **One key to dictate** — hold `fn`, speak, release. Text appears at your cursor instantly.
- **Fully offline** — transcription runs on-device via [OpenAI Whisper](https://github.com/openai/whisper). No audio or text ever leaves your machine.
- **Multiple models** — switch between tiny/base/small/medium/distil-large from the menu bar.
- **Text cleanup** — automatically remove filler words and polish transcriptions (see below).
- **Clipboard-safe** — your clipboard is fully restored after every paste, including images.
- **History** — recent transcriptions with model and latency, click any to re-copy.

---

## Install

```bash
git clone https://github.com/edisonmoy/wisper.git
cd wisper
bash install.sh
```

The installer sets up a virtual environment, builds `Wisper.app`, and registers it as a login item so it starts automatically.

### Required permissions

macOS will prompt on first use. Grant both:

1. **Accessibility** — System Settings → Privacy & Security → Accessibility → enable Wisper
2. **Microphone** — System Settings → Privacy & Security → Microphone → enable Wisper

If either permission is missing, Wisper shows a warning in the menu bar.

### fn key conflict

If the Globe/fn key opens the emoji picker instead of recording:

> System Settings → Keyboard → "Press Globe key to" → set to **Do Nothing**

---

## Usage

Hold `fn` to record, release to transcribe. Text is pasted at your cursor instantly.

Access history, model selection, and text cleanup from the menu bar icon.

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

## Text Cleanup

Choose a cleanup mode from **Text Cleanup** in the menu bar:

| Mode | What it does | Latency |
|---|---|---|
| **None** | Raw Whisper output | 0 ms |
| **Basic** | Removes um/uh, stutters, "you know", "I mean", "right?"; detects first/second/third lists | ~0 ms |
| **AI** | Everything Basic does, plus context-aware rewriting and run-on sentence fixes | ~400–550 ms |

### AI Cleanup — how it works

The AI mode runs a small language model **entirely on your device** — no internet connection, no cloud API. It uses Apple's [MLX](https://github.com/ml-explore/mlx) framework to run [Qwen 2.5 0.5B](https://huggingface.co/mlx-community/Qwen2.5-0.5B-Instruct-4bit) (~400 MB) on Apple Silicon's Neural Engine and GPU.

**Apple Silicon only (M1 and later).** On Intel Macs, AI mode silently falls back to Basic. The model downloads automatically on first use and is cached at `~/.cache/huggingface/`.

---

## Privacy & Security

**Your audio never leaves your device.** Transcription runs entirely on your CPU using a local Whisper model. AI cleanup runs on-device via MLX. No data is sent to any server.

The only network connections Wisper makes:

| When | What |
|---|---|
| First launch | Downloads the Whisper model from Hugging Face (~75 MB – 1.5 GB depending on model) |
| AI mode, first use | Downloads the Qwen 2.5 0.5B cleanup model from Hugging Face (~400 MB) |
| Startup (optional) | Hugging Face makes a lightweight metadata version-check — no audio involved |
| Background | Checks GitHub for app updates via `git fetch` |

To disable the Hugging Face version-check after models are downloaded:

```bash
echo 'export HF_HUB_OFFLINE=1' >> ~/.zshrc
```

### Transcription history

Recent transcriptions are stored in plaintext at `~/.wisper/history.db` (SQLite). This file is local only and never uploaded. Use **Clear History** in the menu bar to wipe it, or delete the file manually:

```bash
rm ~/.wisper/history.db
```

### Update integrity

Updates are fetched via `git fetch` from the configured GitHub remote. Wisper verifies the remote URL before applying any update. Only updates from the expected origin are accepted.

---

## Architecture

```
fn key pressed
     │
     ▼
HotkeyManager         pynput listener; debounced press/release
     │ on_start / on_stop
     ▼
AudioRecorder         sounddevice InputStream; accumulates float32 chunks
     │ numpy array
     ▼
Transcriber           faster-whisper (CTranslate2); lazy-loads WhisperModel
     │ raw text
     ▼
PostProcessor         regex filler removal → optional MLX rewrite (AI mode)
     │ cleaned text
     ▼
WisperApp._paste()    snapshots clipboard → pbpaste/type text → restores clipboard
     │
     ▼
cursor                text appears wherever focus is
```

Supporting components:
- **RecordingOverlay** — floating waveform panel, tracks the cursor's screen
- **HistoryDB** — SQLite store for recent transcriptions (`~/.wisper/history.db`)
- **Config** — JSON config at `~/.wisper/config.json`; validated on load
- **Updater** — background `git fetch` + `git pull` with remote URL verification
- **Logging** — rotating log at `~/.wisper/wisper.log` (5 MB × 3 backups)

---

## Testing & Contributing

### Run tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Full test suite (100% branch coverage)
pytest tests/ -k "not TestPostProcessorAI and not benchmark_ai and not benchmark_report" \
    --cov=. --cov-branch --cov-report=term-missing -q

# Including AI/benchmark tests (requires Apple Silicon + MLX)
pytest tests/ --cov=. --cov-branch --cov-report=term-missing -q
```

### Lint

```bash
ruff check .
ruff format --check .
```

### CI

GitHub Actions runs the full test suite (minus Apple Silicon tests) on every push and pull request to `main`. Coverage is enforced at 100% branch coverage. See `.github/workflows/ci.yml`.

### Project structure

```
app.py            WisperApp — menu bar UI, hotkey callbacks, paste logic
config.py         Config dataclass; JSON persistence; validation
history.py        HistoryDB — SQLite CRUD for transcription history
hotkey.py         HotkeyManager — fn key press/release detection
overlay.py        RecordingOverlay — floating waveform panel
postprocessor.py  PostProcessor — regex + optional MLX text cleanup
recorder.py       AudioRecorder — sounddevice microphone capture
transcriber.py    Transcriber — faster-whisper inference wrapper
updater.py        check_for_updates / install_update — git-based auto-update
utils.py          format_age — human-readable time formatting

tests/            pytest suite (100% branch coverage)
install.sh        One-command installer
uninstall.sh      One-command uninstaller
```

---

## Updating

Click the menu bar icon and select **Check for Updates**. Wisper will download and restart automatically.

---

## Uninstall

```bash
bash uninstall.sh
```

Or manually:

```bash
launchctl unload ~/Library/LaunchAgents/com.wisper.app.plist
rm ~/Library/LaunchAgents/com.wisper.app.plist
```

To also remove app data:

```bash
rm -rf ~/.wisper/
```

To also remove cached models (~75 MB – 2 GB):

```bash
rm -rf ~/.cache/huggingface/
```

---

## Debugging

Run the app directly in your terminal to see live logs:

```bash
./Wisper.app/Contents/MacOS/Wisper
```

Logs are also written to `~/.wisper/wisper.log` with rotation (5 MB × 3 backups).

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Security

To report a vulnerability, see [SECURITY.md](SECURITY.md).
