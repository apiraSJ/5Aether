# Aether Mark-1 — Acceptance Checklist

เอกสารเกณฑ์ส่งมอบ Prototype สำหรับตรวจรับด้วยตนเอง (manual acceptance) และอ้างอิงตอนแก้ defect

- **Baseline**: commit `9b5fff9` — ชุด test ที่คาดหวัง: **1,446 passed**
- **กติการอบตรวจ**: ห้ามแก้โค้ดระหว่าง acceptance run เว้นแต่พบ blocker ที่ทำให้ทดสอบต่อไม่ได้ เพื่อให้ผลตรวจสะท้อน commit ที่กำลังรับมอบจริง
- **ไม่อยู่ในขอบเขตรอบนี้**: AI/LLM, Phase 4 (Review Queue/Evidence), การแก้ Schedule Engine

## 0. ก่อนเริ่ม — Environment

ใช้ Python ของโปรเจกต์เท่านั้น — `python` บน PATH อาจชี้ไป global install
(เช่น `C:\Python314\python.exe`) ที่ไม่มี fastapi/uvicorn

```powershell
# จาก D:\3CS\5Aether
.\.venv\Scripts\python.exe -m pip install -e ".[server,dev]"
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"
```

ถ้า interpreter ผิด `--mode web` จะจบด้วยข้อความ (ไม่ใช่ traceback):

```
[Aether] Web dependencies missing: ...
[Aether] Interpreter: ...
[Aether] Fix: .\.venv\Scripts\python.exe -m pip install -e ".[server]"
```

## 1. Task CRUD — ผ่าน Web UI

ขั้นตอน: สร้าง Task ใหม่จากฟอร์ม → รีเฟรชหน้า → แก้ไข → รีเฟรช → ลบผ่าน `/docs`
(`DELETE /api/v1/tasks/{id}`)

ผลที่ควรเห็น:

- แถวใหม่ปรากฏหลังบันทึก ฟอร์ม reset เป็น "New task" · `status=pending` (badge สีเหลือง)
- ข้อมูลยังอยู่ครบหลัง refresh ทุกครั้ง
- แก้ชื่อแล้วแถวแสดงชื่อใหม่จริง
- ลบผ่าน `/docs` แล้วงานหายจาก list ถาวร

ข้อควรระวัง:

- ⚠️ **ไม่มีปุ่ม Delete ใน UI** — ลบผ่าน `/docs` "Try it out" เท่านั้น (scope decision)
- ⚠️ **Watch item (ยังไม่ใช่ defect)**: ถ้าแก้ไขแบบมี conflict (ข้อ 2) แล้วข้อความที่พิมพ์ค้างในฟอร์ม **หาย** → บันทึกเป็น **Defect #2** (เกณฑ์: ผู้ใช้ต้องพิมพ์ใหม่)

## 2. Task Status & History

ขั้นตอน: กดปุ่ม **Done** → กดปุ่ม **Cancel** (งานอีกอัน) → ตรวจ history ผ่าน
`GET /api/v1/tasks/{id}/history` (ใน `/docs`)

ผลที่ควรเห็น:

- badge เปลี่ยนเป็น `completed` / `cancelled` ตามลำดับ
- **ปุ่ม Done/Cancel หาย** จากแถวที่ไม่ใช่ `pending` อีกต่อไป
- history เรียง **ใหม่สุดบนสุด**: `completed → updated → created`
- งาน event กด Complete ไม่ได้ (API ตอบ 400 — ทำได้แค่ Cancel)

ข้อควรระวัง:

- ⚠️ UI ไม่มีหน้า History — ดูผ่าน `/docs` เท่านั้น (scope decision)
- ⚠️ UI ไม่มีช่อง reason ตอน Cancel — reason ผ่าน API `?reason=...` เท่านั้น
- ⚠️ **Watch item (ยังไม่ใช่ defect)**: ทดสอบ conflict โดยเปิด 2 tabs แก้ task เดียวกัน —
  tab A บันทึกก่อน แล้ว tab B บันทึกทีหลัง ต้องได้ banner
  `This item changed elsewhere — list reloaded, please retry.`
  และข้อมูล tab A ต้อง **ไม่ถูกทับ** · ถ้าฟอร์ม tab B ถูกล้างจนต้องพิมพ์ใหม่ → **Defect #2**

## 3. Calendar Correctness

ขั้นตอน: Tabs `List`/`Calendar` → เลื่อนเดือน ◀ ▶ → คลิก cell วัน → ตรวจ day panel → สร้าง event UTC แล้วดูใน day panel

