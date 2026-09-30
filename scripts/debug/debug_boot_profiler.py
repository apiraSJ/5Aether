"""Debug script to trace boot profiler registration."""

from aether.app import AetherApp
import aether.core.boot_profiler as bp_mod

# Monkey-patch mark to see calls
orig_mark = bp_mod.BootProfiler.mark
def debug_mark(self, name):
    print(f"MARK('{name}') called, enabled={self._enabled}, marks_before={len(self._marks)}")
    return orig_mark(self, name)
bp_mod.BootProfiler.mark = debug_mark

orig_log = bp_mod.BootProfiler.log_summary
def debug_log(self):
    print(f"LOG_SUMMARY called, marks={len(self._marks)}")
    if self._marks:
        for m in self._marks:
            print(f"  {m.name}: {m.elapsed_ms:.1f}ms")
    return orig_log(self)
bp_mod.BootProfiler.log_summary = debug_log

app = AetherApp()
app.boot()

print(f"\nContainer has boot_profiler: {app.container.has('boot_profiler')}")
print(f"Known services: {app.container.registered_names()}")

# Also check the module-level boot_profiler instance
bp_instance = bp_mod.boot_profiler
print(f"\nModule-level boot_profiler marks: {len(bp_instance._marks)}")
for m in bp_instance._marks:
    print(f"  {m.name}: {m.elapsed_ms:.1f}ms")

app.shutdown()
