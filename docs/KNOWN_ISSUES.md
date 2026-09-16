# Known Issues & Limitations

Last updated alongside the current codebase. If you hit something not listed here, see
[CONTRIBUTING.md](../CONTRIBUTING.md) for how to file a report that's actually actionable.

## Open, unconfirmed

### Selecting an effect from the Browser sometimes closes the previously-focused plugin editor
Reported behavior: with a plugin editor open and focused, clicking into the Browser (by mouse or
via the controller) and selecting a new effect/VST closes the previously-focused editor instead of
showing FL's normal "add to rack" flow.

**Status:** Not confirmed as a script bug. This also reproduces via pure mouse interaction with no
controller/script state involved at that moment, which points toward either a native FL Studio
setting (leading candidate: Options -> "Plugin windows are shown one at a time", which auto-closes
the previous editor whenever a new one opens) or something in this script's background idle-tick
work interfering with FL's transient UI state. As a precaution, the auto-mapper's background
parameter scanning now pauses entirely while the Browser has focus, removing it as a possible
factor — but this has not been confirmed to fix the underlying issue, only to rule out one
candidate cause.

**If you can reproduce this:** the single most useful thing you can do is test with the MIDI
script fully disabled (FL Studio -> MIDI Settings -> disable/uncheck the controller) using pure
mouse interaction. If it still happens with the script off, it's a native FL Studio behavior, not
this project. If it stops, that's a concrete before/after to build a fix from.

## Known limitations (working as intended, not bugs)

### Original KeyLab Essential 61: Encoder 9 is unavailable in DAW Mode
The original, pre-MK3 KeyLab Essential 61 firmware does not emit a DAW-mode message for Encoder
9. The control can be assigned in User Mode as an ordinary MIDI control, but the DAW/User split
means the navigation encoder and side controls cannot be retained reliably at the same time.
The combined User-mode/DAW-mode workaround is therefore a dead end for this hardware, and the
project intentionally leaves Encoder 9 disabled.

Per-VST/plugin volume control is not implemented through Encoder 9. A dedicated Encoder 8
override is planned for the next release.

### FLEX's Tags/category filter panel is not automatable
FLEX's internal tag-filter dropdown (opened by clicking "Tags" near its search box) appears to be
mouse-only — no keyboard shortcut for it has been found in official documentation, community
guides, or by testing. The CATEGORY button currently sends the same input as the Right nav arrow
(advance through FLEX's pack list) rather than opening the tags panel. If you discover a working
keyboard shortcut for it, please open an issue.

### The auto-mapper's activity-gating heuristics only work on conventionally-named plugins
There is no structural/dependency metadata available from FL's scripting API — no way to know
"this parameter belongs to oscillator 2" except by guessing from parameter names and values. The
auto-mapper infers module relationships (e.g. "this parameter is subordinate to that disabled
oscillator") from naming patterns like `<Module> On`, `<Module> Bypass`, `<Module> Mix`. Plugins
that don't follow a name-per-module convention will simply not benefit from that gating — their
parameters will still get gated on the two hard-coded checks (empty names, structural/MIDI-CC-like
names) and ranked normally, just without the module-activity awareness.

### Auto-mapper testing coverage is limited
The gate/rank pipeline has been unit-tested against synthetic parameter lists designed to exercise
specific behaviors (tier ranking, deprioritization, hard-exclusion cases), and against a small
number of real plugins in actual use. It has **not** been run against a broad range of real
third-party VSTs with varied naming conventions. Expect rough edges; please report specific
plugins that map poorly, ideally with the plugin name and (if `AUTO_MAP_DEBUG = True`) the debug
log output showing what it discovered.

### Switching plugins mid-scan
If you switch to a different channel/plugin while the auto-mapper is mid-scan (rare — scans
usually complete within a tick or two for typical plugins), the in-progress scan finishes and
commits its result before the newly-selected plugin's own scan begins. Low-impact (the stale
result just gets overwritten the next time that channel is revisited) but not instantaneous.

### Windows-only keystroke emulation
The `ctypes`/`SendInput` path used to drive FLEX's own keyboard navigation is Windows API-specific.
On macOS it will silently fail to import and the affected features (FLEX pack/preset navigation
via encoder) fall back to FL's more limited native `ui.next()`/`ui.previous()` calls instead.

## Fixed, but not independently re-verified after the fix

These had a specific, understood root cause and a targeted fix, but the fix itself hasn't been
confirmed against the original symptom by a second independent test:

- A scheduler crash vector (unhandled exceptions in queued tasks, especially after a long
  idle gap such as alt-tabbing away from FL Studio for a while) — fixed by wrapping task execution
  in the scheduler's idle loop. Plausible cause of at least one reported crash, not confirmed via a
  crash log.
- Enter/select not working in the Browser during contextual navigation — traced to the
  auto-mapper's parameter scan time being misattributed as an external FL Studio freeze, which
  triggered an unrelated state-reset. Fixed by correcting how idle-tick timing is measured.

<a id="persistence"></a>
## Persistence & side effects

This project stores a small amount of state (currently: which auto-mapper mode you last selected)
**inside your FL Studio project file**, encoded into the name of the last mixer track. This reuses
a mechanism the original project already used for drum-pad pattern data. If you stop using this
script and want to remove the stored data, delete the encoded text (it starts with
`DO NOT EDIT:SAVEDATA|`) from that track's name.