ผลที่ควรเห็น:

- grid จันทร์เป็นคอลัมน์แรก (`first_weekday` ของเดือน — ต.ค. 2026 = 3 คือ พฤหัส)
- งานข้ามวันขึ้นทุกวันที่ครอบคลุม
- งานที่มี `tz=UTC` แสดง `+00:00` ใน day panel
- ⚠️ **completed/cancelled ยังแสดงในปฏิทิน** — นี่คือ decision ที่ล็อกไว้ (no status filtering) **ไม่ใช่บั๊ก**
- งานที่ไม่มี due_date ไม่ปรากฏในปฏิทิน (ใช้ได้เฉพาะใน List)

## 4. Persistence

ขั้นตอน: สร้าง + แก้ไข Task → กด `Ctrl+C` ที่ console → เปิด `--mode web` ใหม่ → เช็คข้อมูล

ผลที่ควรเห็น:

- log ปิดด้วย `Shutting down` แล้วคืน prompt (ไม่ค้าง)
- งาน + offset timezone (`+07:00` / `+00:00`) ครบหลังเปิดใหม่
- (Machine-proven โดย `TestRestartPersistence` — รอบนี้ยืนยันด้วยตา)

## 5. API Validation & Errors

รัน snippet ด้านล่างตอน server เปิดอยู่ หรือใช้ `/docs` "Try it out"

```powershell
$h = @{ "Content-Type" = "application/json" }
$b = "http://127.0.0.1:8765/api/v1"

# field เกิน → 400 {"error":"validation_error"}
Invoke-RestMethod "$b/tasks" -Method Post -Headers $h -Body '{"kind":"task","title":"x","colour":"blue"}'

# null ที่ไม่อนุญาต (title) → 400
Invoke-RestMethod "$b/tasks/no-such-id" -Method Patch -Headers $h -Body '{"title":null}'

# R6: date-only สำหรับ timed item → 400
Invoke-RestMethod "$b/tasks" -Method Post -Headers $h -Body '{"kind":"event","title":"x","start_at":"2026-10-21","end_at":"2026-10-21"}'

# R1: ลำดับเวลาแบบ mixed-offset ย้อนแย้ง (end ก่อน start จริง ๆ) → 400
Invoke-RestMethod "$b/tasks" -Method Post -Headers $h -Body '{"kind":"event","title":"x","start_at":"2026-10-21T23:00:00+07:00","end_at":"2026-10-21T23:30:00+09:00"}'

# If-Match ไม่ตรง → 409 {"error":"conflict"}
$task = Invoke-RestMethod "$b/tasks" -Method Post -Headers $h -Body '{"kind":"task","title":"stale check"}'
Invoke-RestMethod "$b/tasks/$($task.id)" -Method Patch -Headers ($h + @{ "If-Match" = "1.0" }) -Body '{"title":"x"}'
Invoke-RestMethod "$b/tasks/$($task.id)" -Method Delete | Out-Null
```

ใน UI ทุกกรณี error ต้องแสดง banner ข้อความอ่านง่าย ห้ามค้างเงียบ

## 6. Lifecycle & Shutdown

ขั้นตอน: เปิด `--mode web` → Ctrl+C → เปิดซ้ำทันที → เช็ค process

```powershell
# หลังปิด server: ต้องเหลือ 0
(Get-CimInstance Win32_Process -Filter "Name='python.exe'").Count
```

ผลที่ควรเห็น: เปิดซ้ำได้ทันทีไม่ต้องรอ · ไม่มี process/thread ค้าง ·
host ต่างประเทศถูกบล็อก (`Host: evil.example.com` → 403)

## บันทึก Defect

```
[Defect #N] ข้อไหนใน checklist / ทำอย่างไร
            ผลที่คาด vs ผลจริง
            รุนแรง: blocker / ควรแก้ / รับได้
```

กติกาแก้ไข: 1 ปัญหา = 1 commit เล็ก · มี test คุมพฤติกรรม · full suite ต้องผ่านก่อน commit
(`.\.venv\Scripts\python.exe -m pytest -q` → มากกว่า 1,446 และห้ามน้อยลง) ·
ไม่แก้ Schedule Engine / Core / Plugins โดยไม่จำเป็น

## ตรวจสอบรายงานด้วยตัวเอง (ทางเลือก)

```powershell
git log --oneline -12        # ลำดับ commits ตั้งแต่ skeleton
git show --stat 9b5fff9      # diff ของ dependency-guard fix
.\.venv\Scripts\python.exe -m pytest -q   # คาด 1,446 passed
```
