let schedules = [];
let tripInfo = null;
let activeDay = null;

async function loadTrip() {
  tripInfo = await api.get(`/api/trips/${TRIP_ID}`);
  document.querySelector("#trip-title h1").textContent = tripInfo.title;
}

async function loadSchedules() {
  const data = await api.get(`/api/trips/${TRIP_ID}/schedules`);
  schedules = data.schedules;
  render();
}

function tripTotalDays() {
  if (!tripInfo) return 1;
  const start = new Date(tripInfo.start_date);
  const end = new Date(tripInfo.end_date);
  return Math.round((end - start) / 86400000) + 1;
}

function groupByDay() {
  const byDay = {};
  for (const s of schedules) {
    if (s.day_no === 0) continue;
    (byDay[s.day_no] ||= []).push(s);
  }
  for (const day in byDay) byDay[day].sort((a, b) => a.order_no - b.order_no);
  return byDay;
}

function render() {
  renderUnassigned();
  renderDayTabs();
  renderDayContent();
  populateDaySelects();
}

function renderDayTabs() {
  const byDay = groupByDay();
  const days = Object.keys(byDay)
    .map(Number)
    .sort((a, b) => a - b);
  if (days.length && !days.includes(activeDay)) activeDay = days[0];
  if (days.length === 0) activeDay = null;

  document.getElementById("day-tabs").innerHTML = days
    .map((d) => `<a href="#" data-day="${d}" class="${d === activeDay ? "active" : ""}">Day ${d}</a>`)
    .join("");
}

function renderDayContent() {
  const byDay = groupByDay();
  const el = document.getElementById("day-content");
  if (!activeDay || !byDay[activeDay]) {
    el.innerHTML = '<div class="empty-state">장소를 추가하고 [경로 자동 생성]을 눌러보세요.</div>';
    return;
  }
  const items = byDay[activeDay];
  el.innerHTML = items.map((s, idx) => scheduleItemHtml(s, idx, items.length)).join("");
}

function renderUnassigned() {
  const list = schedules.filter((s) => s.day_no === 0);
  const el = document.getElementById("unassigned-list");
  if (list.length === 0) {
    el.innerHTML = '<p class="muted">없음</p>';
    return;
  }
  el.innerHTML = list
    .map(
      (s) => `
    <div class="list-item" data-schedule-id="${s.schedule_id}">
      <div>
        <strong>${escapeHtml(s.place.name)}</strong>
        <span class="badge muted">${s.place.category}</span>
      </div>
      <div class="row">
        <select class="day-move-select" style="width:auto;"></select>
        <button class="danger small" type="button" data-action="delete">삭제</button>
      </div>
    </div>
  `
    )
    .join("");
}

function scheduleItemHtml(s, idx, total) {
  const moveInfo = s.move_min == null ? "" : `<span class="badge">이동 ${s.move_min}분 / ${s.move_km}km</span>`;
  return `
    <div class="list-item" style="flex-direction:column; align-items:stretch;" data-schedule-id="${s.schedule_id}">
      <div class="row between">
        <div>
          <strong>${idx + 1}. ${escapeHtml(s.place.name)}</strong>
          <span class="badge muted">${s.place.category}</span>
          ${s.is_locked ? '<span class="badge warn">잠금</span>' : ""}
        </div>
        <div class="row">
          <button class="icon-btn secondary" type="button" data-action="up" ${idx === 0 ? "disabled" : ""}>▲</button>
          <button class="icon-btn secondary" type="button" data-action="down" ${idx === total - 1 ? "disabled" : ""}>▼</button>
        </div>
      </div>
      <div class="row muted" style="font-size:0.85rem;">
        <span>${s.start_time || "-"} 시작</span>
        ${moveInfo}
      </div>
      <div class="row">
        <label style="margin:0; width:auto;">체류(분)</label>
        <input type="number" class="stay-input" value="${s.stay_min}" min="10" step="10" style="width:80px;">
        <label style="margin:0; width:auto;">Day 이동</label>
        <select class="day-move-select" style="width:auto;"></select>
        <label style="display:flex; align-items:center; gap:4px; width:auto; margin:0;">
          <input type="checkbox" class="lock-checkbox" style="width:auto;" ${s.is_locked ? "checked" : ""}> 잠금
        </label>
        <a class="btn small secondary" href="/trips/${TRIP_ID}/planb?schedule_id=${s.schedule_id}">Plan B</a>
        <button class="danger small" type="button" data-action="delete">삭제</button>
      </div>
    </div>
  `;
}

function populateDaySelects() {
  const totalDays = tripTotalDays();
  document.querySelectorAll(".day-move-select").forEach((sel) => {
    const scheduleId = Number(sel.closest("[data-schedule-id]").dataset.scheduleId);
    const s = schedules.find((x) => x.schedule_id === scheduleId);
    if (!s) return;
    let html = '<option value="0">미배치</option>';
    for (let d = 1; d <= totalDays; d++) html += `<option value="${d}">Day ${d}</option>`;
    sel.innerHTML = html;
    sel.value = String(s.day_no);
  });
}

document.getElementById("day-tabs").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-day]");
  if (!a) return;
  e.preventDefault();
  activeDay = Number(a.dataset.day);
  renderDayTabs();
  renderDayContent();
  populateDaySelects();
});

