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
