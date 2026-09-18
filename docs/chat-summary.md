# Conversation Summary: Arturia KeyLab Essential NAV Project

## Overview
This conversation documents the comprehensive development and cleanup of the Arturia KeyLab Essential NAV fork project. The work spans from September 16-17, 2026, and includes code modifications, documentation updates, Git history rewriting, and repository hygiene.

## Key Accomplishments

### 1. Encoder 9 Firmware Limitation Documentation
- **Problem**: The original KeyLab Essential 61 (pre-MK3) firmware does not emit DAW-mode messages for Encoder 9
- **Solution**: Removed all runtime usage of Encoder 9, removed ENCODER9 imports and mappings, and added a comprehensive addendum in docs/AUTO_MAPPER.md explaining the firmware limitation
- **LED behavior**: Encoder 9 handling was disabled in arturia_encoders.py (knob 8 now targets VST volume parameter instead)

### 2. Encoder 8 Per-VST Volume Override
- **Feature**: Long-press PRESET button toggles a project-persisted Encoder 8 volume override
- **Mechanism**: When enabled, Encoder 8 is hard-mapped to the VST's own exposed volume parameter (discovered during auto-mapper scan)
- **Fallback**: If no recognizable volume parameter is found, display reports "VST Volume: Not found"
- **Implementation**: 
  - arturia_auto_mapper.py: Added `find_volume_param()`, `GetVolumeParam()`, `_volume_params` tracking
  - arturia_encoders.py: `_process_plugin_volume_event()` uses `plugins.setParamValue()` with discovered parameter index
  - arturia_processor.py: `OnPresetLongPress()` toggles the override state
  - README.md and docs/KNOWN_ISSUES.md: Documented the feature

### 3. 16 VST Parameter Banks
- **Feature**: LIVE/BANK controls cycle through 16 parameter banks
- **Bank 0**: Curated/native mapping and normal auto-mapper behavior
- **Banks 1-15**: Remaining ranked VST parameters from the VST scan
- **Implementation**:
  - arturia_auto_mapper.py: `MAX_PARAMETER_BANKS = 16`, `_build_parameter_banks()`, `GetKnobParam()`/`GetSliderParam()` with `bank_index` parameter
  - arturia_encoders.py: Bank-aware `ProcessKnobInput()` and `GetKnobParam()`/`GetSliderParam()` calls
  - README.md and docs/KNOWN_ISSUES.md: Documented the 16-bank system

### 4. LIVE/BANK Button Correction
- **Problem**: The LIVE/BANK button was treated as two separate controls (46 and 47), causing unreliable bank cycling. Additionally, `ignore_release` was applied, which filtered out every other press because the button is a hardware toggle (alternates 127/0 as its own state, not as press/release pairs).
- **Solution**:
  - Essential hardware: Only control 47 is active (single button)
  - MKII hardware: Both controls 46 and 47 active (separate Live Part 1/2)
  - Toggle behavior: All events processed regardless of controlVal — every physical press advances/reverses the bank
  - LED behavior: `ID_BANK_TOGGLE` explicitly cleared in `_update_lights` (may not affect hardware-wired LEDs)
- **Implementation**:
  - arturia_processor.py: Conditional dispatcher (`if not arturia_leds.ESSENTIAL_KEYBOARD`)
  - README.md and docs/KNOWN_ISSUES.md: Documented the single-button behavior

### 5. Sampler Multi-Page Support
- **Feature**: Left/Right navigation cycles through curated multi-page maps for plugins
- **Implementation**:
  - vst_maps/vst_default_maps.json: Added `pages` array support with `_example_multi_page_sampler_TEMPLATE`
  - arturia_auto_mapper.py: `GetPageCount()`, `GetPageName()`, `CyclePage()`, `_active_page` tracking, `_last_scan_params` caching
  - docs/KNOWN_ISSUES.md: Documentation of the feature with caveats

### 6. Repository Hygiene
- **Removed**: `__pycache__/` directories, `nav.zip`, `codebase/` snapshot, `nav.zip` from git tracking
- **Added**: `.gitignore` rules for `.venv/`, `codebase/`, FL Studio stub modules
- **Mirror backup**: Created `C:\Work\Github\nav-history-backup.git`
- **Mailmap**: Corrected from `ResilThruTech` to `mchelmb`

### 7. Git History Rewrite
- **Purpose**: Remove stale `ResilThruTech (Pty) Ltd <basil@resilthrutech.com>` attribution from all commits
- **Method**: `git-filter-repo --mailmap mailmap.txt`
- **Result**: All 224 commits now bear `mchelmb <mchelmb@gmail.com>` as both author and committer
- **Remote push**: Force-pushed `main`, `main-nav`, and `main-nav-automapper` branches

