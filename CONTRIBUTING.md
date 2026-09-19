# Contributing

This is a hardware-and-host integration project. Small, precise reports are more useful than broad
descriptions such as "the buttons stopped working".

## Before reporting

1. Confirm the script is deployed to its own folder below FL Studio's `Hardware` directory.
2. Confirm the controller is using the DAW port and is in DAW mode.
3. Reload the MIDI script from FL Studio's MIDI Settings.
4. Check [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).
5. Reproduce with a new or disposable project when the behavior could alter project state.

Do not copy `.venv`, development configuration, API stubs, `__pycache__`, or local scan exports to
the FL Studio deployment folder. The deploy script is the supported way to copy runtime files.

## Bug reports

Include:

- FL Studio version and build;
- Windows or macOS version;
- controller model and whether it is Essential or MKII;
- DAW/User/Analog Lab mode;
- the active FL Studio window;
- the selected channel, plugin, preset, and VST version where relevant;
- the exact hardware control and whether it was pressed, released, turned, or held;
- expected and actual behavior;
- reproduction steps from a clean starting state;
- relevant output from FL Studio's script console with `AUTO_MAP_DEBUG = True` when mapping is
  involved.

Do not include private project files, plugin binaries, license data, MIDI device serial numbers, or
personal paths unless they are necessary to reproduce the issue.

## Mapping contributions

VST maps belong in `vst_maps/vst_default_maps.json`. Prefer parameter names reported by the scan
export over guessed names. Keep entries narrowly scoped to the plugin and preserve `null` slots when
the normal fallback should remain active.

For a mapping issue, attach the relevant sanitized scan JSON and explain which physical control
should drive which parameter. Avoid committing large scan collections unless they are intentionally
part of a curated map change.

## Development setup

Use the project-local environment:

```powershell
.\setup-dev.ps1
```

Select `.venv` as the VS Code interpreter. The FL Studio API package supplies development-time
types and documentation; FL Studio itself remains the only real runtime for host APIs.

The setup script also configures Git to use `.githooks`. The pre-commit hook runs
`bump_version.ps1`, advances `version.py`'s `CHANGE_DATE` monotonically, and stages that file
automatically. Do not bypass the hook unless you intentionally want to preserve the current build
number.

Before submitting a change:

```powershell
.venv\Scripts\python.exe -m py_compile *.py
```

Also run the narrowest available check for the behavior changed. Hardware and FL Studio behavior
still require manual verification in the DAW.

## Pull requests

Keep changes focused. Explain the user-visible behavior, the control or API path changed, and how
you tested it. Update the relevant documentation when a control mapping, configuration option, or
known limitation changes.
