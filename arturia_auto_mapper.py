""" Heuristic, context-aware VST parameter auto-mapper.

Two-stage pipeline over a plugin's exposed parameters (plugins.getParamCount/getParamName/
getParamValue - no structural/dependency metadata exists in FL's scripting API, so everything
below is inferred from parameter NAMES and VALUES only, never audio analysis, ML, or parameter
perturbation):

  Stage A (gate):  drop structural/MIDI-CC/aftertouch-looking parameters outright; find
                   on/off-ish "switch" parameters by name pattern and deprioritize (or, for the
                   two cases the spec calls out explicitly - zero effect mix, filter bypass on -
                   hard-exclude) other parameters that share its name prefix.
  Stage B (rank):  score every surviving candidate against a fixed 3-tier keyword hierarchy
                   (synthesis-performance relevance, highest to lowest), original parameter index
                   as a stable tiebreak.

A settle timer (config.AUTO_MAP_SETTLE_TIME, default 2.5s) debounces rapid preset browsing: a
channel/plugin change starts a pending timer; a further change before it elapses restarts the
timer from scratch; only once stable does the gate+rank pipeline run and the result atomically
replace the active map for that channel. Manual/hand-curated mappings in arturia_native_plugins.py
are checked upstream of this module entirely (in arturia_encoders.py) and always win - this module
is only ever consulted as a fallback.

NOTE ON RELIABILITY: the name-pattern heuristics below (switch detection, prefix matching, tier
keywords) work well on conventionally-named plugins and will simply miss relationships on plugins
that don't follow that convention. There is no way to make this reliable in the general case -
only defensible in the common one. A missed inference degrades to "included, maybe not top
priority" rather than "silently invisible", except for the two spec-explicit hard-exclusion cases.
"""
import json
import os
import time

import channels
import config
import debug
import ui

from arturia_savedata import SaveData

MODE_FIXED_SLOTS = 'FIXED_SLOTS'
MODE_DYNAMIC_RANKED = 'DYNAMIC_RANKED'

# --------------------[ User-editable per-VST default maps ]-----------------------------------
# A third priority layer, between arturia_native_plugins.py (hand-curated Python, highest
# priority, checked upstream in arturia_encoders.py) and this module's own heuristic gate/rank
# fallback (lowest priority): a JSON file mapping plugin name -> knob/slider parameter NAMES
# (not indices - resolved dynamically against each scan, so it survives a plugin reordering its
# own parameter indices between versions, and stays human-readable/editable, including by an
# external tool). Entries can be partial - any slot left null/missing falls through to the normal
# gate/rank fallback for just that slot. See docs/AUTO_MAPPER.md for the schema.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_VST_MAP_PATH = os.path.join(_SCRIPT_DIR, 'vst_maps', 'vst_default_maps.json')

# Every completed parameter scan is also dumped here as <plugin_name>.json (full name/value list,
# not just what got mapped) - a passive, zero-effort way to build up a personal library of what
# each plugin actually exposes, useful as the raw material for curating USER_VST_MAP_PATH by hand
# or with an external tool. Set config.AUTO_MAP_EXPORT_SCANS = False to disable.
SCAN_EXPORT_DIR = os.path.join(_SCRIPT_DIR, 'vst_param_scans')

# Persisted into the project via SaveData (see arturia_savedata.py - encodes small key/value data
# into the last mixer track's name, since FL doesn't limit track-name length and it saves/loads
# with the project automatically). No newer official API for this exists as of FL Studio's current
# MIDI scripting surface - this remains the standard community mechanism. Shared with whatever
# else (e.g. drum-pad pattern data) already uses SaveData in this project - always Load() before
# Commit() so a write here never clobbers unrelated keys.
_SAVEDATA_KEY = 'auto_map_mode'
_ENCODER8_VOLUME_KEY = 'encoder8_volume_override'
_MODE_TO_INT = {MODE_FIXED_SLOTS: 0, MODE_DYNAMIC_RANKED: 1}
_INT_TO_MODE = {value: key for key, value in _MODE_TO_INT.items()}

