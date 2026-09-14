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
import time

import channels
import config
import debug

from arturia_savedata import SaveData

MODE_FIXED_SLOTS = 'FIXED_SLOTS'
MODE_DYNAMIC_RANKED = 'DYNAMIC_RANKED'

# Persisted into the project via SaveData (see arturia_savedata.py - encodes small key/value data
# into the last mixer track's name, since FL doesn't limit track-name length and it saves/loads
# with the project automatically). No newer official API for this exists as of FL Studio's current
# MIDI scripting surface - this remains the standard community mechanism. Shared with whatever
# else (e.g. drum-pad pattern data) already uses SaveData in this project - always Load() before
# Commit() so a write here never clobbers unrelated keys.
_SAVEDATA_KEY = 'auto_map_mode'
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
MAX_PARAM_SCAN = 512

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
        self._savedata = SaveData()
        self._mode = None           # lazily loaded - see _get_mode()
        self._scan = None           # in-progress chunked scan state, or None

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
            channel_number = channels.channelNumber()
            plugin_name = plugins.getPluginName(channel_number, useGlobalIndex=True)
            if plugin_name and plugin_name not in config.AUTO_MAP_EXCLUDED_PLUGINS:
                self._pending_key = None
                self._pending_since_ms = None
                self._start_scan((channel_number, plugin_name))
        except Exception:
            pass
        return new_mode

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
        try:
            count = min(plugins.getParamCount(channel_number), MAX_PARAM_SCAN)
        except Exception:
            count = 0
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
        gated = gate_candidates(params, log=debug_on)
        ranked = rank_candidates(gated)

        if debug_on:
            debug.log('AutoMapper', 'PATCH STABLE: %s' % plugin_name)
            debug.log('AutoMapper', 'valid candidates: %d' % len(ranked))
            for i, c in enumerate(ranked[:16]):
                debug.log('AutoMapper', 'ranked candidates: %d: %s' % (i + 1, c[1]))

        mode = self._get_mode()
        if mode == 'DYNAMIC_RANKED':
            new_map = self._build_dynamic_map(ranked)
        else:
            discovered_names = [(idx, name) for idx, name, _value, _dep in gated]
            new_map = self._build_fixed_slots_map(discovered_names, ranked)

        # Atomic replace - the whole map is built above before this assignment, never mutated
        # in place, so a knob/slider read mid-calculation can't see a half-built map.
        self._active_map[channel_number] = new_map

        if debug_on:
            self._log_committed_map(plugin_name, new_map, dict((c[0], c[1]) for c in ranked))

    def _log_committed_map(self, plugin_name, new_map, names_by_index):
        for label, key in (('Knob', 'knob'), ('Slider', 'slider')):
            for i, param_index in enumerate(new_map[key]):
                if param_index is not None:
                    debug.log('AutoMapper', '%s %d -> %s' % (
                        label, i + 1, names_by_index.get(param_index, '?')))

    @staticmethod
    def _build_dynamic_map(ranked):
        """AUTO_MAP_MODE == 'DYNAMIC_RANKED': every slot filled in ranked order, no fixed
        hardware-label identity at all."""
        knob_params = [None] * 8
        slider_params = [None] * 8
        it = iter(c[0] for c in ranked)
        for i in range(8):
            knob_params[i] = next(it, None)
        for i in range(8):
            slider_params[i] = next(it, None)
        return {'knob': knob_params, 'slider': slider_params}

    @staticmethod
    def _build_fixed_slots_map(discovered_names, ranked):
        """AUTO_MAP_MODE == 'FIXED_SLOTS' (default): knobs 1-4 and both slider ADSR quads keep
        their fixed hardware-label identity via plain name matching (no gating/ranking needed -
        these are always top priority by definition). The 4 generic Param knobs are filled from
        the gated/ranked pool, skipping anything the fixed slots already claimed. Sliders have no
        generic slots (all 8 are the two ADSR quads), so nothing else needs the ranked pool."""
        knob_params, claimed = _match_named_slots(discovered_names, NAMED_KNOBS)
        slider_params, slider_claimed = _match_named_slots(discovered_names, NAMED_SLIDERS)
        claimed |= slider_claimed

        knob_params += [None] * (8 - len(knob_params))  # NAMED_KNOBS only defines slots 0-3
        leftover = iter(c[0] for c in ranked if c[0] not in claimed)
        for i in range(len(knob_params)):
            if knob_params[i] is None:
                knob_params[i] = next(leftover, None)

        return {'knob': knob_params, 'slider': slider_params}

    def GetKnobParam(self, channel_number, index):
        m = self._active_map.get(channel_number)
        return m['knob'][index] if m else None

    def GetSliderParam(self, channel_number, index):
        m = self._active_map.get(channel_number)
        return m['slider'][index] if m else None


_instance = AutoMapper()


def get_instance():
    return _instance
