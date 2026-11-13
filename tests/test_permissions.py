"""Tests for permissions.py — macOS frameworks are replaced via sys.modules."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import permissions


def _avf(status):
    avf = MagicMock()
    avf.AVCaptureDevice.authorizationStatusForMediaType_.return_value = status
    return avf


def _app_services(trusted):
    svc = MagicMock()
    svc.kAXTrustedCheckOptionPrompt = "AXTrustedCheckOptionPrompt"
    svc.AXIsProcessTrusted.return_value = trusted
    return svc


# ---------------------------------------------------------------- identity


def test_responsible_binary_prefers_launcher_bundle(tmp_path, monkeypatch):
    bundle = tmp_path / "Wisper.app"
    bundle.mkdir()
    monkeypatch.setenv("WISPER_APP_BUNDLE", str(bundle))
    assert permissions.responsible_binary() == str(bundle)
    assert permissions.responsible_name() == "Wisper"


def test_responsible_binary_ignores_missing_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("WISPER_APP_BUNDLE", str(tmp_path / "gone.app"))
    assert permissions.responsible_binary() == os.path.realpath(sys.executable)


def test_responsible_binary_resolves_symlinks(monkeypatch):
    monkeypatch.delenv("WISPER_APP_BUNDLE", raising=False)
    with patch.object(permissions.sys, "executable", "/venv/bin/python3"):
        with patch.object(permissions.os.path, "realpath", return_value="/real/python3.11"):
            assert permissions.responsible_binary() == "/real/python3.11"
            assert permissions.responsible_name() == "python3.11"


def test_responsible_binary_is_absolute(monkeypatch):
    monkeypatch.delenv("WISPER_APP_BUNDLE", raising=False)
    assert os.path.isabs(permissions.responsible_binary())


def test_open_settings_opens_privacy_pane():
    with patch("permissions.subprocess.run") as mock_run:
        permissions.open_settings("Microphone")
    mock_run.assert_called_once_with(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"]
    )


# ---------------------------------------------------------------- microphone


@pytest.mark.parametrize(
    "av_status, expected",
    [(0, "missing"), (1, "denied"), (2, "denied"), (3, "granted")],
)
def test_microphone_status_maps_av_authorization(av_status, expected):
    with patch.dict(sys.modules, {"AVFoundation": _avf(av_status)}):
        assert permissions.microphone_status() == expected


def test_microphone_status_missing_without_avfoundation():
    with patch.dict(sys.modules, {"AVFoundation": None}):
        assert permissions.microphone_status() == "missing"


def test_request_microphone_shows_native_prompt():
    avf = _avf(0)
    with patch.dict(sys.modules, {"AVFoundation": avf}):
        with patch("permissions.open_settings") as mock_open:
            permissions.request_microphone()
    mock_open.assert_not_called()
    call = avf.AVCaptureDevice.requestAccessForMediaType_completionHandler_.call_args
    assert call.args[0] is avf.AVMediaTypeAudio
    assert call.args[1](True) is None  # completion handler is a harmless no-op


def test_request_microphone_opens_settings_after_denial():
    avf = _avf(2)
    with patch.dict(sys.modules, {"AVFoundation": avf}):
        with patch("permissions.open_settings") as mock_open:
            permissions.request_microphone()
    mock_open.assert_called_once_with("Microphone")
    avf.AVCaptureDevice.requestAccessForMediaType_completionHandler_.assert_not_called()


def test_request_microphone_opens_settings_without_avfoundation():
    with patch.dict(sys.modules, {"AVFoundation": None}):
        with patch("permissions.open_settings") as mock_open:
            permissions.request_microphone()
    mock_open.assert_called_once_with("Microphone")


# ------------------------------------------------------------- accessibility


@pytest.mark.parametrize("trusted, expected", [(True, "granted"), (False, "missing")])
def test_accessibility_status(trusted, expected):
    with patch.dict(sys.modules, {"ApplicationServices": _app_services(trusted)}):
        assert permissions.accessibility_status() == expected


def test_accessibility_status_missing_without_framework():
    with patch.dict(sys.modules, {"ApplicationServices": None}):
        assert permissions.accessibility_status() == "missing"


def test_request_accessibility_registers_app_and_opens_settings():
    svc = _app_services(False)
    with patch.dict(sys.modules, {"ApplicationServices": svc}):
        with patch("permissions.open_settings") as mock_open:
            permissions.request_accessibility()
    svc.AXIsProcessTrustedWithOptions.assert_called_once_with({"AXTrustedCheckOptionPrompt": True})
    mock_open.assert_called_once_with("Accessibility")


def test_request_accessibility_still_opens_settings_without_framework():
    with patch.dict(sys.modules, {"ApplicationServices": None}):
        with patch("permissions.open_settings") as mock_open:
            permissions.request_accessibility()
    mock_open.assert_called_once_with("Accessibility")


# -------------------------------------------------------------- all_granted


@pytest.mark.parametrize(
    "mic, ax, expected",
    [
        ("granted", "granted", True),
        ("granted", "missing", False),
        ("denied", "granted", False),
    ],
)
def test_all_granted_checks_live_status(mic, ax, expected):
    with (
        patch("permissions.microphone_status", return_value=mic),
        patch("permissions.accessibility_status", return_value=ax),
    ):
        assert permissions.all_granted() is expected


def test_current_statuses():
    with (
        patch("permissions.microphone_status", return_value="granted"),
        patch("permissions.accessibility_status", return_value="missing"),
    ):
        assert permissions.current_statuses() == {"mic": "granted", "ax": "missing"}


@pytest.mark.parametrize(
    "statuses, expected",
    [
        ({"mic": "granted", "ax": "granted"}, True),
        ({"mic": "granted", "ax": "denied"}, False),
        ({}, False),  # nothing checked yet
    ],
)
def test_all_granted_with_given_statuses(statuses, expected):
    assert permissions.all_granted(statuses) is expected
