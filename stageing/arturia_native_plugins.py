# Ported from Image-Line's official KeyLab Essential integration script
# (KeyLabEssPlugin.py, credited to Fares MEZDOUR), which itself builds on
# Ray Juang's MIT-licensed MidiEventDispatcher.
#
# This module lets the 9 encoder knobs and 9 faders drive FL Studio's
# native/bundled instruments directly by parameter index, via
# plugins.setParamValue(), instead of relying on generic MIDI CC forwarding
# through a virtual port plus manual Remote Control Settings links.
#
# Control key convention (matches Image-Line's own table):
#   '16'..'23'   -> the 8 encoder knobs, keyed by event.controlNum
#   '224'..'231' -> the 8 faders/sliders, keyed by (224 + slider_index)
#   '1'          -> reserved (e.g. mod wheel); unused (-1) for most plugins
#
# Values are the plugin's native parameter index (as returned by
# plugins.getParamName / consumed by plugins.setParamValue). -1 means the
# plugin is recognized but that particular control isn't mapped for it.

NATIVE_PARAM_MAPS = {
    'FLEX': {
        '16': 21, '17': 22, '18': 25, '19': 30,
        '20': 0, '21': 2, '22': 3, '23': 4,
        '224': 10, '225': 11, '226': 12, '227': 13,
        '228': 14, '229': 15, '230': 16, '231': 17,
        '1': -1,
    },
    'FPC': {
        '16': 8, '17': 9, '18': 10, '19': 11,
        '20': 12, '21': 13, '22': 14, '23': 15,
        '224': 0, '225': 1, '226': 2, '227': 3,
        '228': 4, '229': 5, '230': 6, '231': 7,
        '1': -1,
    },
    'FL Keys': {
        '16': 0, '17': 1, '18': 14, '19': 13,
        '20': 5, '21': 4, '22': 4, '23': 8,
        '224': 12, '225': 7, '226': 11, '227': 10,
        '228': 3, '229': 2, '230': 6, '231': 9,
        '1': -1,
    },
    'Sytrus': {
        '16': 18, '17': 19, '18': 1, '19': 11,
        '20': 12, '21': 13, '22': 14, '23': 15,
        '224': 3, '225': 4, '226': 5, '227': 6,
        '228': 7, '229': 8, '230': 9, '231': 10,
        '1': -1,
    },
    'GMS': {
        '16': 32, '17': 33, '18': 46, '19': 45,
        '20': 56, '21': 57, '22': 58, '23': 65,
        '224': 24, '225': 25, '226': 26, '227': 27,
        '228': 40, '229': 41, '230': 42, '231': 38,
        '1': -1,
    },
    'Harmless': {
        '16': 54, '17': 59, '18': 58, '19': 89,
        '20': 65, '21': 79, '22': 97, '23': 91,
        '224': 26, '225': 27, '226': 31, '227': 28,
        '228': 48, '229': 49, '230': 52, '231': 58,
        '1': -1,
    },
    'Harmor': {
        '16': 52, '17': 57, '18': 438, '19': 443,
        '20': 787, '21': 791, '22': 803, '23': 810,
        '224': 103, '225': 104, '226': 105, '227': 106,
        '228': 127, '229': 128, '230': 129, '231': 130,
        '1': -1,
    },
    'Morphine': {
        '16': 40, '17': 41, '18': 1, '19': 6,
        '20': 30, '21': 31, '22': 32, '23': 33,
        '224': 21, '225': 22, '226': 23, '227': 24,
        '228': 25, '229': 26, '230': 27, '231': 28,
        '1': -1,
    },
    '3x Osc': {
        '16': 1, '17': 2, '18': 8, '19': 9,
        '20': 7, '21': 15, '22': 16, '23': 14,
        '224': 4, '225': 5, '226': 11, '227': 12,
        '228': 18, '229': 19, '230': 6, '231': 13,
        '1': -1,
    },
    'Fruity DX10': {
        '16': 11, '17': 21, '18': 13, '19': 10,
        '20': 3, '21': 4, '22': 14, '23': 15,
        '224': 0, '225': 1, '226': 2, '227': 4,
        '228': 5, '229': 6, '230': 7, '231': 8,
        '1': -1,
    },
    'BASSDRUM': {
        '16': 8, '17': 7, '18': 6, '19': 0,
        '20': 4, '21': 3, '22': 5, '23': 2,
        '224': 9, '225': 10, '226': 11, '227': 12,
        '228': 14, '229': 13, '230': 15, '231': 1,
        '1': -1,
    },
    'Fruit kick': {
        '16': -1, '17': -1, '18': -1, '19': -1,
        '20': -1, '21': -1, '22': -1, '23': -1,
        '224': 0, '225': 1, '226': 2, '227': 3,
        '228': 4, '229': 5, '230': -1, '231': -1,
        '1': -1,
    },
    'MiniSynth': {
        '16': 8, '17': 9, '18': 20, '19': 19,
        '20': 5, '21': 2, '22': 25, '23': 26,
        '224': 12, '225': 13, '226': 14, '227': 15,
        '228': 21, '229': 22, '230': 23, '231': 24,
        '1': 1,
    },
    'PoiZone': {
        '16': 18, '17': 19, '18': 26, '19': 28,
        '20': 29, '21': 30, '22': 15, '23': 46,
        '224': 11, '225': 12, '226': 13, '227': 14,
        '228': 22, '229': 23, '230': 24, '231': 25,
        '1': 43,
    },
    'Sakura': {
        '16': 29, '17': 30, '18': 33, '19': 31,
        '20': 24, '21': 25, '22': 9, '23': 14,
        '224': 34, '225': 35, '226': 36, '227': 37,
        '228': 2, '229': 3, '230': 4, '231': 5,
        '1': 43,
    },
}