SCRIPT_VERSION = None
try:
    import general
    SCRIPT_VERSION = general.getVersion()
    if SCRIPT_VERSION >= 8:
        import plugins
except Exception:
    pass

PATCH_SETTLE_TIME = getattr(config, 'AUTO_MAP_SETTLE_TIME', 2.5)
MAX_PARAM_SCAN = 8192
MAX_PARAMETER_BANKS = 16
PARAMETERS_PER_BANK = 16

# Params scanned per idle tick during a settle-commit. Scanning (not gating/ranking, which are
# cheap pure-Python list ops on an already-small result) is the part that makes real FL API calls
# per parameter - one per plugins.getParamName/getParamValue - so it's the part that needs to be
# spread across multiple ticks rather than done in one long synchronous burst, which would block
# button responsiveness for however long a big plugin's full scan takes.
SCAN_CHUNK_SIZE = 32

# Structural/internal/global-controller parameter names that are never musically relevant controls
# for a hardware knob/slider, regardless of ranking.
EXCLUDED_NAME_SUBSTRINGS = (
    'midi cc', 'aftertouch', 'internal', 'reserved', 'unused', 'debug', 'test param',
)

# Words that, as the LAST word of a parameter name, indicate an on/off/bypass/enable switch.
# Checked as whole trailing words, not substrings - 'on' as a raw substring would false-positive
# match inside names like "Resonance".
SWITCH_LAST_WORDS = frozenset({'on', 'off', 'on/off', 'enable', 'enabled', 'active', 'bypass'})

# Stage B priority tiers - lower tier number = higher priority. Checked longest-keyword-first
# within a tier is unnecessary here since these are independent categories, not overlapping
# synonyms for one slot (contrast arturia_encoders.NAMED_KNOBS/NAMED_SLIDERS, which do need that).
TIER_1_KEYWORDS = (
    'cutoff', 'resonance', 'attack', 'decay', 'sustain', 'release', 'shape', 'osc mix',
    'oscillator mix', 'fm amount', 'fm amt', 'lfo depth', 'lfo amount', 'effect mix', 'mix',
)
TIER_2_KEYWORDS = (
    'unison', 'pulse width', 'pwm', 'lfo rate', 'lfo speed', 'spread', 'fine pitch', 'fine tune',
    'detune', 'macro',
)
TIER_3_KEYWORDS = (
    'routing', 'algorithm', 'voice count', 'voices', 'polyphony',
)
TIER_UNRANKED = 4  # anything matching no tier - still a valid candidate, lowest priority

# Hardware-printed names for knobs 1-8 and sliders 1-8 (from a photo of the KeyLab layout; knob 9/
# slider 9 are hardwired elsewhere - VST volume / master - and never go through this table).
# Keywords are tried longest-first per slot so a specific phrase like "filter cutoff" is preferred
# over a generic one like "freq". Only used in AUTO_MAP_MODE == 'FIXED_SLOTS'; ignored entirely in
# 'DYNAMIC_RANKED' mode, where these knobs/sliders are filled from the ranked pool like everything
# else. Param 1-4 have no name printed on the hardware in FIXED mode, so they're filled from the
# gated/ranked pool directly (see AutoMapper._commit), not from this table.
NAMED_KNOBS = [
    frozenset({'cutoff', 'filter cutoff', 'filter freq', 'lpf', 'freq', 'frequency'}),
    frozenset({'resonance', 'filter resonance', 'reso', 'emphasis'}),
    frozenset({'lfo rate', 'lfo speed', 'rate'}),
    frozenset({'lfo amount', 'lfo amt', 'lfo depth', 'depth'}),
]
NAMED_SLIDERS = [
    frozenset({'attack', 'atk'}),   # Envelope 1 (Attack/Decay/Sustain/Release, CH1-4 labels)
    frozenset({'decay', 'dec'}),
    frozenset({'sustain', 'sus'}),
    frozenset({'release', 'rel'}),
    frozenset({'attack', 'atk'}),   # Envelope 2 (second ADSR quad, CH5-8 labels)
    frozenset({'decay', 'dec'}),
    frozenset({'sustain', 'sus'}),
    frozenset({'release', 'rel'}),
]

