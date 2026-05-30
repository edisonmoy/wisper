# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (latest) | Yes |

## Reporting a Vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

Report security issues by emailing the maintainer directly. Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept code
- The version of Wisper affected
- Any suggested fix, if you have one

You will receive a response within 72 hours. If the issue is confirmed, a patch will be released as quickly as possible and you will be credited in the release notes (unless you prefer to remain anonymous).

## Security Model

Wisper is a local-only application. Its security properties:

**What is protected:**
- All audio is processed on-device. No audio is transmitted over any network.
- Transcribed text is stored only in `~/.wisper/history.db` (local SQLite, not synced).
- Clipboard contents are snapshotted before paste and restored immediately after — they are held in memory only for the duration of the paste operation.
- The update mechanism verifies the remote URL before applying any git pull.

**What is not protected:**
- `~/.wisper/history.db` stores transcription text in plaintext. Anyone with access to your filesystem can read your transcription history. Encrypt your home directory if this is a concern.
- `~/.wisper/wisper.log` may contain transcribed text snippets in log lines. The log rotates at 5 MB × 3 backups.
- Wisper is not code-signed or notarized. The installer clears the macOS quarantine bit automatically. Do not install Wisper from untrusted forks.

## Dependency Security

Wisper pins dependencies in `requirements.txt`. To audit for known CVEs:

```bash
pip install pip-audit
pip-audit -r requirements.txt
```