# User-added mappings for third-party VSTs (Vital, Serum, etc). Same format
# and control-key convention as NATIVE_PARAM_MAPS above. Unlike FL's bundled
# instruments, third-party parameter indices are NOT documented anywhere and
# are NOT guaranteed to stay stable across plugin versions/updates -- always
# derive them from dump_current_plugin_params() below rather than guessing.
#
# Example, once you've dumped Vital's real indices:
# VST_PARAM_MAPS = {
#     'Vital': {
#         '16': 4,   # e.g. Filter 1 Cutoff
#         '17': 5,   # e.g. Filter 1 Resonance
#         ...
#     },
# }
VST_PARAM_MAPS = {
}


def is_native_plugin(plugin_name):
    """True if this plugin name has a known native or user-added parameter map."""
    return plugin_name in NATIVE_PARAM_MAPS or plugin_name in VST_PARAM_MAPS


def get_param_index(plugin_name, control_key):
    """Return the mapped parameter index for a recognized plugin/control.

    plugin_name: result of ui.getFocusedPluginName().
    control_key: string key, e.g. str(event.controlNum) for a knob (16-23),
                 or str(224 + slider_index) for a fader (224-231).

    Returns:
      None  -> plugin isn't in either map.
      -1    -> plugin is recognized, but this control has no mapping for it.
      int   -> the parameter index to write with plugins.setParamValue().
    """
    param_map = NATIVE_PARAM_MAPS.get(plugin_name)
    if param_map is None:
        param_map = VST_PARAM_MAPS.get(plugin_name)
    if param_map is None:
        return None
    return param_map.get(control_key, -1)


def dump_current_plugin_params():
    """Print every parameter index + name for the CURRENTLY FOCUSED plugin's
    editor window to FL's script output console (View menu -> Script output,
    or the debug console depending on your FL version).

    Use this once per new VST you want to map: open the VST's editor so it's
    the focused window, then trigger this function (see config.py /
    arturia_encoders.py for how it's wired to a debug flag). Read off the
    index numbers next to the parameter names you want on your 8 knobs / 8
    faders, then add a new entry to VST_PARAM_MAPS above using those indices.
    """
    import channels
    import plugins
    import ui

    plugin_idx = channels.channelNumber()
    name = ui.getFocusedPluginName()
    count = plugins.getParamCount(plugin_idx)
    print('--- Parameters for "%s" (%d total) ---' % (name, count))
    for i in range(count):
        print('%3d: %s' % (i, plugins.getParamName(i, plugin_idx)))
    print('--- end of parameter dump ---')
