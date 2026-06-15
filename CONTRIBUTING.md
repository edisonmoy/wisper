# Contributing to Wisper

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

## Project structure

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

## Running tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Full test suite (100% branch coverage)
pytest tests/ -k "not TestPostProcessorAI and not benchmark_ai and not benchmark_report" \
    --cov=. --cov-branch --cov-report=term-missing -q

# Including AI/benchmark tests (requires Apple Silicon + MLX)
pytest tests/ --cov=. --cov-branch --cov-report=term-missing -q
```

## Lint

```bash
ruff check .
ruff format --check .
```

## CI

GitHub Actions runs the full test suite (minus Apple Silicon tests) on every push and pull request to `main`. Coverage is enforced at 100% branch coverage. See `.github/workflows/ci.yml`.

## Debugging

Run the app directly in your terminal to see live logs:

```bash
./Wisper.app/Contents/MacOS/Wisper
```

Logs are also written to `~/.wisper/wisper.log` with rotation (5 MB × 3 backups).