VOLUME_NAME_PRIORITY = (
    'master volume', 'output volume', 'main volume', 'volume', 'output level', 'level',
)


def find_volume_param(params):
    """Find the best exposed VST volume parameter for the Encoder 8 override."""
    candidates = [(idx, name) for idx, name, _value in params]
    for wanted in VOLUME_NAME_PRIORITY:
        for idx, name in candidates:
            if name.strip().lower() == wanted:
                return idx
    for wanted in VOLUME_NAME_PRIORITY:
        for idx, name in candidates:
            if wanted in name.lower():
                return idx
    return None


def _is_excluded_name(name):
    lowered = name.lower()
    return any(token in lowered for token in EXCLUDED_NAME_SUBSTRINGS)


def _rank_tier(name):
    lowered = name.lower()
    for keyword in TIER_1_KEYWORDS:
        if keyword in lowered:
            return 1
    for keyword in TIER_2_KEYWORDS:
        if keyword in lowered:
            return 2
    for keyword in TIER_3_KEYWORDS:
        if keyword in lowered:
            return 3
    return TIER_UNRANKED


def _switch_prefix(name):
    """If name's last word looks like an on/off/bypass/enable switch, returns its module-prefix
    token (everything before that word, lowercased/trimmed) for sibling matching. Returns None
    if name doesn't look like a switch. Whole-word check only - 'on' as a raw substring would
    false-positive match inside names like "Resonance"."""
    words = name.lower().strip().split()
    if not words:
        return None
    last_word = words[-1].strip('/:-')
    if last_word in SWITCH_LAST_WORDS:
        prefix = ' '.join(words[:-1]).strip()
        return prefix or None
    return None


def scan_params(channel_number):
    """Stage 0: raw scan. Returns list of (index, name, value), empty/excluded names dropped."""
    if SCRIPT_VERSION is None or SCRIPT_VERSION < 8:
        return []
    params = []
    try:
        count = min(plugins.getParamCount(channel_number), MAX_PARAM_SCAN)
        for i in range(count):
            name = plugins.getParamName(i, channel_number)
            if not name or _is_excluded_name(name):
                continue
            try:
                value = plugins.getParamValue(i, channel_number)
            except Exception:
                value = None
            params.append((i, name, value))
    except Exception:
        return []
    return params


def gate_candidates(params, log=False):
    """Stage A: contextual filtering by inferred module activity. Returns the subset of params
    that survive, each as (index, name, value, deprioritized: bool)."""
    # Find switch-like parameters and what they imply about their sibling module. The switch/mix/
    # bypass parameter's own index is tracked separately and never self-excluded - a zero-value
    # mix knob is itself the useful "reactivate this effect" control, not an internal parameter of
    # the thing it gates (per spec wording: "its internal parameters" fall out, not the switch).
    hard_excluded_prefixes = set()   # effect mix == 0, or a bypass switch reading "on"
    deprioritized_prefixes = set()   # generic enable/active/on switch reading "off"
    switch_indices = set()

    for idx, name, value in params:
        if value is None:
            continue
        lowered = name.lower()
        if 'mix' in lowered and value <= 0.02:
            # Spec-explicit hard exclusion: effect mix at zero.
            prefix = lowered.split('mix')[0].strip()
            if prefix:
                hard_excluded_prefixes.add(prefix)
                switch_indices.add(idx)
            continue
        if 'bypass' in lowered and value >= 0.5:
            # Spec-explicit hard exclusion: filter/effect bypass switched on.
            prefix = lowered.split('bypass')[0].strip()
            if prefix:
                hard_excluded_prefixes.add(prefix)
                switch_indices.add(idx)
            continue
        prefix = _switch_prefix(name)
        if prefix is not None and value <= 0.05:
            deprioritized_prefixes.add(prefix)
            switch_indices.add(idx)

    gated = []
    for idx, name, value in params:
        lowered = name.lower()
        if idx not in switch_indices and any(
                lowered.startswith(p) for p in hard_excluded_prefixes if p):
            if log:
                debug.log('AutoMapper', 'excluded (inactive module): %s' % name)
            continue
        deprioritized = (idx not in switch_indices and
                         any(lowered.startswith(p) for p in deprioritized_prefixes if p))
        gated.append((idx, name, value, deprioritized))
    return gated


