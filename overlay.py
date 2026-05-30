import objc
from AppKit import (
    NSAppearance,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSObject,
    NSPanel,
    NSScreen,
    NSView,
    NSVisualEffectView,
    NSWindowCollectionBehaviorMoveToActiveSpace,
)
from Foundation import NSMakeRect, NSTimer

PANEL_W = 200
PANEL_H = 44
CORNER_R = 22

BAR_W = 2
BAR_GAP = 1

# NSWindowStyleMask integer values
_BORDERLESS = 0
_NONACTIVATING_PANEL = 1 << 7

# NSVisualEffectMaterial / State
_MATERIAL_HUD = 6  # NSVisualEffectMaterialHUDWindow
_BLENDING_BEHIND = 0  # NSVisualEffectBlendingModeBehindWindow
_STATE_ACTIVE = 1  # NSVisualEffectStateActive

_FLOATING_LEVEL = 8  # NSFloatingWindowLevel

_PANEL_ALPHA = 0.82  # overall window opacity


class _WaveformView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_WaveformView, self).initWithFrame_(frame)
        if self is None:  # pragma: no cover — NSView.alloc().initWithFrame_ never returns nil
            return None
        self._samples = []
        return self

    def setSamples_(self, samples):
        self._samples = samples
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect):
        samples = self._samples
        if not samples:
            return

        max_v = max(samples)
        if max_v < 0.001:
            max_v = 0.001

        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height
        n = len(samples)

        total_w = n * (BAR_W + BAR_GAP) - BAR_GAP
        x0 = (w - total_w) / 2.0

        for i, v in enumerate(samples):
            norm = min(v / max_v, 1.0)
            bar_h = max(2.0, norm * h * 0.75)
            x = x0 + i * (BAR_W + BAR_GAP)
            y = (h - bar_h) / 2.0
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, BAR_W, bar_h), 1.0, 1.0
            )
            NSColor.colorWithWhite_alpha_(1.0, 0.3 + 0.7 * norm).setFill()
            path.fill()

    def isOpaque(self):
        return False


def create_recording_overlay(get_waveform_fn) -> "RecordingOverlay":
    """Module-level factory — keeps the extra arg away from PyObjC's selector scanner."""
    obj = RecordingOverlay.alloc().init()
    obj._get_waveform = get_waveform_fn
    obj._visible = False
    obj._waveform_view = None
    obj._panel = None
    obj._build_panel()
    # 30 fps refresh on the main run loop
    obj._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / 30, obj, "tick:", None, True
    )
    return obj


class RecordingOverlay(NSObject):
    """Floating non-interactive waveform overlay shown while recording."""

    # ---------------------------------------------------------------- setup

    @objc.python_method
    def _build_panel(self):
        screen = NSScreen.mainScreen()
        if screen is None:
            return

        sf = screen.frame()
        x = sf.origin.x + (sf.size.width - PANEL_W) / 2
        y = sf.origin.y + 80
        frame = NSMakeRect(x, y, PANEL_W, PANEL_H)

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, _BORDERLESS | _NONACTIVATING_PANEL, NSBackingStoreBuffered, False
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setLevel_(_FLOATING_LEVEL)
        panel.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)
        panel.setAlphaValue_(_PANEL_ALPHA)
        # Force dark appearance so the HUD material renders near-black.
        panel.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))

        content = panel.contentView()

        effect = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        effect.setMaterial_(_MATERIAL_HUD)
        effect.setBlendingMode_(_BLENDING_BEHIND)
        effect.setState_(_STATE_ACTIVE)
        effect.setWantsLayer_(True)
        effect.layer().setCornerRadius_(CORNER_R)
        effect.layer().setMasksToBounds_(True)
        content.addSubview_(effect)

        wv = _WaveformView.alloc().initWithFrame_(NSMakeRect(6, 0, PANEL_W - 12, PANEL_H))
        effect.addSubview_(wv)
        self._waveform_view = wv

        self._panel = panel

    @objc.python_method
    def _reposition_to_cursor_screen(self):
        """Move the panel to the bottom-centre of whichever screen the cursor is on."""
        if self._panel is None:
            return
        mouse = NSEvent.mouseLocation()
        screen = NSScreen.mainScreen()
        for s in NSScreen.screens():
            sf = s.frame()
            if (
                sf.origin.x <= mouse.x < sf.origin.x + sf.size.width
                and sf.origin.y <= mouse.y < sf.origin.y + sf.size.height
            ):
                screen = s
                break
        sf = screen.frame()
        x = sf.origin.x + (sf.size.width - PANEL_W) / 2
        y = sf.origin.y + 80
        self._panel.setFrameOrigin_((x, y))

    # ----------------------------------------------------------- public API
    # These selectors are called via performSelectorOnMainThread from any thread.

    def show_(self, _):
        self._reposition_to_cursor_screen()
        self._visible = True
        if self._panel:
            self._panel.orderFrontRegardless()

    def hide_(self, _):
        self._visible = False
        if self._panel:
            self._panel.orderOut_(None)

    # ---------------------------------------------------------------- timer

    def tick_(self, _timer):
        if not self._visible:
            return
        if self._waveform_view is not None:
            self._waveform_view.setSamples_(self._get_waveform())
