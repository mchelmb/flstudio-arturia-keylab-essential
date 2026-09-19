# Installation

## Requirements

- FL Studio 20.7 or newer with MIDI Controller Scripting support;
- an Arturia KeyLab Essential 61 or compatible KeyLab controller;
- the controller's DAW MIDI port;
- Windows for the strongest FLEX/plugin keyboard-navigation behavior.

The project is currently tested on FL Studio 2026 on Windows with the original KeyLab Essential
61. MKII support is likely because the script retains the upstream MKII event model, but it is less
well tested. The original Essential 61 has a firmware limitation that makes Encoder 9 unavailable
in DAW Mode.

## Deploy the script

1. Place the repository somewhere convenient for development.
2. Run `deploy.ps1` from PowerShell:

   ```powershell
   .\deploy.ps1
   ```

   The default destination is:

   ```text
   Documents/Image-Line/FL Studio/Settings/Hardware/flstudio-arturia-keylab-essential-nav
   ```

   A different destination can be supplied with `-Destination`.
3. In FL Studio, open `Options -> MIDI Settings`.
4. Select the Arturia DAW input port.
5. Choose `Arturia Keylab mkII DAW (MIDIIN2/MIDIOUT2) NAV` as the controller type.
6. Set the hardware to DAW mode.
7. Refresh or reload the MIDI script from MIDI Settings.

The optional second controller entry, `Arturia Keylab mkII (MIDI) NAV`, is for the ordinary MIDI
port and pad/Analog Lab support. Configure it only if those features are needed.

## Development environment

The development environment is separate from the FL Studio runtime:

```powershell
.\setup-dev.ps1
```

This creates `.venv` with Python 3.12 and the pinned FL Studio API stubs. The environment, stubs,
Pyright configuration, and scan exports are not deployed. See [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md).

## First verification

After reload:

1. Confirm the LCD welcome page appears.
2. Turn the navigation encoder and verify the expected focused-window behavior.
3. In the Channel Rack, verify the first three top encoders control volume, pan, and target mixer
   track when contextual controls are enabled.
4. Focus a plugin and wait for auto-mapping to settle before testing mapped controls.
5. Use LIVE/BANK or the available Part controls to move through VST parameter banks.
6. Test recording only after saving the project, because project-persisted auto-map state is stored
   in mixer-track metadata.

## Troubleshooting

- If controls do nothing, confirm the DAW port and controller type rather than Generic Controller.
- If Encoder 9 does nothing on an Essential 61, this is expected firmware behavior.
- If a plugin map is wrong, enable `AUTO_MAP_DEBUG`, reproduce after the settle delay, and inspect
  the exported scan in `vst_param_scans`.
- If FLEX navigation is weak on macOS, use its native fallback or test on Windows.
- If a reload behaves strangely, run the deploy script again and refresh the controller script.
