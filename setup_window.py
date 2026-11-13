"""First-run permission checklist window.

Shows one row per permission with a button that opens the right prompt or
System Settings pane, and polls once a second so each row flips to a green
checkmark the moment macOS reports it as granted — no restart needed.
"""

import objc
from AppKit import (
    NSURL,
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSDraggingItem,
    NSFont,
    NSImage,
    NSImageSymbolConfiguration,
    NSImageView,
    NSObject,
    NSScreen,
    NSTextField,
    NSView,
    NSWindow,
    NSWorkspace,
)
from Foundation import NSMakeRect, NSTimer

import permissions
from config import REPO_DIR

WIN_W = 480
WIN_H = 372
PAD = 24
ROW_H = 72
BTN_W = 132

# NSWindowStyleMask
_TITLED = 1 << 0
_CLOSABLE = 1 << 1
_FULL_SIZE_CONTENT = 1 << 15
_FLOATING_LEVEL = 3  # NSFloatingWindowLevel — stays above System Settings
_DRAG_OP_COPY = 1  # NSDragOperationCopy
_TITLE_HIDDEN = 1  # NSWindowTitleHidden
_BADGE_PT = 20.0

_INTRO = "Wisper needs two permissions."
_ALL_SET = "You're all set."

# Rows: (key, title, detail shown until granted)
_STEPS = [
    ("mic", "Microphone", "To hear your voice."),
    ("ax", "Accessibility", "To detect your hotkey and paste text."),
]


def _label(text, size=13.0, bold=False, secondary=False):
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if secondary:
        field.setTextColor_(NSColor.secondaryLabelColor())
    return field


def _drag_hint_text(name):
    if name == "Wisper":
        return "Turn on Wisper. Not listed? Drag this in:"
    # Not launched through Wisper.app, so macOS lists the Python interpreter.
    return f"Turn on {name} (that's Wisper). Not listed? Drag this in:"


def _wisper_icon():
    """Wisper's app icon if it's been generated, else the binary's generic Finder icon."""
    icns = REPO_DIR / "assets" / "wisper.icns"
    if icns.exists():
        return NSImage.alloc().initWithContentsOfFile_(str(icns))
    return NSWorkspace.sharedWorkspace().iconForFile_(permissions.responsible_binary())


class _DragTile(NSView):
    """Icon + name of the binary macOS tracks permissions for, draggable into Settings lists.

    Fallback for when the row isn't already in the Accessibility list: drag
    the tile onto the list to add it.
    """

    def mouseDown_(self, event):
        path = permissions.responsible_binary()
        item = NSDraggingItem.alloc().initWithPasteboardWriter_(NSURL.fileURLWithPath_(path))
        item.setDraggingFrame_contents_(self.bounds(), self._icon)
        self.beginDraggingSessionWithItems_event_source_([item], event, self)

    def draggingSession_sourceOperationMaskForDraggingContext_(self, _session, _context):
        return _DRAG_OP_COPY


def create_setup_window(on_change) -> "SetupWindowController":
    """Module-level factory — keeps the extra arg away from PyObjC's selector scanner.

    ``on_change(statuses)`` is called on the main thread whenever any
    permission's status changes, with a dict like {"mic": "granted", ...}.
    """
    obj = SetupWindowController.alloc().init()
    obj._on_change = on_change
    obj._window = None
    obj._rows = {}
    obj._timer = None
    obj._statuses = {}
    obj._done_button = None
    obj._drag_hint = []
    obj._intro = None
    return obj


