"""
Concrete menu tree for the KeyLab Essential NAV script.

Defines the hierarchical menu. FL Studio side-effects are injected as
callbacks from the processor so this file stays free of heavy FL imports
and is easy to reorder.

Usage (inside ArturiaMidiProcessor.__init__):

    from arturia_menu import MenuSystem, latency_gate
    from arturia_menu_tree import build_menu_tree

    self._menu = MenuSystem(
        self._controller.paged_display(),
        display_hint_fn=self._display_hint,
        gate=latency_gate,
    )
    self._menu.register_tree(build_menu_tree(self))
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from arturia_menu import MenuNode

if TYPE_CHECKING:
    from arturia_processor import ArturiaMidiProcessor


def build_menu_tree(processor: "ArturiaMidiProcessor") -> List[MenuNode]:
    """Return the top-level list of MenuNode instances."""

    # ------------------------------------------------------------------
    # LCD line helpers
    # ------------------------------------------------------------------

    def channel_line() -> str:
        try:
            import channels
            idx = channels.selectedChannel()
            name = channels.getChannelName(idx)
            return ("%d: %s" % (idx, name))[:16]
        except Exception:
            return ""

    def volume_line() -> str:
        try:
            import channels
            v = channels.getChannelVolume(channels.selectedChannel())
            return ("Vol %d%%" % int(v * 100))[:16]
        except Exception:
            return ""

    def pan_line() -> str:
        try:
            import channels
            p = channels.getChannelPan(channels.selectedChannel())
            return ("Pan %+d%%" % int(p * 100))[:16]
        except Exception:
            return ""

    def target_mix_line() -> str:
        try:
            import channels
            t = channels.getTargetFxTrack(channels.selectedChannel())
            return ("Mix %d" % t if t > 0 else "Mix MASTER")[:16]
        except Exception:
            return ""

    def pattern_line() -> str:
        try:
            import patterns
            n = patterns.patternNumber()
            name = patterns.getPatternName(n)
            return ("%d: %s" % (n, name))[:16]
        except Exception:
            return ""

    def plugin_line() -> str:
        try:
            import ui
            return (ui.getFocusedPluginName() or "No plugin")[:16]
        except Exception:
            return ""

    def bank_line() -> str:
        try:
            enc = processor._controller.encoders()
            # Best-effort; real bank index may live on the auto-mapper
            return "Bank"
        except Exception:
            return "Bank"

    # ------------------------------------------------------------------
    # Windows sub-tree (absorbs old window-select / window-nav modal)
    # ------------------------------------------------------------------

    def make_window_node(label: str, window_id: int) -> MenuNode:
        def enter():
            for i, (name, wid) in enumerate(processor._window_targets):
                if wid == window_id:
                    processor._window_select_index = i
                    break
            processor._focus_window_target()

        def turn(delta: int):
            processor._navigate_window(window_id, delta)

        return MenuNode(
            name=label,
            on_enter=enter,
            on_turn=turn,
            line2_fn=lambda: "Turn to nav",
            safe_while_recording=True,
        )

    windows_children = [
        make_window_node(name, wid)
        for name, wid in processor._window_targets
    ]

    # ------------------------------------------------------------------
    # Channel sub-tree (absorbs old NavigationMode Channel/Volume/…)
    # Includes the subtle Channel Rack controls: vol, pan, target mix
    # ------------------------------------------------------------------

    channel_children = [
        MenuNode(
            name="Select",
            on_turn=processor.OnUpdateChannel,
            on_press=processor.OnChannelKnobPress,
            line2_fn=channel_line,
        ),
        MenuNode(
            name="Volume",
            on_turn=processor.OnUpdateVolume,
            on_press=processor.OnVolumeKnobPress,
            line2_fn=volume_line,
        ),
        MenuNode(
            name="Panning",
            on_turn=processor.OnUpdatePanning,
            on_press=processor.OnPanningKnobPress,
            line2_fn=pan_line,
        ),
        MenuNode(
            name="Target Mix",
            on_turn=processor.OnUpdateTargetMixerTrack,
            on_press=processor.OnMixerTrackKnobPress,
            line2_fn=target_mix_line,
        ),
        MenuNode(
            name="Plugin Preset",
            on_turn=processor.OnUpdatePlugin,
            on_press=processor.OnChannelKnobPress,
            line2_fn=plugin_line,
        ),
    ]

    try:
        import general
        script_version = general.getVersion()
    except Exception:
        script_version = 0
    if script_version >= 8:
        channel_children.insert(
            3,
            MenuNode(
                name="Pitch",
                on_turn=processor.OnUpdatePitch,
                on_press=processor.OnPitchKnobPress,
                line2_fn=lambda: "Pitch",
            ),
        )

    # ------------------------------------------------------------------
    # Pattern sub-tree
    # ------------------------------------------------------------------

    pattern_children = [
        MenuNode(
            name="Select",
            on_turn=processor.OnUpdatePattern,
            on_press=processor.OnPatternKnobPress,
            line2_fn=pattern_line,
        ),
    ]

    # ------------------------------------------------------------------
    # Plugin / Auto-mapper sub-tree
    # ------------------------------------------------------------------

    def cycle_bank(delta: int):
        try:
            # LIVE/BANK already cycles banks; expose a menu path too
            if delta > 0:
                processor.OnBankNextShortPress(None)
            elif delta < 0:
                processor.OnBankPrevShortPress(None)
        except Exception:
            pass

    def safe_rescan():
        from arturia_menu import latency_gate
        if not latency_gate.allow_discovery():
            processor._display_hint("Scan", "Blocked (rec)")
            return
        try:
            import time
            processor._controller.encoders().MaybeInterrogatePlugin(
                time.monotonic() * 1000
            )
            processor._display_hint("Scan", "Started")
        except Exception as exc:
            processor._display_hint("Scan", str(exc)[:16])

    plugin_children = [
        MenuNode(
            name="Bank",
            on_turn=cycle_bank,
            line2_fn=bank_line,
            safe_while_recording=True,
        ),
        MenuNode(
            name="Re-scan",
            on_enter=safe_rescan,
            line2_fn=lambda: "Press to scan",
            safe_while_recording=False,
        ),
    ]

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    return [
        MenuNode("Windows", children=windows_children),
        MenuNode("Channel", children=channel_children),
        MenuNode("Pattern", children=pattern_children),
        MenuNode("Plugin", children=plugin_children),
    ]

