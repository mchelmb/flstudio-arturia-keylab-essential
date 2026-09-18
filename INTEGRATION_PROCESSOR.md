# Processor Integration – Final Interaction Model

Copy these changes into `arturia_processor.py`. Menu + context knobs both work.

## Interaction (Essential)

| Control | Menu inactive | Menu active |
|---------|---------------|-------------|
| **Encoder click** | Open top-level menu | Enter / confirm |
| **Encoder turn** | Live nav / values | Move selection or change leaf value |
| **Cat/Char** | Existing short behaviour | **Back** one level / exit |
| **Left** | Focus-critical (Browser tabs, plugin tabs, channel jog) | Leave pure focus (recommended) |
| **Right** | Focus-critical forward | Enter (same as click) |

When **Channel Rack** is focused, top encoders 1–3 also control:
- Knob 1 → channel Volume  
- Knob 2 → channel Panning  
- Knob 3 → Target Mixer track  

(Menu path **Channel → Volume / Panning / Target Mix** remains available too.)

---

## 1. Imports

```python
from arturia_menu import MenuSystem, latency_gate
from arturia_menu_tree import build_menu_tree
```

## 2. Construct menu (inside `__init__`, after `_window_targets` and OnUpdate* methods exist)

```python
        self._menu = MenuSystem(
            self._controller.paged_display(),
            display_hint_fn=self._display_hint,
            gate=latency_gate,
        )
        self._menu.register_tree(build_menu_tree(self))
```

## 3. Encoder click = open / enter (no long-press required)

```python
    def OnNavigationKnobShortPress(self, event):
        debug.log('OnNavigationKnobShortPress', 'Dispatched', event=event)
        if self._menu.is_active():
            self._menu.press()
            return
        self._menu.enter()
        return
```

Leave `OnNavigationKnobLongPress` as a no-op for the menu (or repurpose later).

## 4. Cat/Char = Back

At the top of `OnCategoryShortPress`:

```python
    def OnCategoryShortPress(self, event):
        if self._menu.is_active():
            self._menu.back()
            return
        # … existing plugin-tags / browser escape logic …
```

## 5. Encoder turn – menu first

```python
    def OnNavigationKnobTurned(self, event):
        delta = self._get_knob_delta(event)
        debug.log('OnNavigationKnob', 'Delta = %d' % delta, event=event)
        if self._menu.turn(delta):
            return
        # ---- existing fallback ----
        if self._window_nav_turn(delta):
            return
        if not self._window_nav_mode and not self._window_select_mode:
            if self._focused_window_nav_turn(delta):
                return
        if self._button_mode == arturia_macros.SAVE_BUTTON:
            self._change_playlist_track(delta)
        elif self._button_mode or self._locked_mode:
            self._macros.on_macro_actions(
                self._button_mode | self._locked_mode, arturia_macros.NAV_WHEEL, delta)
            self._button_hold_action_committed = True
        else:
            self._navigation.UpdateValue(delta)
```

## 6. Left stays focus-critical

Do **not** route Left into the menu. Keep existing `_focused_window_nav_left` so Browser tabs and plugin internal pages keep working.

## 7. Right – enter when menu active

```python
    def OnNavigationRight(self, event):
        if self._is_pressed(event):
            if self._menu.right():
                return
            # … existing Right logic …
```

## 8. Record → latency gate

In `OnTransportsRecord` after the record toggle:

```python
            if not self._is_pad_recording:
                transport.record()
            try:
                self._menu.set_recording(transport.isRecording())
            except Exception:
                pass
```

And once per `OnIdle`:

```python
        try:
            self._menu.set_recording(transport.isRecording())
            latency_gate.set_playing_strict(
                transport.isPlaying() and getattr(config, 'STRICT_LATENCY_WHILE_PLAYING', False))
            self._menu.on_idle(now_ms)
        except Exception:
            pass
```

## 9. Files to copy

| File | Action |
|------|--------|
| `arturia_menu.py` | Add (new) |
| `arturia_menu_tree.py` | Add (new) |
| `arturia_auto_mapper.py` | Replace (gated Idle + export) |
| `arturia_encoders.py` | Replace (Channel Rack context knobs) |
| `config.py` | Merge the two new flags |
| Processor changes above | Edit by hand |

## Quick test checklist

1. Reload script.
2. Click central encoder → top-level menu on LCD.
3. Turn → highlight moves; click → enters Channel / Windows / ….
4. Channel → Volume → turn changes channel volume, LCD updates.
5. Cat/Char → backs out; at top → exits menu.
6. Focus Channel Rack → turn top knobs 1/2/3 → vol / pan / target mix (no menu needed).
7. Arm record → heavy VST scan stops; notes/transport stay responsive.

Both paths are live. Copy, test, then delete old NavigationMode / window-modal code when happy.
