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
| **AI** | Everything Basic does, plus context-aware "like" removal, run-on sentence fixes, implicit list detection | ~400–550 ms |

### AI Cleanup — how it works

The AI mode runs a small language model **entirely on your device** — no internet connection, no cloud API. It uses Apple's [MLX](https://github.com/ml-explore/mlx) framework to run [Qwen 2.5 0.5B](https://huggingface.co/mlx-community/Qwen2.5-0.5B-Instruct-4bit) (~400 MB) on Apple Silicon's Neural Engine and GPU.

**Apple Silicon only (M1 and later).** On Intel Macs, AI mode silently falls back to Basic. The model downloads automatically on first use and is cached at `~/.cache/huggingface/`.

---

## Privacy

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

---

## Updating

Click the menu bar icon and select **Check for Updates**. Wisper will download and restart automatically.

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
