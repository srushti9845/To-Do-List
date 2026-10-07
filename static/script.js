/* Task Management - frontend logic (fetch API) */
const $ = (id) => document.getElementById(id);
const REFRESH_MS = 15000; // auto-refresh interval (see refreshAll)

let tasks = [];

/* ---------- helpers ---------- */
function esc(text) { // prevents XSS when inserting user text into HTML
  const d = document.createElement("div");
  d.textContent = text == null ? "" : String(text);
  return d.innerHTML;
}

function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 3000);
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) { window.location.href = "/login"; return null; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function statusClass(s) {
  return s === "Completed" ? "completed" : s === "In Progress" ? "progress" : "pending";
}

/* ---------- load data ---------- */
async function loadStats() {
  const s = await api("/api/stats");
  if (!s) return;
  $("stat-total").textContent = s.total;
  $("stat-pending").textContent = s.pending;
  $("stat-progress").textContent = s.in_progress;
  $("stat-done").textContent = s.completed;
  $("stat-overdue").textContent = s.overdue;

  const sel = $("filter-category");
  const current = sel.value;
  sel.innerHTML = '<option value="">All Categories</option>' +
    s.categories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  sel.value = s.categories.includes(current) ? current : "";
}

async function loadTasks() {
  const params = new URLSearchParams({
    q: $("search").value.trim(),
    status: $("filter-status").value,
    priority: $("filter-priority").value,
    category: $("filter-category").value,
    sort: $("sort").value,
  });
  const data = await api("/api/tasks?" + params.toString());
  if (!data) return;
  tasks = data.tasks;
  renderTasks();
}

/* Dashboard auto-refresh. To use WebSockets later, replace this
   function (and the setInterval below) with a Flask-SocketIO listener. */
async function refreshAll() {
  try { await Promise.all([loadStats(), loadTasks()]); }
  catch (e) { toast(e.message, true); }
}

/* ---------- render ---------- */
function renderTasks() {
  const list = $("task-list");
  $("empty").classList.toggle("hidden", tasks.length > 0);
  list.innerHTML = tasks.map((t) => {
    const sc = statusClass(t.status);
    const cls = ["task", "st-" + sc, t.is_overdue ? "overdue" : "",
                 t.priority === "High" ? "priority-high" : ""].join(" ");
    return `
    <article class="${cls}">
      <h3>${esc(t.title)}</h3>
      ${t.description ? `<p class="desc">${esc(t.description)}</p>` : ""}
      <div class="badges">
        <span class="badge b-${sc}">${esc(t.status)}</span>
        <span class="badge b-${t.priority.toLowerCase()}">${t.priority === "High" ? "🔥 " : ""}${esc(t.priority)}</span>
        ${t.is_overdue ? '<span class="badge b-overdue">⚠️ Overdue</span>' : ""}
        ${t.category ? `<span class="badge">🏷️ ${esc(t.category)}</span>` : ""}
      </div>
      <p class="meta">📅 Due: ${t.due_date ? esc(t.due_date) : "No due date"}</p>
      <div class="task-actions">
        ${t.status !== "Completed" ? `<button class="a-done" onclick="completeTask(${t.id})">✔ Complete</button>` : ""}
        <button class="a-edit" onclick="openModal(${t.id})">✏️ Edit</button>
        <button class="a-del" onclick="deleteTask(${t.id})">🗑 Delete</button>
      </div>
    </article>`;
  }).join("");
}

/* ---------- modal ---------- */
function openModal(id = null) {
  $("form-error").classList.add("hidden");
  $("task-form").reset();
  $("task-id").value = "";
  $("modal-title").textContent = "Add Task";
  if (id !== null) {
    const t = tasks.find((x) => x.id === id);
    if (!t) return;
    $("modal-title").textContent = "Edit Task";
    $("task-id").value = t.id;
    $("title").value = t.title;
    $("description").value = t.description || "";
    $("priority").value = t.priority;
    $("status").value = t.status;
    $("due_date").value = t.due_date || "";
    $("category").value = t.category || "";
  }
  $("modal").classList.remove("hidden");
  $("title").focus();
}

function closeModal() { $("modal").classList.add("hidden"); }

$("add-btn").addEventListener("click", () => openModal());
$("modal-close").addEventListener("click", closeModal);
$("cancel-btn").addEventListener("click", closeModal);
$("modal").addEventListener("click", (e) => { if (e.target === $("modal")) closeModal(); });

$("task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("task-id").value;
  const body = {
    title: $("title").value,
    description: $("description").value,
    priority: $("priority").value,
    status: $("status").value,
    due_date: $("due_date").value,
    category: $("category").value,
  };
  try {
    await api(id ? `/api/tasks/${id}` : "/api/tasks", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    closeModal();
    toast(id ? "Task updated ✅" : "Task created 🎉");
    refreshAll();
  } catch (err) {
    $("form-error").textContent = err.message;
    $("form-error").classList.remove("hidden");
  }
});

/* ---------- actions ---------- */
async function completeTask(id) {
  try { await api(`/api/tasks/${id}/complete`, { method: "PATCH" }); toast("Task completed ✅"); refreshAll(); }
  catch (e) { toast(e.message, true); }
}

async function deleteTask(id) {
  if (!confirm("Delete this task permanently?")) return;
  try { await api(`/api/tasks/${id}`, { method: "DELETE" }); toast("Task deleted 🗑"); refreshAll(); }
  catch (e) { toast(e.message, true); }
}

/* ---------- filters ---------- */
let searchTimer;
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadTasks, 300); // wait while typing
});
["filter-status", "filter-priority", "filter-category", "sort"]
  .forEach((id) => $(id).addEventListener("change", loadTasks));

/* ---------- start ---------- */
refreshAll();
setInterval(() => { if ($("modal").classList.contains("hidden")) refreshAll(); }, REFRESH_MS);
