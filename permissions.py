"""macOS privacy-permission checks and requests used by the setup checklist.

Every function degrades gracefully when the relevant PyObjC framework is
missing (e.g. on Linux CI, or before an update has installed a new
dependency), so callers never need their own try/except.
"""

import os
import subprocess
import sys
from typing import Literal

# "missing" = not granted yet (never asked, or asked and the toggle is off).
# "denied"  = the user explicitly refused; only the Settings pane can fix it.
Status = Literal["granted", "missing", "denied"]

_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_{}"

# AVAuthorizationStatus values
_AV_RESTRICTED = 1
_AV_DENIED = 2
_AV_AUTHORIZED = 3


def responsible_binary() -> str:
    """Path of the app or executable macOS attributes Wisper's permissions to.

    Launched through Wisper.app, the native launcher (launcher.c) spawns
    Python as a child and exports WISPER_APP_BUNDLE; macOS then attributes
    permissions to Wisper.app. Without it (an install still using the old
    shell-script launcher, which ``exec``s Python), the interpreter binary
    itself — e.g. ``python3.11`` — is what shows up in System Settings.
    Either way, this is the name users look for in the lists and the file
    they'd drag in to add it manually.
    """
    bundle = os.environ.get("WISPER_APP_BUNDLE")
    if bundle and os.path.isdir(bundle):
        return bundle
    return os.path.realpath(sys.executable)


def responsible_name() -> str:
    name = os.path.basename(responsible_binary())
    return name.removesuffix(".app")


def open_settings(pane: str) -> None:
    """Open System Settings → Privacy & Security → ``pane`` (e.g. "Microphone")."""
    subprocess.run(["open", _SETTINGS_URL.format(pane)])


# ---------------------------------------------------------------- microphone


def microphone_status() -> Status:
    try:
        import AVFoundation  # type: ignore  # macOS-only
    except ImportError:
        return "missing"
    status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
        AVFoundation.AVMediaTypeAudio
    )
    if status == _AV_AUTHORIZED:
        return "granted"
    if status in (_AV_DENIED, _AV_RESTRICTED):
        return "denied"
    return "missing"


def request_microphone() -> None:
    """Show the native microphone prompt, or open Settings if it can't be shown.

    macOS only prompts once; after a denial the only way back is the
    Settings pane, so go straight there.
    """
    if microphone_status() == "denied":
        open_settings("Microphone")
        return
    try:
        import AVFoundation  # type: ignore  # macOS-only
    except ImportError:
        open_settings("Microphone")
        return
    # The result is picked up by the checklist's status polling.
    AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVFoundation.AVMediaTypeAudio, lambda _granted: None
    )


# ------------------------------------------------------------- accessibility


def accessibility_status() -> Status:
    try:
        import ApplicationServices  # type: ignore  # macOS-only
    except ImportError:
        return "missing"
    return "granted" if ApplicationServices.AXIsProcessTrusted() else "missing"


def request_accessibility() -> None:
    """Add Wisper to the Accessibility list and open it so the user can flip the toggle.

    AXIsProcessTrustedWithOptions with the prompt option is what inserts the
    (switched-off) row into System Settings; a plain AXIsProcessTrusted()
    check never does.
    """
    try:
        import ApplicationServices  # type: ignore  # macOS-only

        ApplicationServices.AXIsProcessTrustedWithOptions(
            {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
        )
    except ImportError:
        pass
    open_settings("Accessibility")


def current_statuses() -> dict[str, Status]:
    """Status of every permission Wisper needs, keyed "mic" / "ax"."""
    return {"mic": microphone_status(), "ax": accessibility_status()}


def all_granted(statuses: dict[str, Status] | None = None) -> bool:
    """True if every permission is granted (checks live status if none given)."""
    if statuses is None:
        statuses = current_statuses()
    return bool(statuses) and all(s == "granted" for s in statuses.values())
