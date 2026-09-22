# UI-2 Plan: Global Hotkey

## Scope (locked)

```
Ctrl+Alt+Space
      ↓
Win32 RegisterHotKey (ctypes)
      ↓
GUIPlugin._poll_hotkey()
      ↓
GUIPlugin.toggle_ui()
      ↓
UIShell.toggle()
```

**Not in scope:** system tray, window −/×, Alt+F4, persistence, shutdown changes, UI redesign, panel changes.

## Architecture Decision

Hotkey lives in **GUIPlugin**, NOT UIShell.

- GUIPlugin = lifecycle/input integration layer
- UIShell = window visibility only
- Config `gui.hotkey_toggle` is already defined but unwired
- Scope is minimal (1 hotkey) — no need for separate plugin

## Files Modified

| File | Changes |
|------|---------|
| `aether/plugins/gui_plugin.py` | +~60 lines: hotkey parse, register, poll, unregister |
| `tests/test_ui_lifecycle.py` | +~90 lines: 12 tests in 3 new classes |

**No changes to:** UIShell, Application, config/default.yaml, any other file.

## Implementation Detail

### 1. Constants & Parsing (top of gui_plugin.py)

```python
# Win32 hotkey constants (stdlib ctypes — no new dependencies)
_HOTKEY_ID = 1
_MOD_MAP = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004}
_VK_MAP  = {"space": 0x20, "spacebar": 0x20}

def _parse_hotkey(combo: str) -> tuple[int, int]:
    """'ctrl+alt+space' → (MOD_CONTROL|MOD_ALT, VK_SPACE)"""
```

### 2. Register in `GUIPlugin.start()` (after UIShell.build)

```python
if sys.platform == "win32":
    combo = self._context.config.get("gui.hotkey_toggle", "")
    if combo:
        mod, vk = _parse_hotkey(combo)
        self._register_hotkey(mod, vk)  # ctypes.windll.user32.RegisterHotKey(NULL, 1, mod, vk)
```

### 3. Poll in `GUIPlugin.update()` (after shell.update)

```python
if sys.platform == "win32":
    self._poll_hotkey()  # PeekMessage → if WM_HOTKEY → self.toggle_ui()
```

### 4. Unregister in `GUIPlugin.stop()` (before shell.shutdown)

```python
if self._hotkey_registered:
    self._unregister_hotkey()  # ctypes.windll.user32.UnregisterHotKey(NULL, 1)
```

## Tests (12 tests)

```python
class TestHotkeyComboParser:
    """Parse combo string → (modifiers, vk)."""
    test_ctrl_alt_space        # "ctrl+alt+space" → (6, 0x20)
    test_ctrl_space            # "ctrl+space" → (2, 0x20)
    test_alt_shift_a           # "alt+shift+a" → (5, 0x41)
    test_case_insensitive      # "Ctrl+Alt+Space" same as above
    test_unknown_key_raises    # "ctrl+bogus" → ValueError

class TestHotkeyRegistration:
    """Register/unregister lifecycle (platform-guarded)."""
    test_register_called       # start() calls RegisterHotKey
    test_unregister_called     # stop() calls UnregisterHotKey
    test_no_hotkey_if_disabled # config missing → no RegisterHotKey

class TestHotkeyDispatch:
    """WM_HOTKEY → toggle_ui()."""
    test_hotkey_toggles        # mock PeekMessage WM_HOTKEY → toggle_ui called
    test_no_hotkey_no_toggle   # mock PeekMessage empty → no toggle
```

All platform-guarded with `@pytest.mark.skipif(sys.platform != "win32", ...)` for ctypes tests, pure logic tests (parser) run on all platforms.

## Commit

```
feat: add UI-2 global hotkey
```

## Tick Order (unchanged)

```
Application.tick()
  → command_bus.update()
  → services.update(dt)
  → GUIPlugin.update(dt)
      → shell.update()          # existing
      → _poll_hotkey()          # NEW
  → event_bus.flush()
```