class SetupWindowController(NSObject):
    # ---------------------------------------------------------------- build

    @objc.python_method
    def _build(self):
        frame = NSMakeRect(0, 0, WIN_W, WIN_H)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, _TITLED | _CLOSABLE | _FULL_SIZE_CONTENT, NSBackingStoreBuffered, False
        )
        win.setTitle_("Set up Wisper")
        win.setTitlebarAppearsTransparent_(True)
        win.setTitleVisibility_(_TITLE_HIDDEN)
        win.setReleasedWhenClosed_(False)
        win.setLevel_(_FLOATING_LEVEL)
        win.setDelegate_(self)
        content = win.contentView()

        def place(view, x, top, w, h):
            # AppKit's origin is bottom-left; lay out from the top for readability.
            view.setFrame_(NSMakeRect(x, WIN_H - top - h, w, h))
            content.addSubview_(view)

        place(_label("Set up Wisper", 22, bold=True), PAD, 40, WIN_W - 2 * PAD, 28)
        intro = _label(_INTRO, secondary=True)
        intro.setLineBreakMode_(0)  # NSLineBreakByWordWrapping
        intro.setMaximumNumberOfLines_(2)
        place(intro, PAD, 72, WIN_W - 2 * PAD, 36)
        self._intro = intro

        badge_config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(_BADGE_PT, 0.0)

        top = 124
        for key, title, detail in _STEPS:
            badge = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, 26, 26))
            badge.setSymbolConfiguration_(badge_config)
            place(badge, PAD, top, 26, 26)
            place(_label(title, 14, bold=True), PAD + 40, top, 260, 20)
            detail_label = _label(detail, 12, secondary=True)
            place(detail_label, PAD + 40, top + 22, WIN_W - 2 * PAD - 40 - BTN_W - 8, 32)
            detail_label.setLineBreakMode_(0)
            detail_label.setMaximumNumberOfLines_(2)
            button = NSButton.buttonWithTitle_target_action_("Allow", self, f"{key}Clicked:")
            button.setBezelColor_(NSColor.controlAccentColor())
            place(button, WIN_W - PAD - BTN_W, top + 2, BTN_W, 28)
            self._rows[key] = {"badge": badge, "detail": detail_label, "button": button}
            top += ROW_H

        # Drag fallback under the Accessibility row (hidden until that step is started).
        hint = _label(_drag_hint_text(permissions.responsible_name()), 11, secondary=True)
        hint.setLineBreakMode_(0)
        hint.setMaximumNumberOfLines_(2)
        place(hint, PAD + 40, top - 14, WIN_W - 2 * PAD - 40 - 80, 30)

        tile = _DragTile.alloc().initWithFrame_(NSMakeRect(0, 0, 64, 52))
        icon = _wisper_icon()
        icon.setSize_((36, 36))
        tile._icon = icon
        icon_view = NSImageView.alloc().initWithFrame_(NSMakeRect(14, 14, 36, 36))
        icon_view.setImage_(icon)
        tile.addSubview_(icon_view)
        name = _label(permissions.responsible_name(), 9, secondary=True)
        name.setFrame_(NSMakeRect(0, 0, 64, 12))
        name.setAlignment_(1)  # NSTextAlignmentCenter
        tile.addSubview_(name)
        tile.setToolTip_("Drag into the Accessibility list in System Settings")
        place(tile, WIN_W - PAD - 64, top - 20, 64, 52)
        self._drag_hint = [hint, tile]

        done = NSButton.buttonWithTitle_target_action_("Later", self, "doneClicked:")
        place(done, WIN_W - PAD - 96, WIN_H - PAD - 28, 96, 28)
        self._done_button = done

        self._window = win

    # ------------------------------------------------------------ public API

    def show_(self, _):
        if self._window is None:
            self._build()
        self._refresh(force=True)
        # Park on the left so System Settings (which opens centered) stays visible.
        screen = NSScreen.mainScreen()
        if screen is not None:
            vf = screen.visibleFrame()
            self._window.setFrameOrigin_(
                (vf.origin.x + 40, vf.origin.y + (vf.size.height - WIN_H) / 2)
            )
        NSApp.activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)
        if self._timer is None:
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0, self, "tick:", None, True
            )

    def close_(self, _):
        if self._window is not None:
            self._window.orderOut_(None)
        self._stop_timer_if_done()

    # --------------------------------------------------------------- actions

    def micClicked_(self, _sender):
        permissions.request_microphone()

    def axClicked_(self, _sender):
        permissions.request_accessibility()
        for view in self._drag_hint:
            view.setHidden_(False)

    def doneClicked_(self, _sender):
        self.close_(None)

    def windowWillClose_(self, _notification):
        self._stop_timer_if_done()

    def tick_(self, _timer):
        self._refresh()

    # -------------------------------------------------------------- internal

    @objc.python_method
    def _all_granted(self):
        return bool(self._statuses) and all(s == "granted" for s in self._statuses.values())

    @objc.python_method
    def _stop_timer_if_done(self):
        # Keep polling after "Later" so a permission granted afterwards still
        # reaches the app (hotkey restart, menu bar warning cleared).
        if self._timer is not None and self._all_granted():
            self._timer.invalidate()
            self._timer = None

    @objc.python_method
    def _refresh(self, force=False):
        statuses = {
            "mic": permissions.microphone_status(),
            "ax": permissions.accessibility_status(),
        }
        if statuses == self._statuses and not force:
            return
        changed = statuses != self._statuses
        self._statuses = statuses

        for i, (key, _title, detail) in enumerate(_STEPS, start=1):
            self._render_row(i, key, detail, statuses[key])

        # Only reveal the drag fallback once the user has started that step.
        if force or statuses["ax"] == "granted":
            for view in self._drag_hint:
                view.setHidden_(True)

        everything = self._all_granted()
        self._done_button.setTitle_("Done" if everything else "Later")
        self._done_button.setKeyEquivalent_("\r" if everything else "")
        self._intro.setStringValue_(_ALL_SET if everything else _INTRO)

        if changed:
            self._on_change(statuses)
        if not self._window.isVisible():
            self._stop_timer_if_done()

    @objc.python_method
    def _render_row(self, index, key, detail, status):
        row = self._rows[key]
        badge, button = row["badge"], row["button"]
        if status == "granted":
            name, color, text = "checkmark.circle.fill", NSColor.systemGreenColor(), "Enabled"
        elif status == "denied":
            name, color = "exclamationmark.circle.fill", NSColor.systemOrangeColor()
            text = "Turned off. Enable it in Settings."
        else:
            name, color, text = f"{index}.circle", NSColor.tertiaryLabelColor(), detail
        badge.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None))
        badge.setContentTintColor_(color)
        row["detail"].setStringValue_(text)
        button.setHidden_(status == "granted")
        if key == "mic" and status == "missing":
            button.setTitle_("Allow")
        else:
            button.setTitle_("Open Settings")