def rank_candidates(gated):
    """Stage B: sort gated candidates by (tier asc, deprioritized last, original index asc)."""
    scored = [(idx, name, value, deprioritized, _rank_tier(name))
              for idx, name, value, deprioritized in gated]
    scored.sort(key=lambda c: (1 if c[3] else 0, c[4], c[0]))
    return scored


def _sanitize_filename(name):
    """Makes a plugin name safe to use as a filename - keeps it human-readable rather than
    hashing it, since these files are meant to be opened and read by a person (or their own
    tooling)."""
    safe = ''.join(c if (c.isalnum() or c in ' ._-') else '_' for c in name)
    return safe.strip() or 'unnamed'


def export_scan(plugin_name, params):
    """Dumps a completed scan's full name/value list to SCAN_EXPORT_DIR/<plugin_name>.json.
    Best-effort - a failure here (e.g. no write permission) never blocks the actual mapping."""
    if not getattr(config, 'AUTO_MAP_EXPORT_SCANS', True):
        return
    try:
        os.makedirs(SCAN_EXPORT_DIR, exist_ok=True)
        path = os.path.join(SCAN_EXPORT_DIR, _sanitize_filename(plugin_name) + '.json')
        payload = {
            'plugin_name': plugin_name,
            'params': [{'index': idx, 'name': name, 'value': value}
                       for idx, name, value in params],
        }
        with open(path, 'w') as f:
            json.dump(payload, f, indent=2)
        if getattr(config, 'AUTO_MAP_DEBUG', False):
            debug.log('AutoMapper', 'Exported %d params for %s -> %s' % (
                len(params), plugin_name, path))
    except Exception as e:
        debug.log('AutoMapper', 'Scan export failed (non-fatal): %s' % repr(e))


_user_vst_map_cache = None


