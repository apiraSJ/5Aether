/* Aether Mark-1 — Task List + Create/Edit (P1 + P2)
 * Reads and writes exclusively through the /api/v1 endpoints; the browser
 * never touches SQLite directly (locked Mark 1 rule).
 *
 * Concurrency: PATCH sends If-Match with the item's updated_at (exact
 * float per API Contract v1.1); a 409 conflict reloads the list instead
 * of silently overwriting. */

const API = "/api/v1";

const els = {
  list: document.getElementById("task-list"),
  table: document.getElementById("task-table"),
  empty: document.getElementById("empty-state"),
  loading: document.getElementById("loading-state"),
  listError: document.getElementById("list-error"),
  formError: document.getElementById("error-banner"),
  refresh: document.getElementById("refresh-btn"),
  form: document.getElementById("task-form"),
  formTitle: document.getElementById("form-title"),
  cancelBtn: document.getElementById("cancel-btn"),
  saveBtn: document.getElementById("save-btn"),
  kind: document.getElementById("f-kind"),
  title: document.getElementById("f-title"),
  tz: document.getElementById("f-tz"),
  due: document.getElementById("f-due"),
  start: document.getElementById("f-start"),
  end: document.getElementById("f-end"),
  desc: document.getElementById("f-desc"),
  taskField: document.getElementById("task-field"),
  eventField: document.getElementById("event-field"),
  eventField2: document.getElementById("event-field-2"),
};

/** id + updated_at of the item being edited (null = creating). */
let editing = null;
/** id → item, for prefilling the edit form from the rendered list. */
let itemsById = {};

// ── helpers ────────────────────────────────────────────────────────

function showFormError(message) {
  els.formError.textContent = message;
  els.formError.hidden = false;
}

function clearFormError() {
  els.formError.hidden = true;
  els.formError.textContent = "";
}

function showListError(message) {
  els.listError.textContent = message;
  els.listError.hidden = false;
}

async function readErrorMessage(response, fallback) {
  try {
    const body = await response.json();
    return body.message || body.error || fallback;
  } catch (_) {
    return fallback;
  }
}

function formatWhen(item) {
  if (item.start_at) return item.start_at.replace("T", " ").replace("+07:00", " (+07)");
  if (item.due_date) return item.due_date;
  if (item.end_at) return item.end_at.replace("T", " ").replace("+07:00", " (+07)");
  return "—";
}

function toggleKindFields() {
  const isEvent = els.kind.value === "event";
  els.taskField.hidden = isEvent;
  els.eventField.hidden = !isEvent;
  els.eventField2.hidden = !isEvent;
}

// ── list ───────────────────────────────────────────────────────────

