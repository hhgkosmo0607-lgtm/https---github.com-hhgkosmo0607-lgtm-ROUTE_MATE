async function loadChecklist() {
  const el = document.getElementById("checklist-items");
  try {
    const data = await api.get(`/api/trips/${TRIP_ID}/checklist`);
    if (data.checklist.length === 0) {
      el.innerHTML = '<div class="empty-state">항목이 없습니다.</div>';
      return;
    }
    el.innerHTML = data.checklist
      .map(
        (item) => `
      <div class="list-item" data-check-id="${item.check_id}">
        <label style="display:flex; align-items:center; gap:8px; width:auto; margin:0;">
          <input type="checkbox" class="done-checkbox" style="width:auto;" ${item.is_done ? "checked" : ""}>
          <span style="${item.is_done ? "text-decoration:line-through; color:var(--color-text-muted);" : ""}">${escapeHtml(item.item)}</span>
        </label>
        <button type="button" class="danger small" data-action="delete">삭제</button>
      </div>
    `
      )
      .join("");
  } catch (err) {
    el.innerHTML = `<div class="error-text">${escapeHtml(err.message)}</div>`;
  }
}

document.getElementById("add-item-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("item-input");
  try {
    await api.post(`/api/trips/${TRIP_ID}/checklist`, { item: input.value });
    input.value = "";
    await loadChecklist();
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("checklist-items").addEventListener("click", async (e) => {
  const container = e.target.closest("[data-check-id]");
  if (!container) return;
  const checkId = container.dataset.checkId;

  try {
    if (e.target.classList.contains("done-checkbox")) {
      await api.put(`/api/checklist/${checkId}`, { is_done: e.target.checked });
      await loadChecklist();
    } else if (e.target.closest('button[data-action="delete"]')) {
      await api.delete(`/api/checklist/${checkId}`);
      await loadChecklist();
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

loadChecklist();
