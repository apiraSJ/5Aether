"""Debug boot_profiler identity."""
import sys

import aether.core.boot_profiler as bp_mod
bp_id = id(bp_mod.boot_profiler)
print(f"Module-level bp id: {bp_id}")

from aether.core import application as app_mod
app_bp = getattr(app_mod, "boot_profiler", "NOT_FOUND")
if app_bp != "NOT_FOUND":
    print(f"app module boot_profiler id: {id(app_bp)}")
    print(f"Same? {id(app_bp) == bp_id}")

fn = app_mod.AetherApp.boot
bp_in_globals = fn.__globals__.get("boot_profiler", "NOT_FOUND")
if bp_in_globals != "NOT_FOUND":
    print(f"boot() globals boot_profiler id: {id(bp_in_globals)}")
    print(f"Same as module-level? {id(bp_in_globals) == bp_id}")

# Now mark on the module-level and see
bp_mod.boot_profiler.mark("test")
print(f"After test mark, module-level marks: {len(bp_mod.boot_profiler._marks)}")
if bp_in_globals != "NOT_FOUND":
    print(f"Globals instance marks: {len(bp_in_globals._marks)}")
