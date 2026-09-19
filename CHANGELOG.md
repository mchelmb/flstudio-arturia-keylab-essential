# Changelog

This project is a focused fork of the Arturia KeyLab MIDI script originally developed by Ray
Juang. Dates below reflect repository history and describe the major behavior changes, not every
upstream change.

## Current development line

- Added a project-local Python 3.12 development environment with the FL Studio API stub package.
- Added Pyright/Pylance configuration for the local environment without placing host-module files
  in the deployable script directory.
- Added explicit deployment protection against copying files that could shadow FL Studio built-in
  modules.
- Added GUI-coherence watchdog behavior to recover stale navigation and modifier state after long
  FL Studio idle gaps.
- Added latency gating for expensive auto-mapper discovery and scan export while recording, with
  optional strict playback gating.
- Added contextual Channel Rack controls for the first three top encoders: volume, panning, and
  target mixer track.
- Added a hierarchical menu implementation and integration path for deliberate Channel, Window,
  Pattern, and Plugin actions.

## 2026-09-18

- Added curated parameter maps for additional VST plugins in `vst_maps`.
- Expanded documentation for auto-mapping, persistence, limitations, and development setup.

## 2026-09-16

- Treated the original Essential LIVE/BANK control as one momentary DAW-mode control.
- Mapped LIVE/BANK and Live Part controls to forward/backward VST parameter-bank navigation.
- Added sixteen VST parameter banks, with bank 0 using the curated or normal auto-map and later
  banks exposing the remaining ranked parameters.
- Added the project-persisted PRESET long-press toggle for the VST Encoder 8 volume override.

## 2026-09-15

- Removed runtime reliance on Encoder 9 in DAW Mode after confirming the original KeyLab Essential
  61 firmware does not emit a usable DAW-mode message for that encoder.
- Added the Encoder 9 limitation and User Mode tradeoff to the documentation.
- Added utility and setup work supporting color conversion, project persistence, and local API
  analysis.
- Added development FL Studio API stubs and dependency configuration for static analysis.

## Auto-mapper line

- Added the debounced, chunked VST parameter scanner.
- Added name/value-based gating for structural parameters, inactive modules, zero effect mixes, and
  engaged bypass controls.
- Added ranked fallback mapping with fixed hardware slots and dynamic ranked modes.
- Added `SAVED_ONLY` mode for strict JSON-controlled mappings.
- Added per-VST JSON maps with case-insensitive parameter-name resolution.
- Added raw scan export to `vst_param_scans` for later map curation.

## Upstream foundation

The project retains the original architecture for MIDI event dispatch, LCD paging, mixer and
Channel Rack integration, playlist and piano-roll control, pad recording, scheduler behavior, and
Arturia LED handling from the upstream KeyLab script.

## Status

The script is maintained as a personal, hardware-tested fork. It has been exercised with the
Arturia KeyLab Essential 61 and FL Studio 2026 on Windows. It does not have a complete automated
FL Studio integration test suite; see [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).
