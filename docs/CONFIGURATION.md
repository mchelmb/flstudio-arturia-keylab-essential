# Configuration

Runtime settings live in `config.py`. Changes affect the deployed script after the next script
reload unless the setting is described as project-persisted.

## Display and lights

- `HINT_DISPLAY_ALL_CAPS`: display LCD hints in uppercase.
- `ENABLE_CONTROLS_FL_HINTS`: also send control changes to FL Studio's hint panel.
- `ENABLE_PAD_METRONOME_LIGHTS`: use pad LEDs for metronome indication.
- `ENABLE_TRANSPORTS_METRONOME_LIGHTS`: use transport LEDs for metronome indication.
- `METRONOME_LIGHTS_ONLY_WHEN_METRONOME_ENABLED`: restrict visual metronome lights to audible
  metronome mode.
- `ENABLE_COLORIZE_BANK_LIGHTS`: colorize Essential bank/pad LEDs using channel colors.
- `ENABLE_MK2_COLORIZE_PAD_LIGHTS`: colorize MKII pad LEDs using channel colors.

## Navigation and controls

- `ENABLE_PIANO_ROLL_FOCUS_DURING_RECORD_AND_PLAYBACK`: focus the piano roll during the relevant
  transport actions.
- `ENABLE_PATTERN_NAV_WHEEL_CREATE_NEW_PATTERN`: allow the navigation wheel to create a pattern
  after the last existing pattern; defaults according to detected keyboard type.
- `ENABLE_CHANNEL_RACK_CONTEXT_KNOBS`: when the Channel Rack is focused, map the first three top
  encoders to channel volume, panning, and target mixer track.
- `SLIDERS_FIRST_CONTROL_PLUGINS`: start sliders in plugin mode instead of mixer mode.
- `ENABLE_MIXER_SLIDERS_PICKUP_MODE`: prevent mixer jumps until a slider crosses its current value.
- `MAX_MIXER_VOLUME`: mixer volume ceiling as a percentage. Values above 100 can overdrive levels.
- `PLUGIN_FORWARDING_MIDI_IN_PORT`: MIDI input port used for generic plugin CC forwarding.
- `ENABLE_MPC_STYLE_PADS`: assign pads in a 4x4 MPC-style channel layout.
- `ENABLE_LONG_PRESS_SUSTAIN_ON_PADS`: sustain pad notes after a long press.
- `INVERT_LED_LAYOUT`: invert the pad LED layout.

## Latency and diagnostics

- `STRICT_LATENCY_WHILE_PLAYING`: apply the recording latency gate during playback as well.
- `DEBUG_DUMP_UNMAPPED_PLUGIN_PARAMS`: dump unmapped plugin parameters when debugging.
- `AUTO_MAP_DEBUG`: log auto-mapper filtering, ranking, and committed assignments.
- `AUTO_MAP_EXPORT_SCANS`: write completed raw scans to `vst_param_scans`.

The latency gate suppresses new auto-mapper discovery and disk export during recording. It does not
disable ordinary note, transport, or control handling.

## Auto-mapping

- `AUTO_MAP_MODE`: starting mode for new projects. Supported values are:
  - `FIXED_SLOTS`: preserve Cutoff, Resonance, LFO, and ADSR hardware identities where possible;
  - `DYNAMIC_RANKED`: fill controls from the ranked candidate list;
  - `SAVED_ONLY`: use only entries resolved from `vst_maps/vst_default_maps.json`.
- `AUTO_MAP_SETTLE_TIME`: seconds a channel/plugin must remain stable before scanning.
- `AUTO_MAP_EXCLUDED_PLUGINS`: plugin names excluded from heuristic scanning because they have
  curated maps or do not benefit from generic mapping.

The CATEGORY long press cycles the auto-map mode. The selected mode is persisted per project using
the shared SaveData mechanism; changing the default does not override an already-persisted project
choice.

## Safe editing

Use valid Python syntax and preserve the setting types. Boolean values must be `True` or `False`;
plugin exclusions should remain a `frozenset`; and timing values should be numeric. Back up a
project before changing settings that affect mixer levels or persistent mapping state.
