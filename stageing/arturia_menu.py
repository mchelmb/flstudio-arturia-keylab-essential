"""
Hierarchical menu system for the KeyLab Essential NAV script.

Design goals
------------
1. Single, familiar interaction language (central encoder + Left/Right).
2. Absorb the old NavigationMode list *and* the window-select/window-nav modal
   into one coherent tree so the user never has to switch mental models.
3. Keep the tree shallow (≤ 2 levels in normal use) so it stays intuitive.
4. Explicit latency gates: while recording (or when the user has enabled
   strict live mode) heavy background work is suppressed so the MIDI thread
   stays responsive for notes and transport.

The MenuSystem is deliberately pure Python state + callbacks.  It does not
import FL Studio modules itself; the processor injects the concrete actions
(channel select, window focus, auto-mapper bank change, etc.).  This keeps
the menu testable and makes latency policy a single place.

Public surface used by arturia_processor.py
------------------------------------------
    menu = MenuSystem(paged_display, display_hint_fn)
    menu.register_tree(tree)          # once at init
    menu.enter()                      # long-press encoder → top level
    menu.back()                       # Left button or long-press while inside
    menu.turn(delta)                  # central encoder
    menu.press()                      # central encoder click
    menu.right()                      # Right button (enter / next page)
    menu.is_active()                  # True while a menu page is showing
    menu.on_idle(now_ms)              # timeout + latency gate refresh
    menu.set_recording(is_recording)  # called from transport handlers
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Latency policy
# ---------------------------------------------------------------------------

class LatencyGate:
    """
    Single source of truth for "are we allowed to do expensive work right now?".

    Heavy work (VST parameter discovery, scan export, SaveData writes, long
    ranking passes) must consult this gate.  Navigation, transport, channel
    select and basic value changes stay unrestricted.
    """

    def __init__(self):
        self._recording = False
        self._playing_strict = False          # optional user preference
        self._force_light = False             # temporary override (e.g. after stall)

    def set_recording(self, value: bool) -> None:
        self._recording = bool(value)

    def set_playing_strict(self, value: bool) -> None:
        self._playing_strict = bool(value)

    def force_light_mode(self, value: bool = True) -> None:
        self._force_light = bool(value)

    @property
    def is_critical(self) -> bool:
        """True → suppress discovery, disk I/O, long scans."""
        return self._recording or self._playing_strict or self._force_light

    def allow_discovery(self) -> bool:
        return not self.is_critical

    def allow_disk_io(self) -> bool:
        return not self.is_critical

    def allow_background_rank(self) -> bool:
        return not self.is_critical


# Global gate instance – imported by auto_mapper, savedata, processor, etc.
latency_gate = LatencyGate()


# ---------------------------------------------------------------------------
# Menu node definition
# ---------------------------------------------------------------------------

class MenuNode:
    """
    One entry in the menu tree.

    name          – shown on the LCD (≤ 16 chars ideal)
    children      – list of MenuNode (None / empty → leaf)
    on_enter      – called when the user presses the encoder *on this node*
                    (or presses Right).  Typical uses: focus a window,
                    open a plugin editor, start a value-edit sub-mode.
    on_turn       – called with delta when the encoder is turned *while this
                    node is the selected leaf*.  Used for continuous values
                    (volume, pan, pattern select, bank change…).
    on_press      – optional explicit press handler (defaults to on_enter).
    line2_fn      – zero-arg callable that returns the second LCD line
                    (value, status, etc.).  Called every refresh.
    safe_while_recording – if False the node is hidden / skipped while the
                           latency gate is critical.
    """

    def __init__(
        self,
        name: str,
        children: Optional[Sequence["MenuNode"]] = None,
        on_enter: Optional[Callable[[], None]] = None,
        on_turn: Optional[Callable[[int], None]] = None,
        on_press: Optional[Callable[[], None]] = None,
        line2_fn: Optional[Callable[[], str]] = None,
        safe_while_recording: bool = True,
    ):
        self.name = name
        self.children = list(children) if children else []
        self.on_enter = on_enter
        self.on_turn = on_turn
        self.on_press = on_press or on_enter
        self.line2_fn = line2_fn or (lambda: "")
        self.safe_while_recording = safe_while_recording

    def is_leaf(self) -> bool:
        return not self.children

    def visible_children(self, gate: LatencyGate) -> List["MenuNode"]:
        if not gate.is_critical:
            return self.children
        return [c for c in self.children if c.safe_while_recording]


# ---------------------------------------------------------------------------
# Menu state (pure data)
# ---------------------------------------------------------------------------

class MenuState:
    """
    Immutable-ish snapshot of where the user currently is.

    path          – list of MenuNode from root to the *parent* of the current
                    selection (empty when at top level).
    index         – index into the visible children of path[-1] (or of root).
    active        – False means the menu is hidden and the controller is in
                    "live" mode (encoders control parameters directly).
    entered_ms    – monotonic timestamp when the menu was last entered /
                    navigated; used for auto-timeout.
    """

    def __init__(self):
        self.path: List[MenuNode] = []
        self.index: int = 0
        self.active: bool = False
        self.entered_ms: float = 0.0

    def reset(self) -> None:
        self.path.clear()
        self.index = 0
        self.active = False
        self.entered_ms = 0.0

    def depth(self) -> int:
        return len(self.path)

    def current_parent(self, root: MenuNode) -> MenuNode:
        return self.path[-1] if self.path else root

    def current_node(self, root: MenuNode, gate: LatencyGate) -> Optional[MenuNode]:
        parent = self.current_parent(root)
        visible = parent.visible_children(gate)
        if not visible:
            return None
        self.index = max(0, min(self.index, len(visible) - 1))
        return visible[self.index]


# ---------------------------------------------------------------------------
# MenuSystem – the public controller
# ---------------------------------------------------------------------------

# How long the menu stays open with no interaction before returning to live mode.
MENU_TIMEOUT_MS = 12000

# LCD page name used by ArturiaPagedDisplay
MENU_PAGE = "Menu"


class MenuSystem:
    def __init__(
        self,
        paged_display,
        display_hint_fn: Callable[[str, str], None],
        gate: LatencyGate = latency_gate,
        timeout_ms: int = MENU_TIMEOUT_MS,
    ):
        self._display = paged_display
        self._hint = display_hint_fn
        self._gate = gate
        self._timeout_ms = timeout_ms

        self._root = MenuNode("Root")          # children filled by register_tree
        self._state = MenuState()

        # Register a provider so the paged display can always ask us for the
        # current two lines.
        self._display.SetPageLinesProvider(
            MENU_PAGE,
            line1=self._line1,
            line2=self._line2,
        )

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def register_tree(self, top_level_nodes: Sequence[MenuNode]) -> None:
        """Call once at processor init with the full menu definition."""
        self._root.children = list(top_level_nodes)

    # ------------------------------------------------------------------
    # Public input handlers (called from arturia_processor)
    # ------------------------------------------------------------------

    def enter(self) -> None:
        """Show the top-level menu (long-press encoder, or dedicated Menu button)."""
        self._state.path.clear()
        self._state.index = 0
        self._state.active = True
        self._touch()
        self._refresh()

    def back(self) -> bool:
        """
        Go up one level.  If already at top level, exit the menu entirely.
        Returns True if the event was consumed.
        """
        if not self._state.active:
            return False
        if self._state.path:
            self._state.path.pop()
            self._state.index = 0
            self._touch()
            self._refresh()
            return True
        # Already at root → leave menu
        self.exit("Back")
        return True

    def turn(self, delta: int) -> bool:
        """
        Encoder turned.  Behaviour depends on depth and node type:
        - Inside a list → move selection
        - On a leaf that has on_turn → change value
        Returns True if consumed.
        """
        if not self._state.active:
            return False

        node = self._state.current_node(self._root, self._gate)
        if node is None:
            return True

        # If the selected node is a leaf *and* supplies an on_turn handler,
        # treat the turn as a value change.  Otherwise treat it as navigation.
        if node.is_leaf() and node.on_turn is not None:
            node.on_turn(delta)
        else:
            parent = self._state.current_parent(self._root)
            visible = parent.visible_children(self._gate)
            if not visible:
                return True
            self._state.index = (self._state.index + delta) % len(visible)

        self._touch()
        self._refresh()
        return True

    def press(self) -> bool:
        """Encoder click – enter the selected node or fire its action."""
        if not self._state.active:
            return False

        node = self._state.current_node(self._root, self._gate)
        if node is None:
            return True

        if not node.is_leaf():
            # Dive one level deeper
            self._state.path.append(node)
            self._state.index = 0
        else:
            # Leaf action
            if node.on_press:
                node.on_press()

        self._touch()
        self._refresh()
        return True

    def right(self) -> bool:
        """Right button – same as press (enter / confirm)."""
        return self.press()

    def left(self) -> bool:
        """Left button – same as back."""
        return self.back()

    def exit(self, reason: str = "Exit") -> None:
        """Leave the menu and return to live mode."""
        if not self._state.active:
            return
        self._state.reset()
        self._hint("Menu", reason)
        # Let the paged display fall back to its normal active page
        # (the processor will usually re-assert the previous page).

    def is_active(self) -> bool:
        return self._state.active

    # ------------------------------------------------------------------
    # Idle / timeout / latency
    # ------------------------------------------------------------------

    def on_idle(self, now_ms: float) -> None:
        """Called from processor.OnIdle.  Handles auto-timeout."""
        if not self._state.active:
            return
        if now_ms - self._state.entered_ms > self._timeout_ms:
            self.exit("Timed out")

    def set_recording(self, is_recording: bool) -> None:
        """Forward transport state to the latency gate."""
        self._gate.set_recording(is_recording)
        # If we just entered a critical state while deep in a non-safe branch,
        # snap back to a safe top-level view so the user isn't stuck.
        if self._gate.is_critical and self._state.active:
            node = self._state.current_node(self._root, self._gate)
            if node is None or not node.safe_while_recording:
                self._state.path.clear()
                self._state.index = 0
                self._refresh()

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _touch(self) -> None:
        self._state.entered_ms = time.monotonic() * 1000

    def _line1(self) -> str:
        if not self._state.active:
            return ""
        # Build a short breadcrumb: "Channel > Volume" or just "Windows"
        parts = [n.name for n in self._state.path]
        node = self._state.current_node(self._root, self._gate)
        if node:
            parts.append(node.name)
        crumb = " > ".join(parts) if parts else "Menu"
        return crumb[:16]

    def _line2(self) -> str:
        if not self._state.active:
            return ""
        node = self._state.current_node(self._root, self._gate)
        if node is None:
            return "(empty)"
        try:
            return (node.line2_fn() or "")[:16]
        except Exception:
            return ""

    def _refresh(self) -> None:
        if self._state.active:
            self._display.SetActivePage(MENU_PAGE, expires=None)
            # Force an immediate redraw
            try:
                self._display.Refresh()
            except Exception:
                pass

