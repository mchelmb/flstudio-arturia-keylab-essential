# The Auto-Mapper

When a plugin has no hand-curated entry in `arturia_native_plugins.py`, this project tries to map
its knobs and sliders to something musically useful automatically, instead of leaving them doing
nothing or forwarding a raw, meaningless MIDI CC.

## Priority order

Three layers, checked in order, for every knob and slider independently:

1. **`arturia_native_plugins.py`** — hand-written Python, built into the project. Highest
   priority. Checked first, upstream of everything below (in `arturia_encoders.py`).
2. **`vst_maps/vst_default_maps.json`** — your own per-VST default maps (see below). Checked
   next, inside the auto-mapper.
3. **The heuristic gate/rank pipeline** — last resort. Scans whatever the plugin exposes,
   filters and ranks it, and fills in anything the first two layers didn't cover.

A plugin can be partially covered by each layer — e.g. layer 2 might define knobs 1-2 for a
plugin, leaving knobs 3-8 and all 8 sliders to layer 3's fallback.

## Your own per-VST default maps

`vst_maps/vst_default_maps.json` is a plain JSON file you (or your own tooling) can edit directly.
Re-read fresh on every patch commit — no script reload needed to see a change take effect.

```json
{
  "JE8086": {
    "knob":   ["CUTOFF FREQ", "RESO", "OSC1 CTRL2", "OSC1 CTRL1", "OSC2 CTRL1", "OSC2 CTRL2", "BASS", "TREBLE"],
    "slider": ["AMP ENV ATTACK", "AMP ENV DECAY", "AMP ENV SUSTAIN", "AMP ENV RELEASE"]
  }
}
```

- Keys are exact plugin names, as FL Studio reports them (see the scan export below for the exact
  string to use).
- `knob`/`slider` are arrays of up to 8 parameter names, in physical slot order (first entry =
  knob/slider 1). Either array can be shorter than 8 or omitted entirely.
- A `null` entry, or leaving a slot out, means "let the normal auto-mapper decide this one" - maps
  don't need to be complete to be useful.
- Names are matched case-insensitively against the plugin's actual exposed parameter names at
  commit time. If a name in your map doesn't match anything in the current scan (a typo, or the
  plugin changed its parameter names in an update), that slot logs a note (with
  `AUTO_MAP_DEBUG = True`) and falls through to the normal fallback instead of silently doing
  nothing.
- Knob/slider 9 are never covered by this file - they're permanently hardwired elsewhere (channel
  volume and mixer master, respectively).

## Building your own maps: the scan export

Every time the auto-mapper finishes analyzing a plugin, it also writes the complete raw scan -
every exposed parameter's index, name, and current value, not just what got mapped - to
`vst_param_scans/<plugin name>.json`. This happens automatically and passively; just using a
plugin normally builds up your own library of what it actually exposes. Disable with
`config.AUTO_MAP_EXPORT_SCANS = False`.

This is meant to be the raw material for curating `vst_default_maps.json` by hand, or for feeding
into your own external tooling (a GUI mapper, a script, anything that can read JSON) to help
decide which parameters deserve a physical control.

## Modes: FIXED_SLOTS vs DYNAMIC_RANKED

Governs how the heuristic fallback (layer 3) behaves - layers 1 and 2 are unaffected by this
setting.

- **`FIXED_SLOTS`** (default): knobs 1-4 keep a fixed hardware-label identity (Cutoff, Resonance,
  LFO Rate, LFO Amt), both slider ADSR quads likewise (Attack/Decay/Sustain/Release x2). Only the
  4 generic "Param" knobs are filled from the ranked pool.
- **`DYNAMIC_RANKED`**: no fixed identity at all. Every fallback slot is filled in ranked order,
  whatever that turns out to be for this specific patch.

Toggle live with a long press (2s) of the CATEGORY button; the choice persists per-project (see
[KNOWN_ISSUES.md](KNOWN_ISSUES.md#persistence)).

## The gate/rank pipeline, briefly

- **Gate**: drops structural/MIDI-CC-looking parameter names outright; infers "module activity"
  from on/off-style switch parameters by name pattern (e.g. an `Osc 2 On` reading off
  deprioritizes `Osc 2 Shape`, `Osc 2 Pitch`, etc.), hard-excluding only the two explicit cases of
  a zeroed effect mix or an engaged bypass switch.
- **Rank**: scores survivors against a 3-tier keyword hierarchy (filter/envelope/oscillator-level
  controls highest, modulation-rate/spread/macro controls next, routing/voice-count/technical
  settings lowest), original parameter index as a stable tiebreak.
- **Settle timer**: a plugin/channel change starts a debounce timer (`config.AUTO_MAP_SETTLE_TIME`,
  default 2.5s); a further change before it elapses restarts the timer, so rapid preset browsing
  doesn't trigger a remap on every single step.
- **Chunked scanning**: the actual parameter scan (the part that makes real FL API calls) runs in
  small batches across multiple idle ticks rather than one long synchronous burst, so a plugin
  with hundreds of parameters can't block controller responsiveness while it's being analyzed.

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the honest limits of all of this - in particular, the
gate stage's reliability depends entirely on a plugin following common naming conventions, which
not all of them do.
