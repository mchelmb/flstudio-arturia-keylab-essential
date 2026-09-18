# KeyLab Essential – Unified Menu + Latency Gates

## Outcome

You now have:

1. **A single hierarchical menu** driven by the central encoder + Left/Right  
   (Windows → Channel → Pattern → Plugin).  
   Long-press the encoder to open it; long-press again (or Left at top level) to leave.

2. **Latency isolation while recording**  
   VST parameter discovery, scan export and other heavy idle work are suppressed the moment transport goes into record. Notes and transport stay responsive.

3. **Unification path**  
   The old cyclic `NavigationMode` and the separate window-select/nav modal become ordinary menu nodes. You can delete them once the menu feels right.

## Files added / changed

| File | Role |
|------|------|
| `arturia_menu.py` | `LatencyGate`, `MenuNode`, `MenuState`, `MenuSystem` |
| `arturia_menu_tree.py` | Concrete tree (callbacks close over the processor) |
| `arturia_auto_mapper.py` | Gated: no new discovery / no disk export while critical |
| `docs/MENU_SYSTEM.md` | Full design notes |
| `INTEGRATION_PROCESSOR.md` | Exact copy-paste wiring for `arturia_processor.py` |
| `MENU_README.md` | This file |

## How to use (30-second version)

1. Copy the two new modules into your script folder.
2. Follow `INTEGRATION_PROCESSOR.md` (imports → construct menu → wrap the five navigation handlers → feed record state into the gate → OnIdle).
3. Reload the script in FL Studio.
4. Long-press the central encoder → you should see the top-level menu on the LCD.

## Interaction cheat-sheet

| Action | Result |
|--------|--------|
| Long-press encoder (live) | Open menu |
| Encoder turn | Move selection **or** change leaf value |
| Encoder press / Right | Enter node / confirm |
| Left / long-press (in menu) | Back one level or exit |
| Record armed | Heavy background work stops |

## Cheap iteration tip

The menu is pure Python state + callbacks.  
You can rearrange, rename or prune nodes in `arturia_menu_tree.py` without touching the processor or the auto-mapper. That is the inexpensive way to experiment with the UX.

Once the tree is stable, remove the legacy dual navigation paths and you are done.
"""
)
