# AETHER UPDATE PLAN

> อัปเดตระบบจัดการ Event + แก้ไขปัญหา + เพิ่ม Feature
> วันที่: 2026-07-22

---

## สถานะปัจจุบัน

| สถานะ | รายละเอียด |
|--------|-------------|
| Camera | ทำงานได้ 640x480 |
| YOLO | ทำงานได้ |
| GestureRecognizer | ทำงานได้ 8 gestures |
| DearPyGui Dashboard | ทำงานได้ |
| CursorOverlay (PySide6) | มี code แล้ว แต่ crash บ่อย |
| HomeMenu | มี code แล้ว ไม่เคยเปิดได้จริง |
| AetherUI Panels | มี code แล้ว ไม่เคยเปิดได้จริง |
| ทดสอบ | 84 tests ผ่านทั้งหมด |

---

## ปัญหาที่พบ

### ปัญหาวิกฤต (Critical)

| # | ปัญหา | ไฟล์ | สาเหตุ |
|---|--------|-------|--------|
| 1 | **main.py ใหญ่เกินไป** (497 บรรทัด) | `main.py` | ทุกอย่างอัดอยู่ไฟล์เดียว — camera, gesture, HUD, UI wiring, render loop |
| 2 | **2 ระบบ Command ซ้ำกัน** | `command/` vs `commands/` | `command/` ใช้ dataclass, `commands/` ใช้ ABC ต่างกัน entirely |
| 2 ระบบ Config ซ้ำกัน** | `config.py` vs `core/settings.py` | `config.py` merge ชั้นเดียว, `settings.py` merge ซ้อนกัน |
| 4 | **2 entry points ต่างกัน** | `main.py` vs `brain_main.py` | main.py มี camera ไม่มี UI panels, brain_main.py มี UI panels ไม่มี camera |
| 5 | **Mixed GUI frameworks** | `main.py` | DearPyGui + PySide6 ใน process เดียวกัน ทำให้ crash |

### ปัญหาสำคัญ (High)

| # | ปัญหา | ไฟล์ | สาเหตุ |
|---|--------|-------|--------|
| 6 | **Gesture name ไม่ตรงกัน** | `core/interaction_mode.py` vs `vision/gesture_actions.py` | ใช้ "OPEN_PALM" vs "Open_Palm" ไม่ match กัน |
| 7 | **Global mutable state** | `main.py` | `runtime_hands`, `runtime_cursor` ฯลฯ ใช้ global + lock ไม่ปลอดภัย |
| 8 | **Thread safety ไม่สมบูรณ์** | `main.py` | Vision thread เรียก Qt widget โดยตรง |
| 9 | **AetherApp vs AetherEngine** | `core/app.py` vs `core/engine.py` | 2 lifecycle managers ทำหน้าที่เดียวกัน |
| 10 | **Unused imports** | `main_brain.py` | ใช้ Module, ModuleManager แต่ไม่ได้ทำอะไร |

### ปัญหาเล็ก (Low)

| # | ปัญหา | ไฟล์ | สาเหตุ |
|---|--------|-------|--------|
| 11 | Stub files | `ui/sidebar.py`, `ui/status_bar.py` | มีแต่ state ไม่มี rendering |
| 12 | No tracking | `vision/tracking.py` | ใส่ sequential ID ไม่มี tracking จริง |
| 13 | Windows-only | `context/context_manager.py` | ใช้ win32gui — ทำงานบน Windows เท่านั้น |
| 14 | ไม่มี `__init__.py` | `command/` | ใช้ implicit namespace |
| 15 | Inconsistent packaging | `perception/__init__.py` ว่าง vs `memory/__init__.py` export |

---

## แผนการอัปเดต

### Phase 1: แยกไฟล์ main.py (สำคัญสุด)

**เป้าหมาย:** ลด main.py จาก 497 บรรทัด เหลือ ~150 บรรทัด

| ไฟล์ใหม่ | ย้ายจาก main.py | จำนวนบรรทัด (ประมาณ) |
|-----------|------------------|----------------------|
| `core/gesture_router.py` | `on_hand_update()`, `_handle_gesture_action()`, `_handle_pinch_click()`, cooldown logic | ~120 |
| `interface/hud_renderer.py` | `draw_cursor_on_frame()`, `draw_pinch_line()`, `process_hud_overlays()` | ~100 |
| `core/action_queue.py` | `_action_queue`, `process_action_queue()` | ~40 |

**main.py หลังแก้** เหลือแค่:
```
main()
├── Create QApplication
├── Create AetherApp + EventBus
├── Create CursorManager + UIManager
├── Create AetherUI panels
├── Start perception plugins
├── Start camera thread
├── DearPyGui render loop (processEvents + process_action_queue)
└── Shutdown
```

---

### Phase 2: รวม 2 ระบบ Command

**เป้าหมาย:** เหลือระบบเดียว

| ปัจจุบัน | 保留 | ลบ |
|-----------|------|-----|
| `command/command.py` (EventBus-based) | `command/` | `commands/` |
| `command/handler.py` | `command/handler.py` | `commands/base.py` |
| `commands/` (CLI text commands) | ย้าย `find`, `remember`, `forget`, `status`, `task`, `list` → `command/builtin/` | ทั้ง directory |

**โครงสร้างใหม่:**
```
command/
├── __init__.py
├── command.py          ← dataclass + registry (เดิม)
├── handler.py          ← EventBus integration (เดิม)
└── builtin/
    ├── find.py         ← จาก commands/find.py
    ├── remember.py     ← จาก commands/remember.py
    ├── forget.py       ← จาก commands/forget.py
    ├── status.py       ← จาก commands/status.py
    ├── task.py         ← จาก commands/task.py
    └── list_cmd.py     ← จาก commands/list_cmd.py
```

