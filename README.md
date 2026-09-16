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
- **A dedicated mixer-master control** — fader 9 controls the mixer master and is never forwarded
  to a plugin as a generic CC. On the original KeyLab Essential 61, Encoder 9 is physically
  present but does not transmit in DAW Mode because of a firmware limitation; no reliable
  User-mode/DAW-mode workaround is available. Per-VST/plugin volume control is planned as an
  Encoder 8 override for the next release.
- **A heuristic auto-mapper** for plugins with no hand-curated entry in `arturia_native_plugins.py`
  — scans a newly-selected plugin's exposed parameters, filters out inactive/structural ones,
  ranks the rest by a synthesis-performance priority hierarchy, and maps the results onto the
  physical knobs/sliders. A middle layer, `vst_maps/vst_default_maps.json`, lets you (or your own
  external tooling) define per-VST default maps by parameter name in plain JSON, checked before
  the heuristic fallback — every scan is also auto-exported to `vst_param_scans/` as raw material
  for building these. Runs on a debounced settle timer so it doesn't remap mid-scroll while
  browsing presets, and scans in small chunks across multiple idle ticks so a large plugin can't
  block controller responsiveness. Two fallback modes (fixed hardware-label slots, or fully
  dynamic ranking), toggleable live with a long CATEGORY press, persisted per-project. See
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

### Original KeyLab Essential 61: Encoder 9 is unavailable in DAW Mode

The original, pre-MK3 KeyLab Essential 61 firmware does not emit a DAW-mode message for Encoder
9. User Mode can expose ordinary MIDI assignments, but switching between DAW Mode and User Mode
does not provide a reliable way to preserve the navigation controls and recover Encoder 9 at the
same time. The workaround is therefore considered infeasible and Encoder 9 support is disabled.

Long-pressing the PRESET button toggles a project-persisted Encoder 8 volume override. When enabled,
Encoder 8 is hard-mapped to the volume parameter discovered in that VST's own exposed parameter
list; long-press again to disable it. Because parameter indices and names vary by VST, the
auto-mapper searches for the volume parameter during its scan.

In Channel Plugin mode, the LIVE/BANK controls cycle through 16 parameter banks. Bank 0 uses the
curated/native mapping and the normal auto-mapper; banks 1-15 expose the remaining ranked VST
parameters as eight knobs plus eight faders per bank. Native-plugin hard maps apply to bank 0;
the additional banks are populated from the VST's scanned parameter list.
On the original Essential, the single LIVE/BANK button is a momentary trigger in DAW mode and
advances the bank counter. Its LED is not used as a latched mode indicator. The MKII retains
separate forward/backward Live Part controls.

---

## Feedback & Contributing

Bug reports, feature requests, and pull requests are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) first — in particular the bug report template, since precise
diagnostic detail (FL Studio version, OS, the exact plugin involved, and steps to reproduce) is
what actually gets issues fixed here, as opposed to vague reports that can't be reproduced.

## License

[MIT](LICENSE) — inherited from the original project, with the same permissions and the same "as
is, no warranty" terms.
