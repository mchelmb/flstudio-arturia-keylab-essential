import _random
import time

import arrangement
import channels

import arturia_leds
import arturia_macros
import arturia_midi
import arturia_playlist
import config
import debug
import general
import midi
import mixer
import patterns
import playlist
import transport
import ui
import utils

from arturia_display import ArturiaDisplay
from arturia_midi import MidiEventDispatcher
from arturia_navigation import NavigationMode
from arturia_leds import ArturiaLights
from macro_actions import Actions
import arturia_auto_mapper

SCRIPT_VERSION = general.getVersion()

# Long-press the main navigation encoder to enter window selection.
WINDOW_SELECT_LONG_PRESS_MS = 500

# --------------------[ GUI-coherence watchdog settings ]------------------------------------------
# FL Studio's scripting engine is single-threaded/cooperative: OnIdle only fires when FL's main
# thread isn't blocked (e.g. by a VST caching samples, or a heavy GUI repaint). There is no direct
# "is FL frozen" query, so we infer it from how late OnIdle calls arrive relative to each other.
#
# If the gap between two OnIdle calls is far larger than normal, FL was almost certainly stalled in
# between, and any state we cached before the gap (focused window, in-flight window-select/nav mode,
# pending long-press timers) must be treated as stale rather than trusted, since backlogged MIDI
# events and scheduled tasks can all surface at once the moment the stall clears.
STALL_THRESHOLD_MS = 250
# Safety timeout: if the window-select/window-nav modal is left open this long with no completing
# action (e.g. a release event was lost during a stall), auto-return to a normal state.
WINDOW_MODE_TIMEOUT_MS = 15000
# How often (at most) to refresh the cached "what window is focused" state via ui.getFocused().
# Polling this on an idle interval instead of on every single button/knob event both cuts down on
# work done in the hot path and gives one canonical place where our view of focus gets refreshed.
FOCUS_POLL_INTERVAL_MS = 150

# Keystroke sent to a focused plugin's own internal browser (e.g. FLEX's tag/category filter) when
# the CATEGORY button is pressed. FL exposes no scripting call for this - it only exists inside the
# plugin's own custom-drawn GUI - so this is emulated as a real keystroke via pykeys, same as the
# pack/preset navigation. FLEX's Tags panel is reached by pressing Right from the sample/preset list,
# so CATEGORY maps to Right arrow to match that UX.
PLUGIN_CATEGORY_KEY = 'right'

# Deliberately longer than the usual 450ms long-press threshold - toggling the auto-mapper mode
# changes a setting, not a navigation action, so it shouldn't be easy to trigger by accident.
AUTO_MAPPER_MODE_TOGGLE_LONG_PRESS_MS = 2000

if SCRIPT_VERSION >= 8:
    import plugins

# Event code indicating stop event
SS_STOP = 0
# Event code indicating start start event
SS_START = 2


