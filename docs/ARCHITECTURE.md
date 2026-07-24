# Aether Architecture — Core Principles

## Single Source of Truth

This document is the binding contract. All code must conform. No exceptions.

---

## Five Rules

| Layer | Responsibility | Must Never |
|-------|----------------|------------|
| **Application** | Owns lifecycle: `boot()` → `tick(dt)` → `shutdown()` | Call domain logic directly |
| **Services** | Own domain logic: Memory, Reasoning, Context | Know about UI, plugins, or Application |
| **Plugins** | Produce Commands from input (keyboard, camera, XR) | Contain domain logic or call Services directly |
| **EventBus** | Transport events only — queue → flush per tick | Decide meaning, mutate state, store data |
| **UI** | Present state, send Commands | Talk to Services, Memory, or Reasoning directly |

---

## Data Flow (One Direction)

```
Input → Plugin → Command → CommandBus → Handler → Service → ResultPipeline → EventBus → UI
                    ↑                                              │
                    └────────────────── Event ────────────────────┘
```

- **Commands flow down** (intent)
- **Events flow up** (facts)
- **Application tick** coordinates the cycle — no domain logic inside

---

## Lifecycle Contract

```python
# Application (orchestrator only)
boot()          # once: config, DI, plugins, services
tick(dt)        # every frame: command_bus.update(), services.update(dt), plugins.update(dt), event_bus.flush()
shutdown()      # once: reverse order, flush, persist

# Service (domain logic)
start()         # once after boot
update(dt)      # every tick: process, decide, emit events
stop()          # once before shutdown: persist, cleanup

# Plugin (input adapter)
start()         # once after boot
update(dt)      # every tick: read input → emit Command
stop()          # once before shutdown: release resources
```

---

## Non-Negotiable Invariants

1. **Application has zero domain imports** — no `memory`, `reasoning`, `spatial`
2. **Services have zero UI/plugin imports** — pure domain
3. **Plugins emit Commands only** — never call Service methods
4. **EventBus.publish() queues** — `flush()` delivers (deterministic ordering)
5. **All time is `dt`** — no `time.sleep()` in tick path, no wall-clock in domain

---

## Strangler Fig Migration Rule

New code lives in `aether/` — **never imports from `legacy/`**.

Old code in `core/`, `main.py`, `brain_main.py` → migrate incrementally.
Each migration step: add new → route traffic → delete old.
Tests must pass at every step.

---

## Configuration

```yaml
app:
  tick_rate: 30        # Hz — configurable per target (Desktop=30, Debug=5, XR=90)
event_bus:
  queued: true         # Phase B: dual-mode; Phase C: queued-only
```

---

*This document supersedes all prior architecture discussions. If code contradicts this, the code is wrong.*