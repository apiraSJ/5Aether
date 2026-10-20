/* Aether Mark-1 — Task List (P1)
 * Reads exclusively through the /api/v1 endpoints. The browser never
 * touches SQLite directly (locked Mark 1 rule). */

const API = "/api/v1";

const els = {
  list: document.getElementById("task-list"),
  table: document.getElementById("task-table"),
  empty: document.getElementById("empty-state"),
  loading: document.getElementById("loading-state"),
  error: document.getElementById("error-banner"),
  refresh: document.getElementById("refresh-btn"),
};

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function formatWhen(item) {
  // Timed items show start (or due); all-day/date-only show the date.
  if (item.start_at) return item.start_at.replace("T", " ").replace("+07:00", " (+07)");
  if (item.due_date) return item.due_date;
  if (item.end_at) return item.end_at.replace("T", " ").replace("+07:00", " (+07)");
  return "—";
}

function render(items) {
  els.list.replaceChildren();
  for (const item of items) {
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

    row.append(title, when, kind, status);
    els.list.appendChild(row);
  }
  els.table.hidden = items.length === 0;
  els.empty.hidden = items.length > 0;
}

async function loadTasks() {
  clearError();
  els.loading.hidden = false;
  els.table.hidden = true;
  els.empty.hidden = true;
  try {
    const response = await fetch(`${API}/tasks`);
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        detail = body.message || body.error || detail;
      } catch (_) { /* non-JSON error body */ }
      throw new Error(detail);
    }
    const data = await response.json();
    render(data.items || []);
  } catch (err) {
    showError(`Could not load tasks: ${err.message}`);
  } finally {
    els.loading.hidden = true;
  }
}

els.refresh.addEventListener("click", loadTasks);
document.addEventListener("DOMContentLoaded", loadTasks);
