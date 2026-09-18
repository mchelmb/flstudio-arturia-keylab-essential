# User-settable settings to alter behavior of keyboard
import device

TRUE_IF_ESSENTIAL_KEYBOARD = 'mkII' not in device.getName()

# Set to True to allow drum pads to light up as a metronome indicator.
ENABLE_PAD_METRONOME_LIGHTS = True

# Set to True to allow transport lights to light up as a metronome indicator.
ENABLE_TRANSPORTS_METRONOME_LIGHTS = True

# Set to True to only allow visual metronome lights when audible metronome in FL Studio is enabled.
# Set to False to always enable visual metronome lights when playing/recording.
METRONOME_LIGHTS_ONLY_WHEN_METRONOME_ENABLED = False

# Set to True to enable piano roll to be focused on during playback/record. This is needed for punch buttons to work.
ENABLE_PIANO_ROLL_FOCUS_DURING_RECORD_AND_PLAYBACK = True

# Configure the port number that midi notes are forwarded to for plugins.
PLUGIN_FORWARDING_MIDI_IN_PORT = 10

# Set to True to put display text hints in all caps.
HINT_DISPLAY_ALL_CAPS = False

# Set to True to enable color bank lights. On Essential keyboards, the pad colors are set to the active channel color.
ENABLE_COLORIZE_BANK_LIGHTS = True

# Set True to also colorize the pad lights according to the active color channel (only on MKII. For Essential keyboard,
# the ENABLE_COLORIZE_BANK_LIGHTS sets this option).
ENABLE_MK2_COLORIZE_PAD_LIGHTS = True

# If True, then sliders initially control plugin. If False, sliders initially control mixer tracks.
SLIDERS_FIRST_CONTROL_PLUGINS = False

# If True, the sliders are initially ignored until they cross the initial value in the mixer. For example, if mixer
# for track 1 is set to 100% and mixer is at 50%, then mixer sliders won't do anything until they cross or match the
# value of the mixer.
ENABLE_MIXER_SLIDERS_PICKUP_MODE = True

# If True, changes to the controls also update the FL hint panel when appropriate Useful if you can't visually see the
# display on keyboard and need feedback from FL Studio (i.e. plugin active but UI hidden).
ENABLE_CONTROLS_FL_HINTS = True

# If True, then enable turning nav wheel past last pattern to create a new pattern. (Default True for Essential
# keyboards)
ENABLE_PATTERN_NAV_WHEEL_CREATE_NEW_PATTERN = TRUE_IF_ESSENTIAL_KEYBOARD

# Maximum mixer volume. Set to 120 if you like to overdrive the volume.
# WARNING: You can overdrive this to a larger value, but you may blow out your speaker/headphones if you do not have
# a volume limiter (like some studio monitors). So, do be careful.  I do not recommend values over 120, though it is
# certainly possible.
MAX_MIXER_VOLUME = 100

# Visibility toggle functionality has been removed from the script.

# If True, the pads will assign to the channel rack tracks as follows:
#
#  1   2   3   4
#  5   6   7   8
#  9  10  11  12
# 13  14  15  16
#
# This is useful if you prefer an MPC style assignment where the channel rack tracks contain sample chops.
ENABLE_MPC_STYLE_PADS = False

# If enabled, this will switch the behavior of long pressing on the pads to sustaining the note being played. This
# is particularly useful for MPC style pads that play loops.
# Re-mapping a pad note will still work by holding the record button and pressing the pad button.
ENABLE_LONG_PRESS_SUSTAIN_ON_PADS = False

# If True, this will treat the pad LED layout the same as 88-key which is inverted.
INVERT_LED_LAYOUT = False

DEBUG_DUMP_UNMAPPED_PLUGIN_PARAMS = True

# When True and the Channel Rack window is focused, the first three top-row
# encoders control the selected channel's Volume, Panning and Target Mixer
# track (the "subtle" Channel Rack strip controls). Remaining knobs keep
# their normal plugin / mixer behaviour. This works alongside the menu
# (Channel > Volume / Panning / Target Mix) so both deliberate and live
# control are available.
ENABLE_CHANNEL_RACK_CONTEXT_KNOBS = True

# When True, treat any playback as critical for the latency gate (in addition
# to recording). Default False so normal play stays fully featured.
STRICT_LATENCY_WHILE_PLAYING = False

# --------------------[ Automatic VST parameter mapper ]---------------------------------------
# Controls how the 4 generic "Param" knobs (and, in DYNAMIC_RANKED mode, every auto-mapped knob/
# slider) get filled in for a plugin with no hand-curated entry in arturia_native_plugins.py.
#
# 'FIXED_SLOTS' (default): knobs 1-4 and both slider ADSR quads keep their fixed hardware-label
#   identity (Cutoff/Resonance/LFO Rate/LFO Amt, Attack/Decay/Sustain/Release x2) exactly as
#   printed on the keyboard. Only the 4 generic Param knobs are filled from the gated/ranked
#   candidate pool.
# 'DYNAMIC_RANKED': fixed identity is dropped entirely. All auto-mapped knobs/sliders are filled
#   in ranked order from the same gated/ranked candidate pool - a knob printed "Resonance" may
#   show something else if nothing resonance-like is highly ranked for this patch.
#
# This is only the STARTING default for a new project - the mode can be toggled live with a long
# press of the CATEGORY button, and whatever you toggle it to is persisted per-project (see
# arturia_auto_mapper.py / arturia_savedata.py), so different projects can settle on different
# modes as you curate sounds per VST over time.
AUTO_MAP_MODE = 'FIXED_SLOTS'

# How long (seconds) a newly selected channel/plugin must stay unchanged before the auto-mapper
# analyzes it and commits a new mapping. Prevents remapping mid-scroll while browsing presets.
AUTO_MAP_SETTLE_TIME = 2.5

# If True, logs the auto-mapper's candidate filtering and ranking process via debug.log (requires
# debug.DEBUG = True in debug.py to actually print).
AUTO_MAP_DEBUG = True

# If True (default), every completed parameter scan is dumped to vst_param_scans/<plugin>.json -
# a passive way to build up a personal library of what each plugin exposes, useful as raw material
# for curating vst_maps/vst_default_maps.json. Set to False to disable.
AUTO_MAP_EXPORT_SCANS = True

# Plugins excluded from auto-mapping entirely - either they already have hand-curated mappings in
# arturia_native_plugins.py, or they're simple/stock enough that generic auto-mapping doesn't add
# value. Add more names here as needed.
AUTO_MAP_EXCLUDED_PLUGINS = frozenset({
    'FLEX', 'FPC', 'FL Keys', 'Sytrus', 'GMS', 'Harmless', 'Harmor',
    'Morphine', '3x Osc', 'Fruity DX10', 'BASSDRUM', 'Fruit kick',
    'MiniSynth', 'PoiZone', 'Sakura',
})