def _load_user_vst_map():
    """Re-reads USER_VST_MAP_PATH fresh on every call (cheap for a small JSON file, and means
    edits made externally - by hand or by your own tooling - take effect on the very next patch
    commit, no script reload needed). Returns {} on any error (missing file, malformed JSON) -
    never raises, so a syntax mistake in the file degrades to "no user maps" rather than breaking
    the whole auto-mapper."""
    try:
        with open(USER_VST_MAP_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        debug.log('AutoMapper', 'vst_default_maps.json failed to parse (ignored): %s' % repr(e))
        return {}


def get_page_count(plugin_name):
    """Returns how many curated pages plugin_name has in the user VST map, or 0 if it has no
    multi-page entry (either no entry at all, or an old-style flat single-page one). Callers use
    this to decide whether Left/Right should cycle pages for the currently focused plugin."""
    entry = _load_user_vst_map().get(plugin_name)
    pages = entry.get('pages') if entry else None
    return len(pages) if isinstance(pages, list) and pages else 0


def _resolve_json_slots(plugin_name, params, page_index=0):
    """Looks up plugin_name in the user VST map and resolves each named slot to its current
    parameter index against this scan's actual results (case-insensitive exact match). Returns
    (knob_prefill, slider_prefill, claimed) - two 8-entry lists (None where unresolved/unspecified)
    and the set of indices they claim, so the normal gate/rank fallback never double-assigns
    something the user's map already claimed.

    Supports two formats: a flat single-page entry ({"knob": [...], "slider": [...]}), or a
    multi-page one ({"pages": [{"name": ..., "knob": [...], "slider": [...]}, ...]}) - page_index
    selects which page of the latter to use, clamped to a valid range."""
    entry = _load_user_vst_map().get(plugin_name)
    knob_prefill = [None] * 8
    slider_prefill = [None] * 8
    claimed = set()
    if not entry:
        return knob_prefill, slider_prefill, claimed

    pages = entry.get('pages')
    if isinstance(pages, list) and pages:
        page_index = max(0, min(page_index, len(pages) - 1))
        entry = pages[page_index]

    name_to_index = {}
    for idx, name, _value in params:
        name_to_index.setdefault(name.lower(), idx)

    for label, prefill in (('knob', knob_prefill), ('slider', slider_prefill)):
        wanted = entry.get(label) or []
        for i, param_name in enumerate(wanted[:8]):
            if not param_name:
                continue
            idx = name_to_index.get(str(param_name).lower())
            if idx is not None:
                prefill[i] = idx
                claimed.add(idx)
            else:
                debug.log('AutoMapper', 'User map: "%s" not found in current scan for %s' % (
                    param_name, plugin_name))
    return knob_prefill, slider_prefill, claimed


def _match_named_slots(discovered_names, slots):
    """Greedy best-effort match: for each hardware-printed slot, in priority order, tries its
    keywords longest-first against still-unclaimed discovered parameter names. discovered_names
    is a list of (index, name). Returns (params_out, claimed_indices)."""
    claimed = set()
    params_out = [None] * len(slots)
    for position, keywords in enumerate(slots):
        if not keywords:
            continue
        for keyword in sorted(keywords, key=len, reverse=True):
            found = None
            for idx, name in discovered_names:
                if idx in claimed:
                    continue
                if keyword in name.lower():
                    found = idx
                    break
            if found is not None:
                params_out[position] = found
                claimed.add(found)
                break
    return params_out, claimed


class AutoMapper:
    """Owns the settle timer and the committed active map, per channel."""

    def __init__(self):
        self._pending_key = None
        self._pending_since_ms = None
        self._active_map = {}       # channel_number -> {'knob': [8], 'slider': [8]}
        self._bank_maps = {}        # channel_number -> 16 maps of 8 knobs and 8 sliders
        self._volume_params = {}    # channel_number -> discovered VST volume parameter index
        self._savedata = SaveData()
        self._mode = None           # lazily loaded - see _get_mode()
        self._scan = None           # in-progress chunked scan state, or None
        self._active_page = {}      # channel_number -> current page index, multi-page maps
        self._last_scan_params = {} # channel_number -> params from its most recent full
                                     # scan, so CyclePage re-commits without a re-scan

    def _debug_enabled(self):
        return bool(getattr(config, 'AUTO_MAP_DEBUG', False))

    def _get_mode(self):
        """Loads the persisted per-project mode on first use, falling back to config.AUTO_MAP_MODE
        if nothing's been persisted yet for this project (e.g. a brand new project, or one created
        before this feature existed)."""
        if self._mode is not None:
            return self._mode
        default = getattr(config, 'AUTO_MAP_MODE', MODE_FIXED_SLOTS)
        try:
            self._savedata.Load()
            stored = self._savedata.Get(_SAVEDATA_KEY)
            self._mode = _INT_TO_MODE.get(stored[0], default) if stored else default
        except Exception:
            self._mode = default
        return self._mode

    def ToggleMode(self):
        """Flips FIXED_SLOTS<->DYNAMIC_RANKED, persists the choice into the project, and
        immediately re-commits the currently selected channel/plugin under the new mode rather
        than waiting for the settle timer - this is a deliberate one-off action (a long CATEGORY
        press), not rapid preset browsing, so instant feedback is the right call here. Returns the
        new mode string for an LCD confirmation."""
        new_mode = MODE_DYNAMIC_RANKED if self._get_mode() == MODE_FIXED_SLOTS else MODE_FIXED_SLOTS
        self._mode = new_mode
        try:
            self._savedata.Load()  # merge with whatever else already uses this shared mechanism
            self._savedata.Put(_SAVEDATA_KEY, [_MODE_TO_INT[new_mode]])
            self._savedata.Commit()
        except Exception:
            if self._debug_enabled():
                debug.log('AutoMapper', 'Failed to persist mode toggle (non-fatal)')
        try:
            if not ui.getFocused(5):  # WID_PLUGIN
                if self._debug_enabled():
                    debug.log('AutoMapper', 'ToggleMode: no plugin focused, nothing to re-map yet')
            else:
                channel_number = channels.channelNumber()
                plugin_name = ui.getFocusedPluginName()
                if plugin_name and plugin_name not in config.AUTO_MAP_EXCLUDED_PLUGINS:
                    self._pending_key = None
                    self._pending_since_ms = None
                    self._start_scan((channel_number, plugin_name))
        except Exception as e:
            if self._debug_enabled():
                debug.log('AutoMapper', 'ToggleMode re-map failed: %s' % repr(e))
        return new_mode

    def IsEncoder8VolumeOverrideEnabled(self):
        try:
            self._savedata.Load()
            stored = self._savedata.Get(_ENCODER8_VOLUME_KEY)
            return bool(stored and stored[0])
        except Exception:
            return False

    def ToggleEncoder8VolumeOverride(self):
        enabled = not self.IsEncoder8VolumeOverrideEnabled()
        try:
            self._savedata.Load()
            self._savedata.Put(_ENCODER8_VOLUME_KEY, [1 if enabled else 0])
            self._savedata.Commit()
        except Exception:
            if self._debug_enabled():
                debug.log('AutoMapper', 'Failed to persist Encoder 8 volume override (non-fatal)')
        return enabled

    def NotifyChannelPlugin(self, channel_number, plugin_name, now_ms):
        """Call every idle tick with the currently selected channel + plugin name. Starts/resets
        the settle timer on a change; does nothing else (the pipeline only runs on commit)."""
        key = (channel_number, plugin_name)
        if key == self._pending_key:
            return
        self._pending_key = key
        self._pending_since_ms = now_ms
        if self._debug_enabled():
            debug.log('AutoMapper', 'Pending: %s (settling %.1fs)' % (plugin_name,
                                                                        PATCH_SETTLE_TIME))

    def Idle(self, now_ms):
        """Call every idle tick. Advances an in-progress chunked scan if one is running (bounded
        to SCAN_CHUNK_SIZE parameters per call); otherwise, starts one once the pending key has
        been stable for PATCH_SETTLE_TIME seconds."""
        if self._scan is not None:
            self._advance_scan()
            return
        if self._pending_key is None:
            return
        if now_ms - self._pending_since_ms < PATCH_SETTLE_TIME * 1000:
            return
        key = self._pending_key
        self._pending_key = None
        self._pending_since_ms = None
        self._start_scan(key)

    def _start_scan(self, key):
        channel_number, plugin_name = key
        if SCRIPT_VERSION is None or SCRIPT_VERSION < 8:
            return
        debug_on = self._debug_enabled()
        try:
            raw_count = plugins.getParamCount(channel_number)
            count = min(raw_count, MAX_PARAM_SCAN)
            if debug_on:
                debug.log('AutoMapper', 'Starting scan: %s, channel %d, %d params (capped at %d)'
                          % (plugin_name, channel_number, raw_count, MAX_PARAM_SCAN))
        except Exception as e:
            count = 0
            if debug_on:
                debug.log('AutoMapper', 'getParamCount failed: %s' % repr(e))
        self._scan = {
            'channel_number': channel_number,
            'plugin_name': plugin_name,
            'next_index': 0,
            'count': count,
            'params': [],
        }
        if count == 0:
            self._advance_scan()  # nothing to scan - finishes (and commits) immediately

    def _advance_scan(self):
        scan = self._scan
        channel_number = scan['channel_number']
        end = min(scan['next_index'] + SCAN_CHUNK_SIZE, scan['count'])
        for i in range(scan['next_index'], end):
            try:
                name = plugins.getParamName(i, channel_number)
                if name and not _is_excluded_name(name):
                    try:
                        value = plugins.getParamValue(i, channel_number)
                    except Exception:
                        value = None
                    scan['params'].append((i, name, value))
            except Exception:
                pass
        scan['next_index'] = end
        if scan['next_index'] >= scan['count']:
            self._scan = None
            self._commit((channel_number, scan['plugin_name']), scan['params'])

    def _commit(self, key, params):
        channel_number, plugin_name = key
        debug_on = self._debug_enabled()

        export_scan(plugin_name, params)
        self._last_scan_params[channel_number] = params

        gated = gate_candidates(params, log=debug_on)
        ranked = rank_candidates(gated)

        if debug_on:
            debug.log('AutoMapper', 'PATCH STABLE: %s' % plugin_name)
            debug.log('AutoMapper', 'valid candidates: %d' % len(ranked))
            for i, c in enumerate(ranked[:16]):
                debug.log('AutoMapper', 'ranked candidates: %d: %s' % (i + 1, c[1]))

        page_index = self._active_page.get(channel_number, 0)
        knob_prefill, slider_prefill, claimed = _resolve_json_slots(
            plugin_name, params, page_index)

        mode = self._get_mode()
        if mode == 'DYNAMIC_RANKED':
            new_map = self._build_dynamic_map(ranked, knob_prefill, slider_prefill, claimed)
        else:
            discovered_names = [(idx, name) for idx, name, _value, _dep in gated]
            new_map = self._build_fixed_slots_map(discovered_names, ranked,
                                                   knob_prefill, slider_prefill, claimed)

        # Atomic replace - the whole map is built above before this assignment, never mutated
        # in place, so a knob/slider read mid-calculation can't see a half-built map.
        self._active_map[channel_number] = new_map
        self._bank_maps[channel_number] = self._build_parameter_banks(
            ranked, new_map, knob_prefill, slider_prefill, claimed)
        self._volume_params[channel_number] = find_volume_param(params)

        if debug_on:
            self._log_committed_map(plugin_name, new_map, dict((c[0], c[1]) for c in ranked))

    def _log_committed_map(self, plugin_name, new_map, names_by_index):
        for label, key in (('Knob', 'knob'), ('Slider', 'slider')):
            for i, param_index in enumerate(new_map[key]):
                if param_index is not None:
                    debug.log('AutoMapper', '%s %d -> %s' % (
                        label, i + 1, names_by_index.get(param_index, '?')))

    @staticmethod
    def _build_dynamic_map(ranked, knob_prefill, slider_prefill, claimed):
        """AUTO_MAP_MODE == 'DYNAMIC_RANKED': the user's JSON map (if any) is honored first, then
        every remaining slot filled in ranked order - no fixed hardware-label identity at all."""
        knob_params = list(knob_prefill)
        slider_params = list(slider_prefill)
        leftover = iter(c[0] for c in ranked if c[0] not in claimed)
        for i in range(8):
            if knob_params[i] is None:
                knob_params[i] = next(leftover, None)
        for i in range(8):
            if slider_params[i] is None:
                slider_params[i] = next(leftover, None)
        return {'knob': knob_params, 'slider': slider_params}

    @staticmethod
    def _build_parameter_banks(ranked, first_map, knob_prefill, slider_prefill, claimed):
        """Build sixteen banks of eight knobs and eight sliders from the ranked VST pool.

        Bank 0 retains the normal curated/heuristic map. Later banks consume the remaining
        ranked parameters in groups of sixteen, allowing the LIVE/BANK controls to expose
        substantially more of a large VST without changing the normal first-bank behavior.
        """
        banks = [first_map]
        reserved = set(claimed)
        reserved.update(param for param in first_map['knob'] if param is not None)
        reserved.update(param for param in first_map['slider'] if param is not None)
        remaining = [candidate[0] for candidate in ranked if candidate[0] not in reserved]
        for bank_index in range(1, MAX_PARAMETER_BANKS):
            start = (bank_index - 1) * PARAMETERS_PER_BANK
            values = remaining[start:start + PARAMETERS_PER_BANK]
            banks.append({
                'knob': values[:8] + [None] * (8 - len(values[:8])),
                'slider': values[8:16] + [None] * (8 - len(values[8:16])),
            })
        return banks

    @staticmethod
    def _build_fixed_slots_map(discovered_names, ranked, knob_prefill, slider_prefill, claimed):
        """AUTO_MAP_MODE == 'FIXED_SLOTS' (default): the user's JSON map (if any) is honored
        first. Any knob/slider slot it doesn't cover falls through to the existing fixed
        hardware-label identity (Cutoff/Resonance/.../ADSR x2, via plain name matching), and
        anything still empty after that (generic Param knobs, or an ADSR slot with no match) is
        filled from the gated/ranked pool."""
        matched_knobs, name_claimed = _match_named_slots(discovered_names, NAMED_KNOBS)
        matched_sliders, slider_name_claimed = _match_named_slots(discovered_names, NAMED_SLIDERS)

        # NAMED_KNOBS only defines slots 0-3 - matched_knobs may be shorter than 8.
        knob_params = list(knob_prefill)
        for i, v in enumerate(matched_knobs):
            if knob_params[i] is None:
                knob_params[i] = v
        slider_params = list(slider_prefill)
        for i, v in enumerate(matched_sliders):
            if slider_params[i] is None:
                slider_params[i] = v

        all_claimed = claimed | name_claimed | slider_name_claimed
        leftover = iter(c[0] for c in ranked if c[0] not in all_claimed)
        for i in range(8):
            if knob_params[i] is None:
                knob_params[i] = next(leftover, None)

        return {'knob': knob_params, 'slider': slider_params}

    def GetKnobParam(self, channel_number, index, bank_index=0):
        banks = self._bank_maps.get(channel_number)
        m = banks[bank_index % MAX_PARAMETER_BANKS] if banks else self._active_map.get(channel_number)
        return m['knob'][index] if m else None

    def GetPageCount(self, plugin_name):
        return get_page_count(plugin_name)

    def GetPageName(self, channel_number, plugin_name):
        """Returns the current page's display name, or None if this plugin has no multi-page
        map."""
        entry = _load_user_vst_map().get(plugin_name)
        pages = entry.get('pages') if entry else None
        if not (isinstance(pages, list) and pages):
            return None
        idx = self._active_page.get(channel_number, 0) % len(pages)
        return pages[idx].get('name', 'Page %d' % (idx + 1))

    def CyclePage(self, channel_number, plugin_name, delta):
        """Cycles the curated multi-page map's active page for this channel and immediately
        re-commits using the cached scan (no full re-scan needed - the plugin hasn't changed,
        only which curated names we resolve against). Returns False if this plugin has no
        multi-page map, so callers fall through to their own default Left/Right behavior."""
        count = get_page_count(plugin_name)
        if count == 0:
            return False
        self._active_page[channel_number] = (
            self._active_page.get(channel_number, 0) + delta) % count
        params = self._last_scan_params.get(channel_number)
        if params is not None:
            self._commit((channel_number, plugin_name), params)
        else:
            self._start_scan((channel_number, plugin_name))
        return True

    def GetVolumeParam(self, channel_number):
        return self._volume_params.get(channel_number)

    def GetSliderParam(self, channel_number, index, bank_index=0):
        banks = self._bank_maps.get(channel_number)
        m = banks[bank_index % MAX_PARAMETER_BANKS] if banks else self._active_map.get(channel_number)
        return m['slider'][index] if m else None


_instance = AutoMapper()


def get_instance():
    return _instance
