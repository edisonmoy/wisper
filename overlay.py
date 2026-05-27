import math
import objc
from AppKit import (
    NSObject,
    NSView,
    NSPanel,
    NSVisualEffectView,
    NSColor,
    NSBezierPath,
    NSScreen,
    NSBackingStoreBuffered,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
)
from Foundation import NSMakeRect, NSTimer

PANEL_W = 320
PANEL_H = 68
CORNER_R = 34

BAR_W = 3
BAR_GAP = 2

# NSWindowStyleMask integer values
_BORDERLESS = 0
_NONACTIVATING_PANEL = 1 << 7

# NSVisualEffectMaterial / State
_MATERIAL_HUD = 6           # NSVisualEffectMaterialHUDWindow
_BLENDING_BEHIND = 0        # NSVisualEffectBlendingModeBehindWindow
_STATE_ACTIVE = 1           # NSVisualEffectStateActive

_FLOATING_LEVEL = 8         # NSFloatingWindowLevel
_STATIONARY = 1 << 4        # NSWindowCollectionBehaviorStationary


class _WaveformView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_WaveformView, self).initWithFrame_(frame)
        if self is None:
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
            bar_h = max(3.0, norm * h * 0.78)
            x = x0 + i * (BAR_W + BAR_GAP)
            y = (h - bar_h) / 2.0
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, BAR_W, bar_h), 1.5, 1.5
            )
            NSColor.colorWithWhite_alpha_(1.0, 0.35 + 0.65 * norm).setFill()
            path.fill()

    def isOpaque(self):
        return False


class RecordingOverlay(NSObject):
    """Floating non-interactive waveform overlay shown while recording."""

    @classmethod
    def create(cls, get_waveform_fn):
        obj = cls.alloc().init()
        obj._get_waveform = get_waveform_fn
        obj._visible = False
        obj._tick = 0
        obj._waveform_view = None
        obj._dot_layer = None
        obj._panel = None
        obj._build_panel()
        # 30 fps refresh on the main run loop
        obj._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 30, obj, 'tick:', None, True
        )
        return obj

    # ---------------------------------------------------------------- setup

    def _build_panel(self):
        screen = NSScreen.mainScreen()
        if screen is None:
            return

        sf = screen.frame()
        x = (sf.size.width - PANEL_W) / 2
        y = 100  # px above the bottom edge (clears a typical Dock)
        frame = NSMakeRect(x, y, PANEL_W, PANEL_H)

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, _BORDERLESS | _NONACTIVATING_PANEL, NSBackingStoreBuffered, False
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setLevel_(_FLOATING_LEVEL)
        panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | _STATIONARY)

        content = panel.contentView()

        # Glassmorphic blur background
        effect = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        effect.setMaterial_(_MATERIAL_HUD)
        effect.setBlendingMode_(_BLENDING_BEHIND)
        effect.setState_(_STATE_ACTIVE)
        effect.setWantsLayer_(True)
        effect.layer().setCornerRadius_(CORNER_R)
        effect.layer().setMasksToBounds_(True)
        content.addSubview_(effect)

        # Waveform bars (leave ~30px on the left for the dot)
        wv = _WaveformView.alloc().initWithFrame_(NSMakeRect(30, 0, PANEL_W - 38, PANEL_H))
        effect.addSubview_(wv)
        self._waveform_view = wv

        # Pulsing red recording indicator dot
        dot_d = 8
        dot = NSView.alloc().initWithFrame_(
            NSMakeRect((30 - dot_d) / 2, (PANEL_H - dot_d) / 2, dot_d, dot_d)
        )
        dot.setWantsLayer_(True)
        dot.layer().setCornerRadius_(dot_d / 2)
        dot.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
        effect.addSubview_(dot)
        self._dot_layer = dot.layer()

        self._panel = panel

    # ----------------------------------------------------------- public API
    # These selectors are called via performSelectorOnMainThread from any thread.

    def show_(self, _):
        self._visible = True
        if self._panel:
            self._panel.orderFrontRegardless()

    def hide_(self, _):
        self._visible = False
        if self._panel:
            self._panel.orderOut_(None)

    # ---------------------------------------------------------------- timer

    def tick_(self, _timer):
        self._tick += 1
        if not self._visible:
            return
        if self._waveform_view is not None:
            self._waveform_view.setSamples_(self._get_waveform())
        if self._dot_layer is not None:
            alpha = 0.55 + 0.45 * math.sin(self._tick * 2 * math.pi / 30)
            self._dot_layer.setOpacity_(alpha)