---

### Phase 3: รวม 2 ระบบ Config

**เป้าหมาย:** เหลือ `core/settings.py` เดียว

| 保留 | ลบ |
|------|-----|
| `core/settings.py` (recursive merge) | `config.py` (shallow merge) |

แก้ `main.py` ให้ import `core/settings.py` แทน `config.py`

---

### Phase 4: รวม 2 ระบบ Lifecycle

**เป้าหมาย:** เหลือ `AetherEngine` เดียว

| 保留 | ลบ/merge |
|------|----------|
| `core/engine.py` (AetherEngine) | `core/app.py` (AetherApp) — merge เข้า engine.py |
| `core/module.py` (ModuleManager) | `core/plugin_manager.py` (PluginManager) — merge เข้า module.py |

---

### Phase 5: แก้ Gesture Name Mismatch

**เป้าหมาย:** ใช้ชื่อเดียวกันทั้งระบบ

| ปัจจุบัน | แก้เป็น |
|-----------|---------|
| `core/interaction_mode.py` ใช้ "OPEN_PALM" | เปลี่ยนเป็น "Open_Palm" |
| `core/interaction_mode.py` ใช้ "POINT" | เปลี่ยนเป็น "Pointing_Up" |
| `core/interaction_mode.py` ใช้ "PINCH" | เปลี่ยนเป็น "Pinch" |
| `core/interaction_mode.py` ใช้ "FIST" | เปลี่ยนเป็น "Closed_Fist" |

---

### Phase 6: ลบ Global State

**เป้าหมาย:** ใช้ class-based state แทน global variables

| ปัจจุบัน | แก้เป็น |
|-----------|---------|
| `runtime_hands = []` (global) | ย้ายเข้า `PerceptionState` class |
| `runtime_cursor = None` (global) | ย้ายเข้า `CursorManager` |
| `runtime_pinch = False` (global) | ย้ายเข้า `GestureRouter` |
| `_last_gesture = None` (global) | ย้ายเข้า `GestureRouter` |

---

### Phase 7: Clean Up Dead Code

| ไฟล์ | ทำอะไร |
|------|--------|
| `ui/sidebar.py` | ลบ — stub ไม่มีประโยชน์ |
| `ui/status_bar.py` | ลบ — stub ไม่มีประโยชน์ |
| `vision/tracking.py` | ลบ — ไม่มี tracking จริง |
| `main_brain.py` | ลบ — ซ้ำกับ `brain_main.py` |
| `config.py` | ลบ — ซ้ำกับ `core/settings.py` |

---

## ลำดับความสำคัญ

```
Phase 1 (แยก main.py)         ← ทำก่อน เพราะเป็น root cause ของทุกปัญหา
Phase 5 (แก้ gesture names)    ← ทำทันที เพราะทำให้ UI ไม่เปิด
Phase 6 (ลบ global state)     ← ทำคู่กับ Phase 1
Phase 3 (รวม config)          ← ง่ายสุด ทำได้เร็ว
Phase 2 (รวม command)         ← ใช้เวลา แต่คุ้มค่า
Phase 4 (รวม lifecycle)       ← ซับซ้อน ทำหลัง Phase 1-3
Phase 7 (ลบ dead code)        ← ทำสุดท้าย
```

---

## ผลลัพธ์ที่คาดหวัง

### ก่อนแก้
```
main.py (497 บรรทัด)
├── camera logic
├── hand detection
├── gesture processing
├── HUD drawing
├── cursor drawing
├── action queue
├── UI wiring
├── DearPyGui setup
├── DearPyGui render loop
└── OpenCV fallback

brain_main.py (316 บรรทัด)
├── AetherEngine setup
├── UIManager setup
├── gesture processing (ซ้ำกับ main.py)
└── hotkey listener

config.py (43 บรรทัด) ← ซ้ำกับ core/settings.py
commands/ (8 ไฟล์) ← ซ้ำกับ command/
main_brain.py (241 บรรทัด) ← ซ้ำกับ brain_main.py
```

### หลังแก้
```
main.py (~150 บรรทัด) ← orchestrator เท่านั้น
core/gesture_router.py (~120 บรรทัด) ← gesture → action
interface/hud_renderer.py (~100 บรรทัด) ← CV frame drawing
core/action_queue.py (~40 บรรทัด) ← thread-safe queue
core/engine.py ← รวม AetherApp เข้ามา
core/module.py ← รวม PluginManager เข้ามา
core/settings.py ← config เดียว
command/ ← command เดียว
    └── builtin/ ← text commands ย้ายเข้ามา
```

---

## สถิติ

|  Metric | ก่อน | หลัง |
|---------|------|------|
| Entry points | 3 (`main.py`, `brain_main.py`, `main_brain.py`) | 2 (`main.py`, `brain_main.py`) |
| Command systems | 2 (`command/`, `commands/`) | 1 (`command/`) |
| Config systems | 2 (`config.py`, `core/settings.py`) | 1 (`core/settings.py`) |
| Lifecycle managers | 2 (`AetherApp`, `AetherEngine`) | 1 (`AetherEngine`) |
| main.py บรรทัด | 497 | ~150 |
| Dead code files | 4 | 0 |
| Total files | ~64 | ~52 |
| Total lines | ~6,500 | ~5,500 |