### 8. Private Data Removal
- **Removed**: `ai-conversations/conversations.json` from all branch histories
- **Added**: `.gitignore` rules for `*.zip`, `*.7z`, `*.rar`, `*.tar`, `*.gz`, `*.bz2`, `*.xz`, `.venv/`, `codebase/`

## Files Modified

### Code Changes
- `arturia_auto_mapper.py`: Encoder 8 volume discovery, 16-bank system, volume parameter tracking
- `arturia_encoders.py`: Per-VST volume event handling, bank-aware knob/slider lookups
- `arturia_processor.py`: LIVE/BANK toggle (no ignore_release), bank cycling, LED reset
- `arturia_encoders.py`: Bank-aware knob/slider handling
- `arturia_macros.py`: No changes (kept existing structure)
- `arturia_midi.py`: No changes
- `arturia_leds.py`: No changes
- `arturia_midi.py`: No changes
- `arturia_native_plugins.py`: No changes
- `arturia_playlist.py`: No changes
- `arturia_scheduler.py`: No changes
- `arturia_metronome.py`: No changes
- `config.py`: No changes
- `device_arturia_keylab_mkii.py`: No changes
- `device_arturia_keylab_mkii_midi.py`: No changes

### Documentation Changes
- `README.md`: Encoder 9 limitation, Encoder 8 override, 16-bank system, LIVE/BANK behavior
- `docs/KNOWN_ISSUES.md`: Encoder 9 limitation, 16-bank system, LIVE/BANK behavior
- `docs/AUTO_MAPPER.md`: Encoder 9 addendum, 16-bank system documentation

### Deployment Files
- `deploy.ps1`: Included in the repository (was previously missing)
- `stub_guard.py`: Included in the repository (was previously missing)
- `vst_maps/vst_default_maps.json`: Updated with page support template
- `LICENSE`: Included (was previously missing)
- `.gitignore`: Comprehensive ignore rules

### Git History
- **Commits**: 224+ commits rewritten
- **Remote**: `origin/main-nav-automapper` at `610b926`
- **Local branch**: `main-nav-automapper` at `610b926`
- **Other branches**: `main`, `main-nav` also updated

### Private Data Removal
- `ai-conversations/conversations.json` removed from all branch histories
- Local backup at `C:\Work\Github\nav-private-cleanup-backup.git`

## Technical Details

### Encoder 8 Volume Discovery
- Uses `VOLUME_NAME_PRIORITY` list: `['master volume', 'output volume', 'main volume', 'volume', 'output level', 'level']`
- `find_volume_param(params)` searches each VST's scanned parameters
- Stores discovered parameter index in `_volume_params[channel_number]`
- Uses `plugins.setParamValue()` with the discovered index

### 16-Bank System
- Bank 0: Curated/native mapping + normal auto-mapper
- Banks 1-15: Remaining ranked parameters from VST scan
- Each bank: 8 knob assignments + 8 fader assignments
- Native hard maps apply only to bank 0
- `GetKnobParam(channel, index, bank_index)` and `GetSliderParam(channel, index, bank_index)`

### LIVE/BANK Button
- Essential: Control 47 only, toggle switch (alternating 127/0 values per press — NOT a press/release pair)
- MKII: Controls 46 and 47 active (separate Live Part 1/2)
- Both use `OnLivePart1`/`OnLivePart2` without `ignore_release` filter so every toggle-state change advances/reverses the bank
- Bank counter wraps through 16 positions
- Long-press Bank Next/Previous retain mode-toggle functions

### Sampler Multi-Page
- `vst_default_maps.json` `pages` array format
- `GetPageCount(plugin_name)` returns page count
- `GetPageName(channel_number, plugin_name)` returns current page name
- `CyclePage(channel_number, plugin_name, delta)` cycles pages using cached scan

## Verification
- No conflict markers in any files
- No stale `ResilThruTech` attribution
- No `__pycache__` files in tracked content
- No `conversations.json` in any branch
- No `.venv/` or `codebase/` in any branch
- No archives (`*.zip`, `*.7z`, etc.) in any branch
- Clean worktree

## Commit History
The final commit `610b926` "Add sampler pages and sixteen VST parameter banks" includes all the combined changes from the entire conversation session.

## Remote State
- `origin/main-nav-automapper`: `610b926`
- `origin/main`: `c8d90c1`
- `origin/main-nav`: `c8d90c1`
- No `origin/alternative-llm-logic` branch

## Local State
- Worktree is clean
- No untracked files that should be tracked
- `.gitignore` properly configured