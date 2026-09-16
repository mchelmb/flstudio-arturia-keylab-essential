""" Detects fake/stub FL Studio modules sitting in the script folder.

FL Studio provides `ui`, `plugins`, `channels`, `mixer`, `transport`, `midi`, `device`, etc. as
built-in modules. Python resolves the script's own folder FIRST on sys.path, so a file named
e.g. `ui.py` sitting next to these scripts will SHADOW FL Studio's real module - every call then
silently hits a fake that returns dummy values, and the whole script misbehaves in ways that look
like logic bugs rather than an import problem.

This happens easily: offline test stubs (the kind an AI assistant or a local test harness
generates so the code can be imported outside FL Studio) get copied into the deployment folder by
accident. The failure is near-impossible to diagnose from symptoms alone, so this guard checks for
it at startup and reports it loudly instead.

Import and call check_for_stubs() early in the device script.
"""
import os

# Modules FL Studio provides itself. A .py file with any of these names in the script folder is
# always a mistake.
_FL_BUILTIN_MODULES = (
    'arrangement', 'channels', 'device', 'general', 'launchMapPages', 'midi', 'mixer',
    'patterns', 'playlist', 'plugins', 'screen', 'transport', 'ui', 'utils',
)


def find_stub_files():
    """Returns a list of filenames in this script's folder that shadow FL Studio built-ins."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    found = []
    for name in _FL_BUILTIN_MODULES:
        if os.path.isfile(os.path.join(script_dir, name + '.py')):
            found.append(name + '.py')
    return found


def check_for_stubs():
    """Prints a loud warning to FL's script output if stub files are present. Returns True if the
    folder is clean, False if stubs were found."""
    stubs = find_stub_files()
    if not stubs:
        return True
    print('=' * 70)
    print('!! CRITICAL: fake FL Studio modules found in the script folder !!')
    print('')
    print('These files shadow FL Studio\'s real built-in modules, so the script is')
    print('talking to dummy stand-ins instead of FL Studio. Nothing will work correctly')
    print('until they are deleted:')
    print('')
    for name in stubs:
        print('    %s' % name)
    print('')
    print('Delete them from the script folder, then reload the script')
    print('(FL Studio: MIDI Settings -> click the refresh/reload icon).')
    print('=' * 70)
    return False
