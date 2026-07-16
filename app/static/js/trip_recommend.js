async function loadScheduleOptions() {
  const data = await api.get(`/api/trips/${TRIP_ID}/schedules`);
  const sel = document.getElementById("near_schedule_id");
  data.schedules.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.schedule_id;
    opt.textContent = `${escapeHtml(s.place.name)} (Day ${s.day_no || "미배치"})`;
    sel.appendChild(opt);
  });
}

function recCardHtml(rec) {
  return `
    <div class="card" data-rec-id="${rec.rec_id}">
      <div class="row between">
        <div>
          <h3>${escapeHtml(rec.place.name)} <span class="badge muted">${rec.place.category}</span></h3>
          <p class="muted">적합도 ${(rec.score * 100).toFixed(0)}점</p>
          <p>${escapeHtml(rec.reason)}</p>
        </div>
        <div class="row">
          <button type="button" data-action="accept">일정에 추가</button>
          <button type="button" class="secondary" data-action="reject">숨기기</button>
        </div>
      </div>
    </div>
  `;
}

document.getElementById("rec-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const resultsEl = document.getElementById("rec-results");
  resultsEl.innerHTML = '<div class="spinner"></div>';
  try {
    const nearId = document.getElementById("near_schedule_id").value;
    const body = {
      type: document.getElementById("rec_type").value,
      count: Number(document.getElementById("rec_count").value),
    };
    if (nearId) body.near_schedule_id = Number(nearId);

    const data = await api.post(`/api/trips/${TRIP_ID}/recommendations`, body);
    if (data.recommendations.length === 0) {
      resultsEl.innerHTML = '<div class="empty-state">조건에 맞는 추천 결과가 없습니다.</div>';
      return;
    }
    resultsEl.innerHTML = data.recommendations.map(recCardHtml).join("");
  } catch (err) {
    resultsEl.innerHTML = "";
    showToast(err.message, true);
  }
});

document.getElementById("rec-results").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const card = btn.closest("[data-rec-id]");
  const recId = card.dataset.recId;
  try {
    if (btn.dataset.action === "accept") {
      await api.post(`/api/recommendations/${recId}/accept`);
      showToast("일정(미배치 보관함)에 추가했습니다.");
    } else {
      await api.post(`/api/recommendations/${recId}/reject`);
    }
    card.remove();
  } catch (err) {
    showToast(err.message, true);
  }
});

loadScheduleOptions().catch((err) => showToast(err.message, true));