class ArturiaMidiProcessor:
    @staticmethod
    def _is_pressed(event):
        return event.controlVal != 0

    def __init__(self, controller):
        def by_midi_id(event): return event.midiId
        def by_control_num(event): return event.controlNum
        def ignore_release(event): return self._is_pressed(event)

        self._controller = controller
        self._button_hold_action_committed = False
        self._button_mode = 0
        # Contextual window navigation state.  This is deliberately separate from
        # the existing macro/navigation modes so normal live-play behaviour is unchanged.
        self._window_select_mode = False
        self._window_nav_mode = False
        self._window_select_index = 0
        self._window_nav_target = None
        # Wall-clock (monotonic) timestamp of when we entered window-select/window-nav mode, used
        # to detect a stuck modal (e.g. a release event lost during a GUI stall) and auto-recover.
        self._window_mode_entered_ms = 0
        self._locked_mode = 0
        self._random = _random.Random()
        self._mixer_plugins_visible = False
        self._mixer_plugins_last_track = 0

        # --------------------[ GUI-coherence watchdog state ]--------------------------------------
        # Cached focused-window value. Refreshed on an OnIdle interval (see _poll_focused_window)
        # rather than re-queried live on every button/knob event.
        self._focused_window = None
        self._last_focus_poll_ms = 0
        # Timestamp of the previous OnIdle call, used to detect abnormally large gaps (a proxy for
        # "FL Studio's main thread was just blocked").
        self._last_idle_ms = time.monotonic() * 1000

        self._midi_id_dispatcher = (
            MidiEventDispatcher(by_midi_id)
            .SetHandler(144, self.OnCommandEvent)
            .SetHandler(176, self.OnKnobEvent)
            .SetHandler(224, self.OnSliderEvent))   # Sliders 1-9

        self._midi_command_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .SetHandler(91, self.OnTransportsBack)
            .SetHandler(92, self.OnTransportsForward)
            .SetHandler(93, self.OnTransportsStop)
            .SetHandler(94, self.OnTransportsPausePlay)
            .SetHandler(95, self.OnTransportsRecord)
            .SetHandler(86, self.OnTransportsLoop)

            .SetHandler(80, self.OnGlobalSave)
            .SetHandler(87, self.OnGlobalIn, ignore_release)
            .SetHandler(88, self.OnGlobalOut, ignore_release)
            .SetHandler(89, self.OnGlobalMetro, ignore_release)
            .SetHandler(81, self.OnGlobalUndo)

            .SetHandlerForKeys(range(8, 16), self.OnTrackSolo, ignore_release)
            .SetHandlerForKeys(range(16, 24), self.OnTrackMute, ignore_release)
            .SetHandlerForKeys(range(0, 8), self.OnTrackRecord)

            .SetHandler(74, self.OnTrackRead, ignore_release)
            .SetHandler(75, self.OnTrackWrite, ignore_release)

            .SetHandler(98, self.OnNavigationLeft)
            .SetHandler(99, self.OnNavigationRight)
            .SetHandler(101, self.OnCategory)
            .SetHandler(100, self.OnPreset)
            .SetHandler(84, self.OnNavigationKnobLongPressOrShort)

            .SetHandler(49, self.OnBankNext)
            .SetHandler(48, self.OnBankPrev)
            .SetHandler(47, self.OnLivePart1, ignore_release)
            .SetHandler(46, self.OnLivePart2, ignore_release)

            .SetHandlerForKeys(range(24, 32), self.OnBankSelect, ignore_release)
            .SetHandlerForKeys(range(104, 112), self.OnStartOrEndSliderEvent)
        )
        # Targets for the long-press window selector.  FL Studio's window IDs let us
        # focus the actual FL window rather than emulating mouse/keyboard shortcuts.
        self._window_targets = (
            ('Browser', midi.widBrowser),
            ('Plugin', midi.widPlugin),
            ('Mixer', midi.widMixer),
            ('Channel Rack', midi.widChannelRack),
            ('Playlist', midi.widPlaylist),
            ('Piano Roll', midi.widPianoRoll),
        )

        self._knob_dispatcher = (
            MidiEventDispatcher(by_control_num)
            .SetHandlerForKeys(range(16, 25), self.OnPanKnobTurned)
            .SetHandler(60, self.OnNavigationKnobTurned)
        )

        def get_volume_line(): return '    [%d%%]' % int(channels.getChannelVolume(channels.selectedChannel()) * 100)
        def get_panning_line(): return '    [%d%%]' % int(channels.getChannelPan(channels.selectedChannel()) * 100)
        def get_pitch_line(): return '    [%d%%]' % int (channels.getChannelPitch(channels.selectedChannel()) * 100)
        def get_pattern_line(): return arturia_playlist.get_playlist_track_name(patterns.patternNumber())
        def get_channel_line(): return '[%s]' % (channels.getChannelName(channels.selectedChannel()))
        def get_plugin_line(): return '[%s]' % channels.getChannelName(channels.selectedChannel())

        def get_playlist_track():
            current_track = arturia_playlist.current_playlist_track()
            name = arturia_playlist.get_playlist_track_name(current_track)
            return '%d: [%s]' % (current_track, name)

        def get_target_mixer_track():
            track = channels.getTargetFxTrack(channels.selectedChannel())
            return '%d' % track if track > 0 else 'MASTER'

        self._navigation = (
            NavigationMode(self._controller.paged_display())
            .AddMode('Channel', self.OnUpdateChannel, self.OnChannelKnobPress, get_channel_line)
            .AddMode('Volume', self.OnUpdateVolume, self.OnVolumeKnobPress, get_volume_line)
            .AddMode('Panning', self.OnUpdatePanning, self.OnPanningKnobPress,  get_panning_line)
        )

        if SCRIPT_VERSION >= 8:
            self._navigation.AddMode('Pitch', self.OnUpdatePitch, self.OnPitchKnobPress, get_pitch_line)

        (self._navigation
            .AddMode('Auto Color', self.OnUpdateChannel, self.OnColorKnobPress, get_channel_line)
            .AddMode('Plugin Preset', self.OnUpdatePlugin, self.OnChannelKnobPress, get_plugin_line)
            .AddMode('Pattern', self.OnUpdatePattern, self.OnPatternKnobPress, get_pattern_line)
            .AddMode('Playlist Track', self.OnUpdatePlaylistTrack, self.OnTrackPlaylistKnobPress, get_playlist_track)
            .AddMode('Target Mix Track', self.OnUpdateTargetMixerTrack, self.OnMixerTrackKnobPress,
                     get_target_mixer_track)
         )
        self._update_focus_time_ms = 0
        self._debug_value = 0
        # Mapping of string -> entry corresponding to scheduled long press task
        self._long_press_tasks = {}
        # Indicates if punch button is pressed (needed for essential keyboards)
        self._punched = False
        # Indicates pad is recording
        self._is_pad_recording = False
        self._macros = arturia_macros.ArturiaMacroBank(display_fn=self._display_hint)

    def circular(self, low, high, x):
        if x > high:
            x = low + (x - high - 1)
        elif x < low:
            x = high - (low - x - 1)
        return x

    def clip(self, low, high, x):
        return max(low, min(high, x))

    def NotifyPadRecordingState(self, is_recording):
        self._is_pad_recording = is_recording

    def OnUpdateVolume(self, delta):
        channel = channels.selectedChannel()
        volume = self.clip(0., 1., channels.getChannelVolume(channels.selectedChannel()) + (delta / 100.0))
        channels.setChannelVolume(channel, volume)

    def OnUpdatePanning(self, delta):
        channel = channels.selectedChannel()
        pan = self.clip(-1., 1., channels.getChannelPan(channel) + (delta / 100.0))
        channels.setChannelPan(channel, pan)

    def OnUpdatePitch(self, delta):
        if SCRIPT_VERSION < 8:
            # This isn't supported in older versions
            return
        channel = channels.selectedChannel()
        pan = self.clip(-1., 1., channels.getChannelPitch(channel) + (delta / 100.0))
        channels.setChannelPitch(channel, pan)

    def OnUpdateTimeMarker(self, delta, power=0):
        num_beats = patterns.getPatternLength(patterns.patternNumber())
        step_size = 1.0 / float(num_beats)
        pos = transport.getSongPos()
        delta *= (2**power)
        transport.setSongPos(self.clip(0.0, 1.0, pos + step_size * delta))

    def OnUpdatePattern(self, delta):
        index = self.clip(1, patterns.patternCount(), patterns.patternNumber() + delta)
        if (config.ENABLE_PATTERN_NAV_WHEEL_CREATE_NEW_PATTERN and
                patterns.patternNumber() + delta > patterns.patternCount()):
            self._new_empty_pattern(linked=False)
        else:
            arturia_playlist.select_playlist_track_from_pattern(index)

    def OnUpdateChannel(self, delta):
        index = self.clip(0, channels.channelCount() - 1, channels.selectedChannel() + delta)
        self._select_one_channel(index)

    def OnVolumeKnobPress(self):
        selected = channels.selectedChannel()
        if selected < 0:
            return
        channels.setChannelVolume(selected, 0.78125)

    def OnPanningKnobPress(self):
        selected = channels.selectedChannel()
        if selected < 0:
            return
        channels.setChannelPan(selected, 0.0)

    def OnPitchKnobPress(self):
        selected = channels.selectedChannel()
        if selected < 0:
            return
        if SCRIPT_VERSION >= 8:
            channels.setChannelPitch(selected, 0)

    def OnColorKnobPress(self):
        selected = channels.selectedChannel()
        if selected < 0:
            return
        rgb = int(self._random.random() * 16777215.0)
        channels.setChannelColor(selected, rgb)
        self._controller.encoders().Refresh()

    def OnChannelKnobPress(self):
        selected = channels.selectedChannel()
        if selected < 0:
            return

        if SCRIPT_VERSION > 9:
            channels.showCSForm(selected, -1)
        elif SCRIPT_VERSION >= 8:
            if plugins.isValid(selected):
                # If valid plugin, then toggle
                channels.showEditor(selected)
            else:
                # For audio, no ability to close window settings
                channels.showCSForm(selected)
        else:
            # Older versions, don't bother with toggle since no support for determining whether plugin or audio
            channels.showCSForm(selected)

    def OnPatternKnobPress(self):
        self._show_and_focus(midi.widPianoRoll)

    def OnTrackPlaylistKnobPress(self):
        track_name = playlist.getTrackName(arturia_playlist.current_playlist_track())
        channel_name = channels.getChannelName(channels.selectedChannel())
        track_mode = track_name == channel_name and track_name.startswith('* ')
        if track_mode:
            self.OnChannelKnobPress()
        else:
            self._show_and_focus(midi.widPlaylist)

    def OnMixerTrackKnobPress(self):
        if not channels.getTargetFxTrack(channels.selectedChannel()):
            track = self._next_free_mixer_track()
            self.OnUpdateTargetMixerTrack(track)
        else:
            pass

    def OnUnassignedKnobPress(self):
        # TODO
        self._display_hint('Unassigned', 'Knob press')

    def _request_plugin_window_focus(self):
        current_time_ms = ArturiaDisplay.time_ms()
        # Require explicit window focus if last request to focus was more than a second ago.
        if current_time_ms > self._update_focus_time_ms + 1000:
            # This call is expensive so try to use sparingly.
            channels.focusEditor(channels.selectedChannel())
        self._update_focus_time_ms = current_time_ms

    def OnUpdatePlugin(self, delta):
        # Indicator to notify user that preset is in process of being set.
        self._request_plugin_window_focus()
        if SCRIPT_VERSION >= 10:
            idx = channels.selectedChannel()
            if delta > 0:
                plugins.nextPreset(idx)
            elif delta < 0:
                plugins.prevPreset(idx)
        else:
            if delta > 0:
                ui.next()
            elif delta < 0:
                ui.previous()

    def OnUpdateColorRed(self, delta):
        r, g, b = utils.ColorToRGB(channels.getChannelColor(channels.selectedChannel()))
        r = self.clip(0, 255, r + delta)
        channels.setChannelColor(channels.selectedChannel(), utils.RGBToColor(r, g, b))
        self._controller.encoders().Refresh()

    def OnUpdateColorGreen(self, delta):
        r, g, b = utils.ColorToRGB(channels.getChannelColor(channels.selectedChannel()))
        g = self.clip(0, 255, g + delta)
        channels.setChannelColor(channels.selectedChannel(), utils.RGBToColor(r, g, b))
        self._controller.encoders().Refresh()

    def OnUpdateColorBlue(self, delta):
        r, g, b = utils.ColorToRGB(channels.getChannelColor(channels.selectedChannel()))
        b = self.clip(0, 255, b + delta)
        channels.setChannelColor(channels.selectedChannel(), utils.RGBToColor(r, g, b))
        self._controller.encoders().Refresh()

    def _channel_with_route_to_mixer_track(self, track):
        max_channel = channels.channelCount()
        for i in range(max_channel):
            if channels.getTargetFxTrack(i) == track:
                return i
        return -1

    def OnUpdatePlaylistTrack(self, delta):
        track = max(1, min(playlist.trackCount(), arturia_playlist.current_playlist_track() + delta))
        arturia_playlist.set_playlist_track(track)

    def _recolor_mixer_track(self, index):
        if index != 0:
            for i in range(channels.channelCount()):
                if channels.getTargetFxTrack(i) == index:
                    mixer.setTrackColor(index, channels.getChannelColor(i))
                    return
        mixer.setTrackColor(index, -10261391)

    def OnUpdateTargetMixerTrack(self, delta):
        max_track_idx = mixer.trackCount() - 2   # One of the track is a control track
        prev_track = channels.getTargetFxTrack(channels.selectedChannel())
        target_track = self.circular(0, max_track_idx, prev_track + delta)
        # Remember to unset the name of the previous pointed to track.
        mixer.setTrackNumber(target_track, midi.curfxMinimalLatencyUpdate)
        mixer.linkTrackToChannel(midi.ROUTE_ToThis)
        channel_idx = self._channel_with_route_to_mixer_track(prev_track)
        if channel_idx < 0:
            mixer.setTrackName(prev_track, '')
        elif mixer.getTrackName(prev_track) == mixer.getTrackName(target_track):
            mixer.setTrackName(prev_track, arturia_playlist.strip_pattern_name(channels.getChannelName(channel_idx)))
        if target_track == 0:
            mixer.setTrackName(target_track, '')
        if target_track != 0:
            mixer.setTrackNumber(target_track, channels.getChannelColor(channels.selectedChannel()))
        self._recolor_mixer_track(prev_track)

    def ProcessEvent(self, event):
        return self._midi_id_dispatcher.Dispatch(event)

    def OnCommandEvent(self, event):
        self._midi_command_dispatcher.Dispatch(event)

    def OnKnobEvent(self, event):
        self._knob_dispatcher.Dispatch(event)

    def OnSliderEvent(self, event):
        slider_index = event.status - event.midiId
        slider_value = event.controlVal

        if SCRIPT_VERSION < 8:
            # Arturia keyboards on 20.7.2 seem to experience issues with sliders bouncing values between 126 and 127.
            if slider_value >= 126:
                slider_value = 127

        debug.log('OnSliderEvent', 'Slider %d = %d' % (slider_index, slider_value), event=event)
        self._controller.encoders().ProcessSliderInput(event, slider_index, slider_value)

    @staticmethod
    def _get_knob_delta(event):
        val = event.controlVal
        return val if val < 64 else 64 - val

    def _horizontal_scroll(self, delta, power=0):
        if ui.getFocused(midi.widPianoRoll):
            self.OnUpdateTimeMarker(delta, power=power)
        elif ui.getFocused(midi.widPlaylist):
            self.OnUpdateTimeMarker(delta, power=power)
        else:
            transport.globalTransport(midi.FPT_Jog, delta)

    def _show_window_target(self):
        if not self._window_targets:
            return
        name, window = self._window_targets[self._window_select_index]
        self._display_hint('WINDOW SELECT', name)

    def _enter_window_select(self):
        # Start on the currently focused target when possible.
        focused_index = 0
        for i, (_name, window) in enumerate(self._window_targets):
            try:
                if ui.getFocused(window):
                    focused_index = i
                    break
            except Exception:
                pass
        self._window_select_index = focused_index
        self._window_select_mode = True
        self._window_nav_mode = False
        self._window_nav_target = None
        self._window_mode_entered_ms = time.monotonic() * 1000
        self._button_hold_action_committed = True
        self._show_window_target()
        debug.log('WindowSelect', 'Entered window selection')

    def _focus_window_target(self):
        if not self._window_targets:
            return
        name, window = self._window_targets[self._window_select_index]
        try:
            ui.showWindow(window)
            ui.setFocused(window)
            if window == midi.widPlugin:
                channels.focusEditor(channels.selectedChannel())
            self._window_nav_target = window
            self._window_select_mode = False
            self._window_nav_mode = True
            self._window_mode_entered_ms = time.monotonic() * 1000
            # We just told FL what to focus - update the cache immediately rather than waiting up
            # to FOCUS_POLL_INTERVAL_MS for OnIdle to notice.
            self._focused_window = window
            self._button_hold_action_committed = True
            self._display_hint(name, 'NAVIGATION')
            debug.log('WindowSelect', 'Focused %s' % name)
        except Exception as exc:
            debug.log('WindowSelect', 'Unable to focus %s: %s' % (name, exc))

    def _get_focused_window(self):
        """Returns the cached focused-window value. See _poll_focused_window / OnIdle."""
        return self._focused_window

    def _poll_focused_window(self):
        """Actually queries FL for the focused window and refreshes the cache.

        This does the real ui.getFocused() work that used to run inline on every single
        button/knob event. It's now only called from OnIdle (throttled by FOCUS_POLL_INTERVAL_MS)
        or immediately after an action we know changes focus ourselves (optimistic update).
        """
        found = None
        for name, window in self._window_targets:
            try:
                if ui.getFocused(window):
                    found = window
                    break
            except Exception:
                pass
        self._focused_window = found
        return found

    def _exit_window_modes(self, reason):
        """Drops out of window-select/window-nav mode back to a normal state, if active."""
        if not (self._window_select_mode or self._window_nav_mode):
            return
        self._window_select_mode = False
        self._window_nav_mode = False
        self._window_nav_target = None
        self._display_hint('Window Nav', reason)
        debug.log('WindowSelect', reason)

    def _on_stall_recovered(self, gap_ms):
        """Called when OnIdle notices FL's main thread was likely blocked for a while.

        Anything cached before the gap (focused window, an open window-select/nav modal, held
        modifier state, pending long-press timers) may be stale - a backlog of buffered MIDI events
        and overdue scheduled tasks can all surface in the same instant the stall clears. Rather than
        trust it, drop back to a known-safe state and force a fresh read.
        """
        debug.log('Watchdog', 'OnIdle gap of %dms - resyncing state' % gap_ms)
        self._exit_window_modes('Resynced')
        self._button_mode = 0
        self._locked_mode = 0
        scheduler = self._controller.scheduler()
        for task in self._long_press_tasks.values():
            scheduler.CancelTask(task)
        self._long_press_tasks.clear()
        self._poll_focused_window()

    def OnIdle(self):
        """Hooked up to the midi script's OnIdle event (see device_arturia_keylab_mkii.py).

        This is the one place we get a (roughly) regular heartbeat from FL Studio, so it's used for
        four things: detecting stalls (see _on_stall_recovered), refreshing the focused-window cache
        on a throttled interval, timing out a stuck window-select/nav modal, and driving the
        auto-mapper's settle timer.

        IMPORTANT: the stall-gap check below only measures the time between the START of this tick
        and the START of the previous one. Any potentially-slow work THIS tick does (chiefly
        MaybeInterrogatePlugin's parameter scan on a settle-commit) must never be allowed to count
        towards the NEXT tick's gap - that would misattribute our own work as an external FL freeze
        and trigger a self-inflicted state reset (_on_stall_recovered) right when the user might be
        mid-interaction. So _last_idle_ms is re-stamped with a fresh timestamp AFTER any such work,
        not left at the value captured on entry.
        """
        now_ms = time.monotonic() * 1000
        gap = now_ms - self._last_idle_ms
        self._last_idle_ms = now_ms
        if gap > STALL_THRESHOLD_MS:
            self._on_stall_recovered(gap)
            return

        if now_ms - self._last_focus_poll_ms >= FOCUS_POLL_INTERVAL_MS:
            self._last_focus_poll_ms = now_ms
            self._poll_focused_window()
            # Skip while the Browser has focus - this is exactly the moment a new plugin might be
            # getting inserted, and background scanning work has no reason to run then anyway
            # (nothing plugin-related is being played with yet).
            if self._focused_window != midi.widBrowser:
                self._controller.encoders().MaybeInterrogatePlugin(now_ms)
            # Re-stamp after potentially-slow work - see docstring above.
            self._last_idle_ms = time.monotonic() * 1000

        if self._window_select_mode or self._window_nav_mode:
            if now_ms - self._window_mode_entered_ms > WINDOW_MODE_TIMEOUT_MS:
                self._exit_window_modes('Timed out')

    def _navigate_window(self, window, delta):
        if window == midi.widBrowser:
            direction = midi.FPT_Down if delta > 0 else midi.FPT_Up
            for _ in range(abs(delta)):
                ui.navigateBrowser(direction, 0)
        elif window in (midi.widMixer, midi.widChannelRack, midi.widPlaylist, midi.widPianoRoll):
            direction = ui.down if delta > 0 else ui.up
            for _ in range(abs(delta)):
                direction()
        elif window == midi.widPlugin:
            # FLEX-style plugin browsers (and similar) have their own internal preset list that
            # isn't exposed through a dedicated FL scripting call - the only way to drive it is to
            # emulate the real Up/Down keystrokes the plugin's own GUI listens for. Falls back to
            # FL's generic next/previous-preset call if pykeys/ctypes SendInput isn't available.
            key = 'down' if delta > 0 else 'up'
            fallback = ui.next if delta > 0 else ui.previous
            for _ in range(abs(delta)):
                if not Actions.fl_windows_shortcut(key):
                    fallback()
        else:
            return False
        self._button_hold_action_committed = True
        return True

    def _window_nav_turn(self, delta):
        if self._window_select_mode:
            count = len(self._window_targets)
            self._window_select_index = (self._window_select_index + delta) % count
            self._show_window_target()
            self._button_hold_action_committed = True
            return True

        if not self._window_nav_mode or self._window_nav_target is None:
            return False

        return self._navigate_window(self._window_nav_target, delta)

    def _focused_window_nav_turn(self, delta):
        window = self._get_focused_window()
        if window is None:
            return False
        return self._navigate_window(window, delta)

    def _focused_window_nav_left(self):
        window = self._get_focused_window()
        if window is None:
            debug.log('NavLeft', 'No focused window')
            return False
        debug.log('NavLeft', 'Focused window: %s' % str(window))
        if window == midi.widBrowser:
            Actions.escape(None)
            self._display_hint('Browser', 'Back / Escape')
        elif window in (midi.widMixer, midi.widChannelRack, midi.widPlaylist, midi.widPianoRoll):
            transport.globalTransport(midi.FPT_Jog, -1)
            self._display_hint('Navigate', 'Left')
        else:
            debug.log('NavLeft', 'Unhandled window type')
            return False
        self._button_hold_action_committed = True
        return True

    def _focused_window_nav_right(self):
        window = self._get_focused_window()
        if window is None:
            debug.log('NavRight', 'No focused window')
            return False
        debug.log('NavRight', 'Focused window: %s' % str(window))
        if window == midi.widBrowser:
            ui.navigateBrowserTabs(midi.FPT_Right)
            self._display_hint('Browser Tab', 'Next')
        elif window in (midi.widMixer, midi.widChannelRack, midi.widPlaylist, midi.widPianoRoll):
            transport.globalTransport(midi.FPT_Jog, 1)
            self._display_hint('Navigate', 'Right')
        else:
            debug.log('NavRight', 'Unhandled window type')
            return False
        self._button_hold_action_committed = True
        return True

    def OnNavigationKnobTurned(self, event):
        delta = self._get_knob_delta(event)
        debug.log('OnNavigationKnob', 'Delta = %d' % delta, event=event)
        if self._window_nav_turn(delta):
            return
        if not self._window_nav_mode and not self._window_select_mode:
            if self._focused_window_nav_turn(delta):
                return
        if self._button_mode == arturia_macros.SAVE_BUTTON:
            self._change_playlist_track(delta)
        elif self._button_mode or self._locked_mode:
            self._macros.on_macro_actions(self._button_mode | self._locked_mode, arturia_macros.NAV_WHEEL, delta)
            self._button_hold_action_committed = True
        else:
            self._navigation.UpdateValue(delta)

    _KNOB_MAPPING = {
        0: midi.REC_Chan_Plugin_First + 18,
        1: midi.REC_Chan_Plugin_First + 20,
        2: midi.REC_Chan_Plugin_First + 19,
        3: midi.REC_Chan_Plugin_First + 5,
        4: midi.REC_Chan_Plugin_First + 6,
        5: midi.REC_Chan_Plugin_First + 7,
        6: midi.REC_Chan_Plugin_First + 8,
        7: midi.REC_Chan_Plugin_First + 9,
        8: midi.REC_Chan_Plugin_First + 0,
    }

    def OnPanKnobTurned(self, event):
        idx = event.controlNum - 16
        delta = self._get_knob_delta(event)
        self._button_hold_action_committed = True
        if self._button_mode or self._locked_mode:
            macro_id = idx + arturia_macros.ENCODER1
            self._macros.on_macro_actions(self._button_mode | self._locked_mode, macro_id, delta)
        elif self._button_mode == 0:
            self._controller.encoders().ProcessKnobInput(event, idx, delta)

    def OnTransportsBack(self, event):
        debug.log('OnTransportsBack', 'Dispatched', event=event)
        if self._is_pressed(event):
            transport.continuousMove(-1, SS_START)
            self._controller.paged_display().SetActivePage('Time Marker')
        else:
            transport.continuousMove(-1, SS_STOP)
            self._controller.paged_display().SetActivePage('main')

    def OnTransportsForward(self, event):
        debug.log('OnTransportsForward', 'Dispatched', event=event)
        if self._is_pressed(event):
            transport.continuousMove(1, SS_START)
            self._controller.paged_display().SetActivePage('Time Marker')
        else:
            transport.continuousMove(1, SS_STOP)
            self._controller.paged_display().SetActivePage('main')

    def OnTransportsStop(self, event):
        if self._is_pressed(event):
            self._button_mode |= arturia_macros.STOP_BUTTON
            self._button_hold_action_committed = False
            debug.log('OnTransportsStop [down]', 'Dispatched', event=event)
            data1 = arturia_midi.INTER_SCRIPT_DATA1_BTN_DOWN_CMD
        else:
            debug.log('OnTransportsStop [up]', 'Dispatched', event=event)
            data1 = arturia_midi.INTER_SCRIPT_DATA1_BTN_UP_CMD
            self._button_mode &= ~arturia_macros.STOP_BUTTON
            if not self._button_hold_action_committed:
                self._controller.metronome().Reset()
                transport.stop()

        arturia_midi.dispatch_message_to_other_scripts(
            arturia_midi.INTER_SCRIPT_STATUS_BYTE,
            data1,
            event.controlNum)

    def _show_and_focus(self, window):
        ui.showWindow(window)
        ui.setFocused(window)

    def OnTransportsPausePlay(self, event):
        debug.log('OnTransportsPausePlay', 'Dispatched', event=event)
        if self._is_pressed(event):
            self._button_mode |= arturia_macros.PLAY_BUTTON
            self._button_hold_action_committed = False
        else:
            self._button_mode &= ~arturia_macros.PLAY_BUTTON
            if self._button_hold_action_committed:
                # Update event happened so do not process button release.
                return
            song_mode = transport.getLoopMode() == 1
            if config.ENABLE_PIANO_ROLL_FOCUS_DURING_RECORD_AND_PLAYBACK:
                if song_mode:
                    self._show_and_focus(midi.widPlaylist)
                else:
                    self._show_and_focus(midi.widPianoRoll)
            transport.globalTransport(midi.FPT_Play, midi.FPT_Play, event.pmeFlags)

    def OnTransportsRecord(self, event):
        if self._is_pressed(event):
            debug.log('OnTransportsRecord [down]', 'Dispatched', event=event)
            self._button_mode |= arturia_macros.REC_BUTTON
            self._button_hold_action_committed = False
            arturia_midi.dispatch_message_to_other_scripts(
                arturia_midi.INTER_SCRIPT_STATUS_BYTE,
                arturia_midi.INTER_SCRIPT_DATA1_BTN_DOWN_CMD,
                event.controlNum)
        else:
            # Release event
            self._button_mode &= ~arturia_macros.REC_BUTTON
            arturia_midi.dispatch_message_to_other_scripts(
                arturia_midi.INTER_SCRIPT_STATUS_BYTE,
                arturia_midi.INTER_SCRIPT_DATA1_BTN_UP_CMD,
                event.controlNum)
            if self._button_hold_action_committed:
                # Update event happened so do not process button release.
                return
            debug.log('OnTransportsRecord [up]', 'Dispatched', event=event)
            if not self._is_pad_recording:
                transport.record()

    def OnTransportsLoop(self, event):
        debug.log('OnTransportsLoop', 'Dispatched', event=event)
        if self._is_pressed(event):
            self._button_mode |= arturia_macros.LOOP_BUTTON
            self._button_hold_action_committed = False
        else:
            self._button_mode &= ~arturia_macros.LOOP_BUTTON
            if self._button_hold_action_committed:
                return
            transport.globalTransport(midi.FPT_LoopRecord, midi.FPT_LoopRecord, event.pmeFlags)

    def OnGlobalSave(self, event):
        debug.log('OnGlobalSave', 'Dispatched', event=event)
        if self._is_pressed(event):
            self._button_mode |= arturia_macros.SAVE_BUTTON
            self._button_hold_action_committed = False
        else:
            self._button_mode &= ~arturia_macros.SAVE_BUTTON
            if not self._button_hold_action_committed:
                transport.setLoopMode()

    def OnGlobalIn(self, event):
        if arturia_leds.ESSENTIAL_KEYBOARD:
            if self._punched:
                # Dispatch to punchOut for essential keyboards since essential only has one punch button.
                self.OnGlobalOut(event)
                return
        self._punched = True
        debug.log('OnGlobalIn', 'Dispatched', event=event)
        transport.globalTransport(midi.FPT_PunchIn, midi.FPT_PunchIn, event.pmeFlags)
        self._controller.lights().SetLights({ArturiaLights.ID_GLOBAL_IN: ArturiaLights.LED_ON})

    def OnGlobalOut(self, event):
        debug.log('OnGlobalOut', 'Dispatched', event=event)
        self._punched = False
        transport.globalTransport(midi.FPT_PunchOut, midi.FPT_PunchOut, event.pmeFlags)
        Actions.fl_windows_shortcut("right", ctrl=1)
        Actions.fl_windows_shortcut("left", ctrl=1)

        if arrangement.selectionStart() < 0:
            self._controller.lights().SetLights({ArturiaLights.ID_GLOBAL_IN: ArturiaLights.LED_OFF})

    def OnGlobalMetro(self, event):
        debug.log('OnGlobalMetro', 'Dispatched', event=event)
        transport.globalTransport(midi.FPT_Metronome, midi.FPT_Metronome, event.pmeFlags)

    def OnGlobalUndo(self, event):
        debug.log('OnGlobalUndo', 'Dispatched', event=event)
        self._detect_long_press(event, self.OnGlobalUndoShortPress, self.OnGlobalUndoLongPress)

    def OnGlobalUndoShortPress(self, event):
        debug.log('OnGlobalUndo (short press)', 'Dispatched', event=event)
        transport.globalTransport(midi.FPT_Undo, midi.FPT_Undo, event.pmeFlags)

    def OnGlobalUndoLongPress(self, event):
        debug.log('OnGlobalUndo (long press)', 'Dispatched', event=event)
        # Clear current pattern
        self._show_and_focus(midi.widChannelRack)
        ui.cut()
        self._display_hint('CLEARED ACTIVE', 'CHANNEL PATTERN')

    def OnTrackSolo(self, event):
        debug.log('OnTrackSolo', 'Dispatched', event=event)
        playlist_mode = self._navigation.GetMode() == 'Playlist Track'
        if self._button_mode == arturia_macros.SAVE_BUTTON or playlist_mode:
            current_track = arturia_playlist.current_playlist_track()
            playlist.soloTrack(current_track)
            status = playlist.isTrackSolo(current_track)
            self._display_playlist_track_op_hint("Solo Playlist: %d" % status)
            self._button_hold_action_committed = True
        else:
            channels.soloChannel(channels.selectedChannel())

    def OnTrackMute(self, event):
        debug.log('OnTrackMute', 'Dispatched', event=event)
        playlist_mode = self._navigation.GetMode() == 'Playlist Track'
        if self._button_mode == arturia_macros.SAVE_BUTTON or playlist_mode:
            current_track = arturia_playlist.current_playlist_track()
            playlist.muteTrack(current_track)
            status = playlist.isTrackMuted(current_track)
            self._display_playlist_track_op_hint("Mute Playlist: %d" % status)
            self._button_hold_action_committed = True
        else:
            channels.muteChannel(channels.selectedChannel())

    def _detect_long_press(self, event, short_fn, long_fn, duration_ms=450):
        control_id = event.controlNum
        if self._is_pressed(event):
            task = self._controller.scheduler().ScheduleTask(lambda: long_fn(event), delay=duration_ms)
            self._long_press_tasks[control_id] = task
        else:
            # Release event. Attempt to cancel the scheduled long press task.
            if control_id in self._long_press_tasks and self._controller.scheduler().CancelTask(
                    self._long_press_tasks[control_id]):
                # Dispatch short function press if successfully cancelled the long press.
                short_fn(event)

    def OnTrackRecord(self, event):
        debug.log('OnTrackRecord', 'Dispatched', event=event)
        self._detect_long_press(event, self.OnTrackRecordShortPress, self.OnTrackRecordLongPress)

    def _new_empty_pattern(self, linked=True):
        pattern_id = patterns.patternCount() + 1
        if linked:
            pattern_name = arturia_playlist.next_pattern_name()
            color = channels.getChannelColor(channels.selectedChannel())
            patterns.setPatternName(pattern_id, pattern_name)
            patterns.setPatternColor(pattern_id, color)
        patterns.jumpToPattern(pattern_id)
        patterns.selectPattern(pattern_id, 1)
        return pattern_id

    def _new_pattern_from_selected(self):
        self._show_and_focus(midi.widPianoRoll)
        ui.copy()
        self._new_empty_pattern()
        ui.paste()
        # Hack to fix the pattern shift by moving it to far left most.
        transport.globalTransport(midi.FPT_StripJog, -midi.FromMIDI_Max)
        # Deselect region once we've copied it out.
        transport.globalTransport(midi.FPT_PunchOut, midi.FPT_PunchOut)

    def _clone_active_pattern(self):
        active_channel = channels.selectedChannel()
        self._show_and_focus(midi.widChannelRack)
        channels.selectAll()
        ui.copy()
        self._new_empty_pattern()
        ui.paste()
        self._select_one_channel(active_channel)

    def _next_free_mixer_track(self):
        last_track = 0
        for i in range(channels.channelCount()):
            if i == channels.selectedChannel():
                # Skip the assignment for the channel we are assigning.
                continue
            last_track = max(last_track, channels.getTargetFxTrack(i))
        return last_track + 1

    def OnTrackRecordShortPress(self, event):
        debug.log('OnTrackRecord Short', 'Dispatched', event=event)
        # Piano roll needs to be in focus to determine if a new pattern is needed
        piano_roll_visible = ui.getVisible(midi.widPianoRoll)
        self._show_and_focus(midi.widPianoRoll)
        if arrangement.selectionEnd() > arrangement.selectionStart():
            self._new_pattern_from_selected()
        else:
            self._new_empty_pattern()
        if not piano_roll_visible:
            ui.hideWindow(midi.widPianoRoll)

    def OnTrackRecordLongPress(self, event):
        debug.log('OnTrackRecord Long', 'Dispatched', event=event)
        self._clone_active_pattern()

    def _is_pattern_mode(self):
        return transport.getLoopMode() == 0

    def _display_playlist_track_hint(self):
        self._display_playlist_track_op_hint('Playlist Track')

    def _display_playlist_track_op_hint(self, title):
        track = arturia_playlist.current_playlist_track()
        name = arturia_playlist.get_playlist_track_name(track)
        self._display_hint(title, '%d: %s' % (track, name))

    def _change_playlist_track(self, delta):
        # Adjust track number.
        next = arturia_playlist.current_playlist_track() + delta
        if 0 < next <= playlist.trackCount():
            arturia_playlist.set_playlist_track(next)
        self._display_playlist_track_hint()
        self._button_hold_action_committed = True

    def OnTrackRead(self, event):
        debug.log('OnTrackRead', 'Dispatched', event=event)
        # Move to previous pattern (move up pattern list)
        if self._button_mode == arturia_macros.SAVE_BUTTON:
            # Adjust track number.
            self._change_playlist_track(-1)
        else:
            prev = patterns.patternNumber() - 1
            if prev <= 0:
                return
            arturia_playlist.select_playlist_track_from_pattern(prev)

    def OnTrackWrite(self, event):
        debug.log('OnTrackWrite', 'Dispatched', event=event)
        # Move to next pattern (move down pattern list)
        if self._button_mode == arturia_macros.SAVE_BUTTON:
            # Adjust track number.
            self._change_playlist_track(1)
        else:
            next = patterns.patternNumber() + 1
            if next > patterns.patternCount():
                return
            arturia_playlist.select_playlist_track_from_pattern(next)

    def OnNavigationLeft(self, event):
        if self._is_pressed(event):
            if not self._window_nav_mode and not self._window_select_mode:
                if self._focused_window_nav_left():
                    return
            elif self._window_nav_mode and self._window_nav_target == midi.widPlugin:
                # In window nav mode for plugin: send left arrow (exit pack mode)
                if not Actions.fl_windows_shortcut('left'):
                    ui.previous()
                self._display_hint('Plugin Browser', 'Exit Pack Mode (Left)')
                self._button_hold_action_committed = True
                return
            if self._window_nav_mode and self._window_nav_target == midi.widBrowser:
                Actions.escape(None)
                self._display_hint('Browser', 'Back / Escape')
                self._button_hold_action_committed = True
                return
            if self._button_mode & arturia_macros.RIGHT_BUTTON:
                Actions.escape(None)
                self._button_hold_action_committed = True
                return

            self._button_mode |= arturia_macros.LEFT_BUTTON
            self._button_hold_action_committed = False
        else:
            self._button_mode &= ~arturia_macros.LEFT_BUTTON

    def OnNavigationRight(self, event):
        if self._is_pressed(event):
            if not self._window_nav_mode and not self._window_select_mode:
                if self._focused_window_nav_right():
                    return
            elif self._window_nav_mode and self._window_nav_target == midi.widPlugin:
                # In window nav mode for plugin: send right arrow (pack select/next)
                if not Actions.fl_windows_shortcut('right'):
                    ui.next()
                self._display_hint('Plugin Browser', 'Pack Select / Next (Right)')
                self._button_hold_action_committed = True
                return
            if self._window_nav_mode and self._window_nav_target == midi.widBrowser:
                ui.navigateBrowserTabs(midi.FPT_Right)
                self._display_hint('Browser Tab', 'Next')
                self._button_hold_action_committed = True
                return
            if self._button_mode & arturia_macros.LEFT_BUTTON:
                Actions.escape(None)
                self._button_hold_action_committed = True
                return

            self._button_mode |= arturia_macros.RIGHT_BUTTON
            self._button_hold_action_committed = False
        else:
            self._button_mode &= ~arturia_macros.RIGHT_BUTTON

    def OnCategory(self, event):
        """Arturia's dedicated CATEGORY button. Short press: existing plugin-browser behavior.
        Long press (2s, deliberately longer than the usual 450ms - this changes a setting, not a
        navigation action, so it shouldn't fire by accident): toggles the auto-mapper between
        FIXED_SLOTS and DYNAMIC_RANKED mode."""
        self._detect_long_press(event, self.OnCategoryShortPress, self.OnCategoryLongPress,
                                duration_ms=AUTO_MAPPER_MODE_TOGGLE_LONG_PRESS_MS)

    def OnCategoryShortPress(self, event):
        """Arturia's dedicated CATEGORY button (built for Analog Lab-style tag filtering).

        On a focused/targeted plugin window (e.g. FLEX), opens its internal Tags panel
        via an emulated Right keystroke - see PLUGIN_CATEGORY_KEY.
        """
        window = self._window_nav_target if self._window_nav_mode else self._get_focused_window()
        if window == midi.widPlugin:
            if not Actions.fl_windows_shortcut(PLUGIN_CATEGORY_KEY):
                # Fallback: FL's generic next-preset (same as Right arrow in FLEX)
                ui.next()
                debug.log('OnCategory', 'pykeys unavailable - used ui.next() fallback')
            self._display_hint('Plugin Browser', 'Tags (Right)')
        else:
            debug.log('OnCategory', 'Not plugin window: %s' % str(window))

    def OnCategoryLongPress(self, event):
        new_mode = arturia_auto_mapper.get_instance().ToggleMode()
        label = 'Fixed Slots' if new_mode == arturia_auto_mapper.MODE_FIXED_SLOTS else 'Dynamic Ranked'
        self._display_hint('Auto-Map Mode', label)
        debug.log('OnCategoryLongPress', 'Toggled auto-map mode to %s' % new_mode)

    def OnPreset(self, event):
        """Short press advances a preset; long press toggles the Encoder 8 volume override."""
        self._detect_long_press(event, self.OnPresetShortPress, self.OnPresetLongPress,
                                duration_ms=AUTO_MAPPER_MODE_TOGGLE_LONG_PRESS_MS)

    def OnPresetShortPress(self, event):
        window = self._window_nav_target if self._window_nav_mode else self._get_focused_window()
        if window == midi.widPlugin:
            ui.next()
            self._display_hint('Plugin Browser', 'Next Preset')

    def OnPresetLongPress(self, event):
        enabled = arturia_auto_mapper.get_instance().ToggleEncoder8VolumeOverride()
        self._display_hint('Encoder 8 Volume', 'Enabled' if enabled else 'Disabled')
        debug.log('OnPresetLongPress', 'Encoder 8 volume override %s' % ('enabled' if enabled else 'disabled'))

    def OnNavigationLeftShortPress(self, event):
        debug.log('OnNavigationLeftShortPress', 'Dispatched', event=event)
        if self._button_hold_action_committed:
            return
        self._navigation.PreviousMode()

    def OnNavigationRightShortPress(self, event):
        debug.log('OnNavigationRightShortPress', 'Dispatched', event=event)
        if self._button_hold_action_committed:
            return
        self._navigation.NextMode()

    def OnNavigationKnobLongPressOrShort(self, event):
        self._detect_long_press(
            event,
            self.OnNavigationKnobShortPress,
            self.OnNavigationKnobLongPress,
            duration_ms=WINDOW_SELECT_LONG_PRESS_MS)

    def OnNavigationKnobShortPress(self, event):
        debug.log('OnNavigationKnobShortPress', 'Dispatched', event=event)
        if self._window_select_mode:
            # A short press commits the highlighted window and immediately hands
            # the encoder over to contextual navigation for that window.
            self._focus_window_target()
            return
        if self._window_nav_mode:
            # A short press in contextual navigation acts as Enter/select.
            if self._window_nav_target == midi.widBrowser:
                try:
                    ui.selectBrowserMenuItem()
                except Exception:
                    Actions.enter(None)
            else:
                Actions.enter(None)
            self._button_hold_action_committed = True
            return

        # Same implicit-focus behavior Left/Right/turn already have (see
        # _focused_window_nav_left/right, _navigate_window) - no need to explicitly enter the
        # window-select modal every time just to add/remove a highlighted browser item. Only the
        # Browser gets this; other windows keep their existing default knob-press behavior below
        # (bring the focused plugin's editor to front / hide it) rather than being silently
        # reinterpreted as "Enter".
        if self._get_focused_window() == midi.widBrowser:
            try:
                ui.selectBrowserMenuItem()
            except Exception:
                Actions.enter(None)
            self._button_hold_action_committed = True
            return

        self.OnNavigationKnobPressed(event)

    def OnNavigationKnobLongPress(self, event):
        debug.log('OnNavigationKnobLongPress', 'Dispatched', event=event)
        self._enter_window_select()

    def OnNavigationKnobPressed(self, event):
        # Kept as the original normal short-press behaviour.  Long-press handling
        # is wrapped by _detect_long_press below.
        debug.log('OnNavigationKnobPressed', 'Dispatched', event=event)
        self._button_hold_action_committed = True
        was_locked = self._locked_mode
        if self._button_mode & arturia_macros.LOOP_BUTTON:
            self._locked_mode = arturia_macros.LOOP_BUTTON
            self._display_hint('Entering', 'Move Mode')
        elif self._button_mode & arturia_macros.REC_BUTTON:
            self._locked_mode = arturia_macros.REC_BUTTON
            self._display_hint('Entering', 'H. Scroll Mode')
        elif self._button_mode:
            self._locked_mode = self._button_mode
            self._display_hint('Locking', 'Modifier Button')
        else:
            self._locked_mode = 0
            if not was_locked:
                self._navigation.NotifyKnobPressed()
            else:
                self._display_hint('Exiting mode')

    def OnBankNext(self, event):
        self._detect_long_press(event, self.OnBankNextShortPress, self.OnBankNextLongPress)

    def OnBankNextShortPress(self, event):
        debug.log('OnBankNext (short)', 'Dispatched', event=event)
        self._controller.encoders().NextControlsPage()

    def OnBankNextLongPress(self, event):
        debug.log('OnBankNext (long)', 'Dispatched', event=event)
        self.OnLivePart1(event)

    def OnBankPrev(self, event):
        self._detect_long_press(event, self.OnBankPrevShortPress, self.OnBankPrevLongPress)

    def OnBankPrevShortPress(self, event):
        debug.log('OnBankPrev (short)', 'Dispatched', event=event)
        self._controller.encoders().PrevControlsPage()

    def OnBankPrevLongPress(self, event):
        debug.log('OnBankPrev (long)', 'Dispatched', event=event)
        self.OnLivePart2(event)

    def OnLivePart1(self, event):
        debug.log('OnLivePart1', 'Dispatched', event=event)
        self._controller.encoders().ToggleKnobMode()

    def OnLivePart2(self, event):
        debug.log('OnLivePart2', 'Dispatched', event=event)
        self._controller.encoders().ToggleCurrentMode()

    def OnBankSelect(self, event):
        bank_index = event.controlNum - 24
        debug.log('OnBankSelect', 'Selected bank index=%d' % bank_index, event=event)
        if self._button_mode or self._locked_mode:
            debug.log('OnBankSelect', 'Dispatching macro. Mod=%d, index=%d' % (self._button_mode, bank_index),
                      event=event)
            channel_index = self._controller.encoders().GetBankChannelIndex(bank_index)
            self._macros.on_macro_actions(self._button_mode | self._locked_mode, bank_index, channel_index)
            self._button_hold_action_committed = True
        else:
            self._controller.encoders().ProcessBankSelection(event, bank_index)

    def OnStartOrEndSliderEvent(self, event):
        debug.log('OnStartOrEndSliderEvent', 'Dispatched', event=event)
        self._controller.encoders().StartOrEndSliderInput()

    def _display_hint(self, line1=None, line2=None):
        if line1 is None:
            line1 = ' '
        if line2 is None:
            line2 = ' '
        self._controller.paged_display().SetPageLines('hint', line1=line1, line2=line2)
        self._controller.paged_display().SetActivePage('hint', expires=1500)

    def _select_one_channel(self, index):
        if SCRIPT_VERSION >= 8:
            channels.selectOneChannel(index)
        else:
            channels.deselectAll()
            channels.selectChannel(index, 1)
        if config.ENABLE_CONTROLS_FL_HINTS:
            ui.setHintMsg('[%d:%d] %s' % (channels.selectedChannel() + 1, patterns.patternNumber(),
                                          channels.getChannelName(channels.selectedChannel())))
