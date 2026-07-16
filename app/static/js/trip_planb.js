let scheduleOptions = [];

function currentScheduleId() {
  const val = document.getElementById("schedule-select").value;
  return val ? Number(val) : null;
}

async function loadSchedules() {
  const data = await api.get(`/api/trips/${TRIP_ID}/schedules`);
  scheduleOptions = data.schedules.filter((s) => s.day_no !== 0);
  const sel = document.getElementById("schedule-select");

  if (scheduleOptions.length === 0) {
    sel.innerHTML = "";
    document.getElementById("planb-list").innerHTML =
      '<p class="muted">먼저 여행 설계에서 경로를 생성해주세요.</p>';
    return;
  }

  sel.innerHTML = scheduleOptions
    .map((s) => `<option value="${s.schedule_id}">Day ${s.day_no} — ${escapeHtml(s.place.name)}</option>`)
    .join("");

  const preselect = window.PRESELECT_SCHEDULE_ID ? Number(window.PRESELECT_SCHEDULE_ID) : null;
  if (preselect && scheduleOptions.some((s) => s.schedule_id === preselect)) {
    sel.value = String(preselect);
  }

  renderRevertArea();
  await loadPlanB();
}

function renderRevertArea() {
  const s = scheduleOptions.find((x) => x.schedule_id === currentScheduleId());
  const el = document.getElementById("revert-area");
  if (s && s.original_place_id) {
    el.innerHTML = `<p class="badge warn">대체 장소 적용됨</p> <button type="button" class="secondary small" id="revert-btn">원래 장소로 되돌리기</button>`;
    document.getElementById("revert-btn").addEventListener("click", async () => {
      try {
        await api.post(`/api/schedules/${currentScheduleId()}/revert`);
        showToast("원래 일정으로 되돌렸습니다.");
        await loadSchedules();
      } catch (err) {
        showToast(err.message, true);
      }
    });
  } else {
    el.innerHTML = "";
  }
}

const TRIGGER_LABEL = { WAIT: "웨이팅", CLOSED: "휴무", RAIN: "우천", MANUAL: "기타" };
const STATUS_LABEL = { READY: "대기", ACTIVATED: "발동됨", REJECTED: "거절됨", EXPIRED: "만료" };

async function loadPlanB() {
  const scheduleId = currentScheduleId();
  const listEl = document.getElementById("planb-list");
  if (!scheduleId) {
    listEl.innerHTML = "";
    return;
  }
  try {
    const data = await api.get(`/api/schedules/${scheduleId}/planb`);
    if (data.planb.length === 0) {
      listEl.innerHTML = '<p class="muted">등록된 대체 장소가 없습니다.</p>';
      return;
    }
    listEl.innerHTML = data.planb
      .map(
        (p) => `
      <div class="list-item" data-planb-id="${p.planb_id}">
        <div>
          <strong>${escapeHtml(p.alt_place.name)}</strong>
          <span class="badge muted">${TRIGGER_LABEL[p.trigger_type] || p.trigger_type}</span>
          <span class="badge ${p.status === "READY" ? "" : "muted"}">${STATUS_LABEL[p.status] || p.status}</span>
          <p class="muted" style="margin:2px 0 0;">우선순위 ${p.priority}</p>
        </div>
        <div class="row">
          ${p.status === "READY" ? '<button type="button" data-action="activate">발동</button>' : ""}
          <button type="button" class="danger small" data-action="delete">삭제</button>
        </div>
      </div>
    `
      )
      .join("");
  } catch (err) {
    showToast(err.message, true);
  }
}

document.getElementById("schedule-select").addEventListener("change", () => {
  document.getElementById("preview-area").innerHTML = "";
  renderRevertArea();
  loadPlanB();
});

document.getElementById("planb-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const scheduleId = currentScheduleId();
  if (!scheduleId) return;
  try {
    await api.post(`/api/schedules/${scheduleId}/planb`, {
      trigger_type: document.getElementById("trigger_type").value,
      name: document.getElementById("alt_name").value,
      category: document.getElementById("alt_category").value,
      lat: Number(document.getElementById("alt_lat").value),
      lng: Number(document.getElementById("alt_lng").value),
    });
    e.target.reset();
    showToast("대체 장소를 등록했습니다.");
    await loadPlanB();
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("planb-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const planbId = btn.closest("[data-planb-id]").dataset.planbId;

  try {
    if (btn.dataset.action === "delete") {
      await api.delete(`/api/planb/${planbId}`);
      await loadPlanB();
    } else if (btn.dataset.action === "activate") {
      const preview = await api.post(`/api/planb/${planbId}/activate`);
      renderPreview(planbId, preview);
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

function renderPreview(planbId, preview) {
  const rows = preview.preview_day
    .map((it) => `<tr><td>${it.order_no}</td><td>${it.start_time}</td><td>${it.stay_min}분</td><td>${it.move_min ?? "-"}분</td></tr>`)
    .join("");
  const warnings = preview.recalc_summary.warnings.map((w) => `<p class="error-text">${escapeHtml(w)}</p>`).join("");

  document.getElementById("preview-area").innerHTML = `
    <div class="card">
      <h2>재구성 미리보기</h2>
      <p>${escapeHtml(preview.replaced.from)} → <strong>${escapeHtml(preview.replaced.to)}</strong></p>
      <p class="muted">이동시간 변화: ${preview.recalc_summary.move_min_delta}분</p>
      ${warnings}
      <table>
        <thead><tr><th>#</th><th>시각</th><th>체류</th><th>이동</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="row" style="margin-top:12px;">
        <button type="button" id="confirm-btn">확정</button>
        <button type="button" class="secondary" id="cancel-preview-btn">취소</button>
      </div>
    </div>
  `;

  document.getElementById("cancel-preview-btn").addEventListener("click", () => {
    document.getElementById("preview-area").innerHTML = "";
  });

  document.getElementById("confirm-btn").addEventListener("click", () => confirmPlanB(planbId, false));
}

async function confirmPlanB(planbId, acceptOverflow) {
  try {
    await api.post(`/api/planb/${planbId}/confirm`, { accept_overflow: acceptOverflow });
    showToast("일정을 재구성했습니다.");
    document.getElementById("preview-area").innerHTML = "";
    await loadSchedules();
  } catch (err) {
    if (err.code === "CONSTRAINT_VIOLATION") {
      document.getElementById("preview-area").insertAdjacentHTML(
        "beforeend",
        `<div class="card"><p class="error-text">${escapeHtml(err.message)}</p>
          <button type="button" id="force-confirm-btn">초과를 감수하고 확정</button></div>`
      );
      document
        .getElementById("force-confirm-btn")
        .addEventListener("click", () => confirmPlanB(planbId, true));
    } else {
      showToast(err.message, true);
    }
  }
}

loadSchedules().catch((err) => showToast(err.message, true));