function render(items) {
  els.list.replaceChildren();
  itemsById = {};
  for (const item of items) {
    itemsById[item.id] = item;

    const row = document.createElement("tr");

    const title = document.createElement("td");
    title.textContent = item.title;

    const when = document.createElement("td");
    when.textContent = formatWhen(item);

    const kind = document.createElement("td");
    kind.textContent = item.kind;

    const status = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge badge-${item.status}`;
    badge.textContent = item.status;
    status.appendChild(badge);

    const actions = document.createElement("td");

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => startEdit(item.id));
    actions.appendChild(editBtn);

    // Status actions (P3): only pending items can transition.
    if (item.status === "pending") {
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", () => setStatus(item.id, "complete"));
      actions.appendChild(doneBtn);

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.textContent = "Cancel";
      cancelBtn.className = "danger";
      cancelBtn.addEventListener("click", () => setStatus(item.id, "cancel"));
      actions.appendChild(cancelBtn);
    }

    row.append(title, when, kind, status, actions);
    els.list.appendChild(row);
  }
  els.table.hidden = items.length === 0;
  els.empty.hidden = items.length > 0;
}

/** POST /tasks/{id}/complete or /cancel, then refresh from the server. */
async function setStatus(id, action) {
  els.listError.hidden = true;
  try {
    const response = await fetch(`${API}/tasks/${id}/${action}`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
    }
    await loadTasks();
  } catch (err) {
    showListError(`Could not ${action}: ${err.message}`);
  }
}

async function loadTasks() {
  els.listError.hidden = true;
  els.loading.hidden = false;
  els.table.hidden = true;
  els.empty.hidden = true;
  try {
    const response = await fetch(`${API}/tasks`);
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
    }
    const data = await response.json();
    render(data.items || []);
  } catch (err) {
    showListError(`Could not load tasks: ${err.message}`);
  } finally {
    els.loading.hidden = true;
  }
}

// ── create / edit ──────────────────────────────────────────────────

function resetForm() {
  editing = null;
  els.form.reset();
  els.kind.disabled = false;
  els.formTitle.textContent = "New task";
  els.saveBtn.textContent = "Add task";
  els.cancelBtn.hidden = true;
  clearFormError();
  toggleKindFields();
}

function startEdit(id) {
  const item = itemsById[id];
  if (!item) return;
  editing = { id: item.id, updated_at: item.updated_at };
  clearFormError();

  els.kind.value = item.kind;
  els.kind.disabled = true; // kind is immutable (server rejects changes)
  els.title.value = item.title;
  els.desc.value = item.description || "";
  els.tz.value = item.tz;
  els.due.value = item.due_date || "";
  // Stored timestamps are aware ("…T10:00:00+07:00"); datetime-local
  // inputs take the naive prefix. Re-saving sends the naive value and the
  // service re-attaches this item's timezone.
  els.start.value = item.start_at ? item.start_at.slice(0, 16) : "";
  els.end.value = item.end_at ? item.end_at.slice(0, 16) : "";

  els.formTitle.textContent = "Edit task";
  els.saveBtn.textContent = "Save changes";
  els.cancelBtn.hidden = false;
  toggleKindFields();
  els.title.focus();
}

function toTimestamp(value) {
  // datetime-local gives "YYYY-MM-DDTHH:MM"; the service accepts naive
  // timestamps and attaches the item's timezone (R6 rejects date-only).
  return value ? `${value}:00` : undefined;
}

function buildPayload() {
  const payload = {
    kind: els.kind.value,
    title: els.title.value.trim(),
    description: els.desc.value,
    tz: els.tz.value,
  };
  if (payload.kind === "task") {
    if (els.due.value) payload.due_date = els.due.value;
  } else {
    const start = toTimestamp(els.start.value);
    const end = toTimestamp(els.end.value);
    if (start) payload.start_at = start;
    if (end) payload.end_at = end;
  }
  if (editing) {
    delete payload.kind; // immutable — never send it on PATCH
  }
  return payload;
}

async function submitForm(event) {
  event.preventDefault();
  clearFormError();

  const payload = buildPayload();
  if (!payload.title) {
    showFormError("Title is required.");
    return;
  }
  if (payload.kind === "event" && Boolean(payload.start_at) !== Boolean(payload.end_at)) {
    showFormError("Events need both a start and an end time.");
    return;
  }

  els.saveBtn.disabled = true;
  try {
    let response;
    if (editing) {
      response = await fetch(`${API}/tasks/${editing.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "If-Match": String(editing.updated_at),
        },
        body: JSON.stringify(payload),
      });
    } else {
      response = await fetch(`${API}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    if (response.ok) {
      resetForm();
      await loadTasks();
      return;
    }

    const message = await readErrorMessage(response, `HTTP ${response.status}`);
    if (response.status === 409) {
      // Optimistic-concurrency conflict: our copy is stale.
      showFormError("This item changed elsewhere — list reloaded, please retry.");
      await loadTasks();
      resetForm();
      return;
    }
    showFormError(message);
  } catch (err) {
    showFormError(`Request failed: ${err.message}`);
  } finally {
    els.saveBtn.disabled = false;
  }
}

// ── wiring ─────────────────────────────────────────────────────────

els.refresh.addEventListener("click", loadTasks);
els.form.addEventListener("submit", submitForm);
els.kind.addEventListener("change", toggleKindFields);
els.cancelBtn.addEventListener("click", resetForm);
document.addEventListener("DOMContentLoaded", () => {
  toggleKindFields();
  loadTasks();
});

// ── calendar view (P4) ─────────────────────────────────────────────

const cal = {
  tabList: document.getElementById("tab-list"),
  tabCalendar: document.getElementById("tab-calendar"),
  listView: document.getElementById("list-view"),
  calendarView: document.getElementById("calendar-view"),
  label: document.getElementById("cal-label"),
  grid: document.getElementById("cal-grid"),
  prev: document.getElementById("cal-prev"),
  next: document.getElementById("cal-next"),
  today: document.getElementById("cal-today"),
  dayLabel: document.getElementById("cal-day-label"),
  dayItems: document.getElementById("cal-day-items"),
  dayEmpty: document.getElementById("cal-day-empty"),
  error: document.getElementById("list-error-cal"),
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

let calYear = null;
let calMonth = null; // 1-12
let selectedDate = null;

function isoDate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function showView(name) {
  const isList = name === "list";
  cal.listView.hidden = !isList;
  cal.calendarView.hidden = isList;
  cal.tabList.classList.toggle("active", isList);
  cal.tabCalendar.classList.toggle("active", !isList);
  if (!isList && calYear === null) {
    const now = new Date();
    loadMonth(now.getFullYear(), now.getMonth() + 1, isoDate(now));
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `HTTP ${response.status}`));
  }
  return response.json();
}

function itemChip(item, timeLabel) {
  const li = document.createElement("li");
  li.className = "cal-item";
  const badge = document.createElement("span");
  badge.className = `badge badge-${item.status}`;
  badge.textContent = item.status;
  const title = document.createElement("span");
  title.className = "cal-item-title";
  title.textContent = item.title;
  const time = document.createElement("span");
  time.className = "cal-item-time muted";
  time.textContent = timeLabel || "";
  li.append(badge, title, time);
  return li;
}

async function loadDay(dateStr) {
  selectedDate = dateStr;
  cal.dayLabel.textContent = dateStr;
  cal.dayItems.replaceChildren();
  cal.dayEmpty.hidden = true;
  try {
    // Engine semantics: tasks on due_date, events across covered days,
    // all statuses shown.
    const view = await fetchJson(`${API}/calendar/day?date=${dateStr}`);
    const rows = [
      ...view.events.map((e) => itemChip(e, e.start_at ? e.start_at.slice(11, 16) : "all-day")),
      ...view.tasks.map((t) => itemChip(t, t.due_date || "")),
    ];
    for (const row of rows) cal.dayItems.appendChild(row);
    cal.dayEmpty.hidden = rows.length > 0;
    highlightSelectedDay();
  } catch (err) {
    showCalendarError(`Could not load day: ${err.message}`);
  }
}

function highlightSelectedDay() {
  for (const cell of cal.grid.querySelectorAll(".cal-cell[data-date]")) {
    cell.classList.toggle("selected", cell.dataset.date === selectedDate);
  }
}

function showCalendarError(message) {
  cal.error.textContent = message;
  cal.error.hidden = false;
}

async function loadMonth(year, month, selectDate) {
  calYear = year;
  calMonth = month;
  cal.error.hidden = true;
  cal.label.textContent = `${MONTHS[month - 1]} ${year}`;
  cal.grid.replaceChildren();
  try {
    const data = await fetchJson(`${API}/calendar/month?year=${year}&month=${month}`);

    for (const wd of WEEKDAYS) {
      const head = document.createElement("div");
      head.className = "cal-weekday";
      head.textContent = wd;
      cal.grid.appendChild(head);
    }
    // Empty leading cells so day 1 lands under its ISO weekday.
    for (let i = 0; i < data.first_weekday; i += 1) {
      cal.grid.appendChild(document.createElement("div"));
    }

    for (const day of data.days) {
      const cell = document.createElement("div");
      cell.className = "cal-cell";
      cell.dataset.date = day.date;

      const num = document.createElement("div");
      num.className = "cal-daynum";
      num.textContent = String(Number(day.date.slice(8, 10)));
      cell.appendChild(num);

      // All statuses; events first, then tasks (server order).
      for (const item of [...day.events, ...day.tasks]) {
        const chip = document.createElement("div");
        chip.className = `cal-chip cal-chip-${item.status}`;
        chip.textContent = item.title;
        cell.appendChild(chip);
      }

      cell.addEventListener("click", () => loadDay(day.date));
      cal.grid.appendChild(cell);
    }

    highlightSelectedDay();
    if (selectDate) loadDay(selectDate);
  } catch (err) {
    showCalendarError(`Could not load month: ${err.message}`);
  }
}

function shiftMonth(delta) {
  let month = calMonth + delta;
  let year = calYear;
  if (month < 1) { month = 12; year -= 1; }
  if (month > 12) { month = 1; year += 1; }
  loadMonth(year, month);
}

cal.prev.addEventListener("click", () => shiftMonth(-1));
cal.next.addEventListener("click", () => shiftMonth(1));
cal.today.addEventListener("click", () => {
  const now = new Date();
  loadMonth(now.getFullYear(), now.getMonth() + 1, isoDate(now));
});
cal.tabList.addEventListener("click", () => showView("list"));
cal.tabCalendar.addEventListener("click", () => showView("calendar"));
