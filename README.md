<<<<<<< HEAD
# FL Studio Arturia KeyLab Essential — Navigation & Auto-Mapping Fork

> A fork of [rjuang/flstudio-arturia-keylab-mk2](https://github.com/rjuang/flstudio-arturia-keylab-mk2),
> extended with contextual window navigation, FLEX pack-browser handling, a dedicated
> mixer-master / VST-channel-volume control scheme, and a heuristic auto-mapping system for
> unmapped VST parameters.

This is **not** the original project. If you just want the well-established, widely-used base
script for Arturia KeyLab (mkII or Essential) in FL Studio, start with
[rjuang's repository](https://github.com/rjuang/flstudio-arturia-keylab-mk2) — it has a larger
user base, an active discussion thread, and a track record this fork doesn't have yet. Come here
if you specifically want the features described below and are comfortable with a newer,
less-tested codebase.

---

## Credit where it's due

All of the original architecture — the MIDI event dispatcher, the paged LCD display system, the
mixer/channel-rack/playlist integration, the drum pad recorder, the scheduler that works around FL
Studio's lack of real threading, and the core control mapping for the KeyLab hardware — is
[**Ray Juang's**](https://github.com/rjuang) work. This fork would not exist without it. If
you find this useful, the original project (and its
[Discord](https://discord.gg/aqA8rnnTFp) / [discussion thread](https://forum.image-line.com/viewtopic.php?f=1994&t=243170))
deserves your first stop, your stars, and your thanks.

## Built with AI assistance

Substantial parts of this fork — the new navigation logic, the FLEX-specific handling, the
auto-mapping system, and various bug fixes to the original codebase — were built through
extended, iterative collaboration with an AI coding assistant (Claude, Anthropic), directed and
tested by a human throughout. This is disclosed plainly because it's relevant to how much you
should trust any given piece of this code: the AI did not have access to a running FL Studio
instance to verify its own output. Everything here has been tested only as thoroughly as the
maintainer's own real-world use has exercised it — see [Known Issues & Limitations](docs/KNOWN_ISSUES.md)
for an honest accounting of what that does and doesn't cover.

## No warranty, no liability

This software is provided **as-is**, with no guarantee it will work correctly, safely, or at all
on your system. By using it, you accept that:

- The maintainer(s) are **not responsible** for any data loss, project corruption, crashes, or
  other issues arising from using this script.
- This script writes a small amount of persistent state into your FL Studio project file itself
  (encoded into the name of your last mixer track — see [Persistence & Side Effects](docs/KNOWN_ISSUES.md#persistence)).
  Back up your projects as you normally would.
- This is a community project maintained on a best-effort basis, not a commercial product with
  support guarantees.

See the [LICENSE](LICENSE) (MIT) for the full legal terms.

---

## What's different from upstream

This fork adds, on top of everything in rjuang's original:

- **Contextual window navigation** — a long-press of the navigation encoder opens a window
  selector (Browser, Plugin, Mixer, Channel Rack, Playlist, Piano Roll); once selected, the
  encoder and nav arrows behave differently depending on which window is targeted, instead of one
  fixed behavior for all of them.
- **FLEX-aware browsing** — encoder scroll and Enter drive FLEX's own preset list correctly
  (works best with FLEX's "flatten all packs" display mode).
- **A dedicated master/VST-volume control scheme** — encoder 9 always controls the current
  channel's own volume (distinct from any plugin's internal parameters); fader 9 always controls
  the mixer master, in every mode, never forwarded to a plugin as a generic CC.
- **A heuristic auto-mapper** for plugins with no hand-curated entry in `arturia_native_plugins.py`
  — scans a newly-selected plugin's exposed parameters, filters out inactive/structural ones,
  ranks the rest by a synthesis-performance priority hierarchy, and maps the results onto the
  physical knobs/sliders. Runs on a debounced settle timer so it doesn't remap mid-scroll while
  browsing presets, and scans in small chunks across multiple idle ticks so a large plugin can't
  block controller responsiveness. Two modes (fixed hardware-label slots, or fully dynamic
  ranking), toggleable live with a long CATEGORY press, persisted per-project. See
  [docs/AUTO_MAPPER.md](docs/AUTO_MAPPER.md).
- **A GUI-coherence watchdog** — FL Studio's scripting engine has no true threading and no direct
  way to detect a GUI stall; this fork infers one from irregular idle-tick spacing and resynchronizes
  script state (cancelling stale timers, dropping stuck navigation modes) when it happens, rather
  than silently trusting state that may have gone stale during a freeze.
- Assorted correctness fixes to the original codebase (an escape/enter path that wasn't reaching
  its full fallback chain, a scheduler that could crash the whole idle loop on one bad task, a
  timing bug where the auto-mapper's own scan time could be misattributed as an external freeze).

Full technical changelog: [CHANGELOG.md](CHANGELOG.md).

---

## Supported devices & software

| | This fork |
|---|---|
| **Hardware tested on** | Arturia KeyLab Essential 61 mk2 |
| **Hardware likely compatible, untested** | Arturia KeyLab mkII (same underlying script family) |
| **FL Studio tested on** | 2026 (build 26.1.6) |
| **OS tested on** | Windows |
| **OS partially supported** | macOS — the FLEX/plugin keystroke-emulation path (`ctypes` `SendInput`) is Windows-only by construction; on Mac it silently falls back to FL's native API calls, which is weaker but shouldn't error |
| **Python** | Whatever FL Studio 2026 embeds (3.12.1 at time of writing) |

If you're running something outside this table, it may well work — the base project supports a
wide range of configurations — but nothing here has been verified against it. Please report back
(see [Contributing](CONTRIBUTING.md)) so this table can grow.

---

## Installation

1. Clone or download this repository into:
   ```
   Documents/Image-Line/FL Studio/Settings/Hardware/
   ```
   Make sure the scripts end up in their own subfolder inside `Hardware/` — FL Studio ignores
   files placed directly in `Hardware/` itself.
2. In FL Studio, go to `Options -> MIDI Settings` and select your Arturia device (the **DAW** port)
   under **Input**. Choose this project's script (`Arturia Keylab mkII DAW (MIDIIN2/MIDIOUT2) NAV`)
   from the **Controller type** dropdown, not "(generic controller)".
3. Set your keyboard to **DAW mode** (not User or Analog Lab mode) on the hardware itself.
4. Optional: the second port (`Arturia Keylab mkII (MIDI) NAV`) enables Analog Lab / drum pad
   support — set it up the same way if you use those features.

For the full walkthrough with port-configuration screenshots (Arturia's own port-setup guide is
still accurate for this fork — the port names differ slightly but the process is identical):
[docs/INSTALL.md](docs/INSTALL.md).

**Visual aids & tutorials:** rjuang's original videos (linked in his repository) still cover the
base navigation, mixer, and Analog Lab features accurately, since this fork builds on top of that
without changing them. Fork-specific features (auto-mapper, FLEX pack browsing, window
navigation) don't have their own tutorial video/PDF yet — see
[docs/INSTALL.md](docs/INSTALL.md) for text-based setup steps in the meantime, and
[Contributing](CONTRIBUTING.md) if you'd like to help produce one.

---

## Configuration

Most day-to-day settings live in `config.py` — auto-mapper mode and settle time, the plugin
exclusion list, debug logging. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for what each
setting does and which are safe to change without understanding the code.

---

## Known Issues & Limitations

Read before reporting a bug — it might already be a known, open issue:
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).

---

## Feedback & Contributing

Bug reports, feature requests, and pull requests are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) first — in particular the bug report template, since precise
diagnostic detail (FL Studio version, OS, the exact plugin involved, and steps to reproduce) is
what actually gets issues fixed here, as opposed to vague reports that can't be reproduced.

## License

[MIT](LICENSE) — inherited from the original project, with the same permissions and the same "as
is, no warranty" terms.
=======
# MIDI Script for Arturia Keylab 49/61/88 (Essential or mkII)

## Overview
The goal of this MIDI Script is to make Arturia Keylab (mkII or Essential) more friendlier to use with FL Studio. The script was recently ported to work with Essential keyboards (so it is safe to ignore the mkII naming).

## Really old demo (refer to the feature videos below for updated results)
[![](http://img.youtube.com/vi/Ts2SnW9r2fc/0.jpg)](http://www.youtube.com/watch?v=Ts2SnW9r2fc "Old Demo of Script")

Refer to this [playlist](https://youtube.com/playlist?list=PLet-RTUimaMTyzOR9OvTb7-DQWe5RmWY8) for the latest content covering different features of the midiscript functionality in shorter videos.


## Discussion Thread
There is a discussion thread you can provide feedback or ask questions at [here](https://forum.image-line.com/viewtopic.php?f=1994&t=243170)

## Discord Server
I can also be reached via [Discord](https://discord.gg/aqA8rnnTFp)


## Setting Up
Video link describing setup below:

### Windows Setup Video ###
[![](http://img.youtube.com/vi/KUNfQjWnZwc/0.jpg)](http://www.youtube.com/watch?v=KUNfQjWnZwc "Setup instructions for Windows users")

### Mac Setup Video ###
[![](http://img.youtube.com/vi/woxzfQc238s/0.jpg)](http://www.youtube.com/watch?v=woxzfQc238s "Setup instructions for Mac users")

You can simply clone this project into the folder:
``` 
Documents/Image-Line/FL Studio/Settings/Hardware/
```
Then in FL Studio, goto `Options->Midi Settings` and select your Arturia device (the DAW one) under
`Input` section.

IMPORTANT: Make sure the scripts are in a subfolder within the Hardware folder. Otherwise, FL Studio will ignore the
files.

### For Macs ###

Follow the tips and instructions [here](https://support.arturia.com/hc/en-us/articles/4405748362002-KeyLab-MkII-Tips-Tricks) for setting
up the ports correctly.  Scroll down to "FL Studio" section at the very bottom of the link.

In the instructions, instead of selecting "Mackie Control Universal" select my script
`Arturia Keylab mkII DAW (MIDIIN2/MIDIOUT2)` under the scripts column.

Note that there will be another script called `Arturia Keylab mkII (MIDI)`. This is an optional script for enabling
Analog Lab. You can set `Keylab mkII XX MIDI` to this script. 

## For Windows ##
Follow the tips and instructions [here](https://support.arturia.com/hc/en-us/articles/4405741358738-KeyLab-Essential-Tips-Tricks) for
setting up the ports correctly. These are instructions for Keylab essential but the setup is the same as Keylab mkII.
I reference this one because it has a screenshot from a Windows setup.

In the instructions, instead of selecting "Mackie Control Universal" select my script
`Arturia Keylab mkII DAW (MIDIIN2/MIDIOUT2)` under the scripts column.

Note that there will be another script called `Arturia Keylab mkII (MIDI)`. This is an optional script for enabling
Analog Lab. You can set `Arturia Keylab mkII` device to this script. 

## IMPORTANT ##
When using your keyboard, make sure that you set it to use the DAW mode (i.e., the DAW button is selected as opposed to
the User or Analog Lab buttons).

If you would like to use Analog Lab plugins and control it with the "Analog Lab" mode button, you can use the optional
script provided here. FL Studio 20.8 also provides a native script to do this, but it has a known issue where by 
sustain pedal notes will be suppressed. Using either script, you'll still need to configure Analog Lab plugin's MIDI In
port to 10. This needs to be done for each plugin that is to be controlled with Analog Lab mode.
TODO: Add video explaining this. Refer to this [link](https://forum.image-line.com/viewtopic.php?f=100&t=245527&p=1569738#p1566027)

## Features

### Navigation Panel and Controls ###

[![](http://img.youtube.com/vi/4YrnS2aaSkw/0.jpg)](http://www.youtube.com/watch?v=4YrnS2aaSkw "LCD Display and Navigation")

### Mixer Panel and Controls ###

[![](http://img.youtube.com/vi/BjKG9kKLDo0/0.jpg)](http://www.youtube.com/watch?v=BjKG9kKLDo0 "Mixer Panel and Controls")

### Controlling Arturia Plugins with Analog Lab ###

[![](http://img.youtube.com/vi/QtMN1y-Kf_w/0.jpg)](http://www.youtube.com/watch?v=QtMN1y-Kf_w "Analog Lab Mode")

### Controlling Other Plugins and Learning Midi Assignments ###

[![](http://img.youtube.com/vi/4nkRHf5kwT8/0.jpg)](http://www.youtube.com/watch?v=4nkRHf5kwT8 "Controlling plugins")

### Remapping the Pads ###

[![](http://img.youtube.com/vi/wiynzuc7Vqg/0.jpg)](http://www.youtube.com/watch?v=wiynzuc7Vqg "Remapping Pad Buttons")

### DAW controls and Transports ###

[![](http://img.youtube.com/vi/hSm6koiTwVA/0.jpg)](http://www.youtube.com/watch?v=hSm6koiTwVA "DAW controls and transports")

>>>>>>> 28c38f7e1071f92d7b350077ef5720f67257b245