async function addPlace(place) {
  await api.post(`/api/trips/${TRIP_ID}/places`, place);
  await loadSchedules();
  showToast(`${place.name}을(를) 추가했습니다.`);
}

let searchTimer = null;
document.getElementById("place_search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const query = e.target.value.trim();
  const resultsEl = document.getElementById("search-results");
  if (query.length < 2) {
    resultsEl.innerHTML = "";
    return;
  }
  searchTimer = setTimeout(async () => {
    resultsEl.innerHTML = '<div class="spinner"></div>';
    try {
      const region = tripInfo ? tripInfo.region : "";
      const data = await api.get(`/api/places/search?q=${encodeURIComponent(query)}&region=${encodeURIComponent(region)}`);
      if (data.places.length === 0) {
        resultsEl.innerHTML = '<p class="muted">검색 결과가 없습니다. 아래 "직접 입력"을 이용해주세요.</p>';
        return;
      }
      resultsEl.innerHTML = data.places
        .map(
          (p, idx) => `
        <div class="list-item" data-idx="${idx}">
          <div>
            <strong>${escapeHtml(p.name)}</strong> <span class="badge muted">${p.category}</span>
            <p class="muted" style="margin:2px 0 0; font-size:0.8rem;">${escapeHtml(p.address || "")}</p>
          </div>
          <button type="button" class="small" data-action="add-searched">추가</button>
        </div>
      `
        )
        .join("");
      resultsEl.dataset.places = JSON.stringify(data.places);
    } catch (err) {
      resultsEl.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
    }
  }, 400);
});

document.getElementById("search-results").addEventListener("click", async (e) => {
  const btn = e.target.closest('button[data-action="add-searched"]');
  if (!btn) return;
  const idx = Number(btn.closest("[data-idx]").dataset.idx);
  const places = JSON.parse(document.getElementById("search-results").dataset.places || "[]");
  try {
    await addPlace(places[idx]);
    document.getElementById("place_search").value = "";
    document.getElementById("search-results").innerHTML = "";
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("add-place-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await addPlace({
      name: document.getElementById("place_name").value,
      category: document.getElementById("place_category").value,
      lat: Number(document.getElementById("place_lat").value),
      lng: Number(document.getElementById("place_lng").value),
    });
    e.target.reset();
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("generate-route-btn").addEventListener("click", async () => {
  const btn = document.getElementById("generate-route-btn");
  const status = document.getElementById("route-status");
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> 계산 중...';
  try {
    const result = await api.post(`/api/trips/${TRIP_ID}/route`, {
      transport: document.getElementById("transport").value,
    });
    const badge = result.approximate ? " (근사치)" : "";
    status.textContent = `총 이동 ${result.total_move_min}분 / ${result.total_move_km}km${badge}`;
    activeDay = null;
    await loadSchedules();
  } catch (err) {
    status.textContent = "";
    showToast(err.message, true);
  } finally {
    btn.disabled = false;
  }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const container = btn.closest("[data-schedule-id]");
  if (!container) return;
  const scheduleId = Number(container.dataset.scheduleId);
  const action = btn.dataset.action;

  try {
    if (action === "delete") {
      if (!confirm("이 일정을 삭제할까요?")) return;
      await api.delete(`/api/schedules/${scheduleId}`);
      await loadSchedules();
    } else if (action === "up" || action === "down") {
      const s = schedules.find((x) => x.schedule_id === scheduleId);
      const dayItems = groupByDay()[s.day_no];
      const idx = dayItems.findIndex((x) => x.schedule_id === scheduleId);
      const targetIdx = action === "up" ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= dayItems.length) return;
      const newOrderNo = dayItems[targetIdx].order_no;
      await api.put(`/api/trips/${TRIP_ID}/schedules/order`, {
        schedule_id: scheduleId,
        day_no: s.day_no,
        order_no: newOrderNo,
      });
      await loadSchedules();
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

document.addEventListener("change", async (e) => {
  const container = e.target.closest("[data-schedule-id]");
  if (!container) return;
  const scheduleId = Number(container.dataset.scheduleId);

  try {
    if (e.target.classList.contains("day-move-select")) {
      await api.put(`/api/trips/${TRIP_ID}/schedules/order`, {
        schedule_id: scheduleId,
        day_no: Number(e.target.value),
        order_no: 999,
      });
      await loadSchedules();
    } else if (e.target.classList.contains("lock-checkbox")) {
      await api.put(`/api/schedules/${scheduleId}`, { is_locked: e.target.checked });
      showToast("저장했습니다.");
    }
  } catch (err) {
    showToast(err.message, true);
    await loadSchedules();
  }
});

document.addEventListener(
  "blur",
  async (e) => {
    if (!e.target.classList || !e.target.classList.contains("stay-input")) return;
    const container = e.target.closest("[data-schedule-id]");
    if (!container) return;
    const scheduleId = Number(container.dataset.scheduleId);
    try {
      await api.put(`/api/schedules/${scheduleId}`, { stay_min: Number(e.target.value) });
      await loadSchedules();
    } catch (err) {
      showToast(err.message, true);
    }
  },
  true
);

(async function init() {
  try {
    await loadTrip();
    await loadSchedules();
  } catch (err) {
    showToast(err.message, true);
  }
})();
