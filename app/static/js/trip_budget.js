const CATEGORY_LABEL = { TRANSPORT: "교통", STAY: "숙박", FOOD: "식비", TICKET: "입장료", ETC: "기타" };

async function loadSummary() {
  const data = await api.get(`/api/trips/${TRIP_ID}/expenses/summary`);
  const el = document.getElementById("summary-area");
  const rows = data.categories
    .map((c) => {
      const ratioPct = c.ratio == null ? 0 : Math.min(100, Math.round(c.ratio * 100));
      const over = c.remaining < 0;
      return `
      <div style="margin-bottom:10px;">
        <div class="row between">
          <strong>${CATEGORY_LABEL[c.category]}</strong>
          <span class="muted">${c.spend.toLocaleString()}원 / ${c.budget.toLocaleString()}원</span>
        </div>
        <div style="background:var(--color-border); border-radius:6px; height:8px; overflow:hidden;">
          <div style="width:${ratioPct}%; height:100%; background:${over ? "var(--color-danger)" : "var(--color-primary)"};"></div>
        </div>
        ${over ? '<span class="badge warn">예산 초과</span>' : ""}
      </div>
    `;
    })
    .join("");
  el.innerHTML = `
    <div class="row between" style="margin-bottom:14px;">
      <strong>총 잔액</strong>
      <span>${data.total_remaining.toLocaleString()}원</span>
    </div>
    ${rows}
  `;
}

async function loadExpenses() {
  const data = await api.get(`/api/trips/${TRIP_ID}/expenses`);
  const el = document.getElementById("expense-list");
  if (data.expenses.length === 0) {
    el.innerHTML = '<p class="muted">기록이 없습니다.</p>';
    return;
  }
  el.innerHTML = `
    <table>
      <thead><tr><th>카테고리</th><th>유형</th><th>금액</th><th>메모</th></tr></thead>
      <tbody>
        ${data.expenses
          .map(
            (e) => `
          <tr>
            <td>${CATEGORY_LABEL[e.category]}</td>
            <td>${e.item_type === "BUDGET" ? "예산" : "지출"}</td>
            <td>${e.amount.toLocaleString()}원</td>
            <td>${escapeHtml(e.memo || "")}</td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

document.getElementById("expense-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api.post(`/api/trips/${TRIP_ID}/expenses`, {
      category: document.getElementById("category").value,
      item_type: document.getElementById("item_type").value,
      amount: Number(document.getElementById("amount").value),
      memo: document.getElementById("memo").value || null,
    });
    e.target.reset();
    await Promise.all([loadSummary(), loadExpenses()]);
  } catch (err) {
    showToast(err.message, true);
  }
});

Promise.all([loadSummary(), loadExpenses()]).catch((err) => showToast(err.message, true));
