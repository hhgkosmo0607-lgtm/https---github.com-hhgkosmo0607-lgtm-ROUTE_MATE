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
  renderMapSchedules();
  loadGaps();
}

async function loadGaps() {
  // FR-303: 60분 이상 빈 시간대를 감지해 "AI로 채우기" 제안
  try {
    const data = await api.get(`/api/trips/${TRIP_ID}/gaps`);
    const el = document.getElementById("gap-banner");
    el.innerHTML = data.gaps
      .slice(0, 3)
      .map(
        (g) => `
      <div class="list-item" style="background:#f1f1ee;">
        <span class="muted">Day ${g.day_no} · ${g.from}부터 ${Math.floor(g.free_min / 60)}시간 ${g.free_min % 60}분 여유</span>
        <a class="btn small secondary" href="/trips/${TRIP_ID}/recommend?type=GAP_FILL&near=${g.near_schedule_id}">AI로 채우기</a>
      </div>`
      )
      .join("");
  } catch (err) {
    /* 배너는 부가 정보 — 실패해도 조용히 넘어간다 */
  }
}

// ───────── 작업용 지도 (UI-06 중앙 / FR-502 지도에서 장소 선택) ─────────
const PLAN_DAY_COLORS = ["#2b2b29", "#6f6f6a", "#45453f", "#8f8f89", "#55554f", "#a3a39d"];
const CATEGORY_LABEL_KO = { ATTRACTION: "관광지", RESTAURANT: "음식점", CAFE: "카페", SHOPPING: "쇼핑", ETC: "기타" };
const POI_MIN_ZOOM = 16;

let planMap = null;
let scheduleLayer = null;
let poiLayer = null;
let searchPreviewMarker = null;
let poiFetchTimer = null;

function initPlanMap() {
  planMap = L.map("plan-map").setView([37.5665, 126.978], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(planMap);
  scheduleLayer = L.layerGroup().addTo(planMap);
  poiLayer = L.layerGroup().addTo(planMap);

  planMap.on("moveend zoomend", () => {
    clearTimeout(poiFetchTimer);
    poiFetchTimer = setTimeout(refreshPois, 500);
  });
}

function renderMapSchedules() {
  if (!planMap) return;
  scheduleLayer.clearLayers();
  const byDay = groupByDay();
  const allPoints = [];

  for (const [dayNo, items] of Object.entries(byDay)) {
    const color = PLAN_DAY_COLORS[(Number(dayNo) - 1) % PLAN_DAY_COLORS.length];
    const latlngs = items.map((s) => [s.place.lat, s.place.lng]);
    allPoints.push(...latlngs);
    L.polyline(latlngs, { color, weight: 3, opacity: 0.7 }).addTo(scheduleLayer);
    items.forEach((s, idx) => {
      L.circleMarker([s.place.lat, s.place.lng], {
        radius: 10, color, fillColor: color, fillOpacity: 0.95, weight: 1,
      })
        .bindTooltip(`Day ${dayNo} · ${idx + 1}. ${s.place.name}`)
        .addTo(scheduleLayer);
    });
  }
  // 미배치 장소는 흐린 마커로
  for (const s of schedules.filter((x) => x.day_no === 0)) {
    allPoints.push([s.place.lat, s.place.lng]);
    L.circleMarker([s.place.lat, s.place.lng], {
      radius: 8, color: "#8f8f89", fillColor: "#c9c9c4", fillOpacity: 0.9, weight: 1.5,
    })
      .bindTooltip(`미배치 · ${s.place.name}`)
      .addTo(scheduleLayer);
  }

  if (allPoints.length > 0 && !planMap._fittedOnce) {
    planMap.fitBounds(allPoints, { padding: [40, 40], maxZoom: 15 });
    planMap._fittedOnce = true;
  }
}

async function refreshPois() {
  if (!planMap) return;
  const hint = document.getElementById("poi-hint");
  if (planMap.getZoom() < POI_MIN_ZOOM) {
    poiLayer.clearLayers();
    hint.hidden = false;
    return;
  }
  const b = planMap.getBounds();
  try {
    const data = await api.get(
      `/api/places/nearby?south=${b.getSouth()}&west=${b.getWest()}&north=${b.getNorth()}&east=${b.getEast()}`
    );
    if (data.need_zoom) {
      hint.hidden = false;
      return;
    }
    hint.hidden = true;
    poiLayer.clearLayers();
    poiCache = {};
    const scheduledKeys = new Set(schedules.map((s) => `${s.place.lat.toFixed(5)},${s.place.lng.toFixed(5)}`));
    data.places.forEach((poi, idx) => {
      if (scheduledKeys.has(`${poi.lat.toFixed(5)},${poi.lng.toFixed(5)}`)) return;
      poiCache[idx] = poi;
      const marker = L.circleMarker([poi.lat, poi.lng], {
        radius: 5, color: "#55554f", fillColor: "#fdfdfc", fillOpacity: 0.9, weight: 1.5,
      }).bindTooltip(poi.name);
      // 외부 데이터(상호명)는 속성에 넣지 않고 poiCache 인덱스로만 참조한다
      marker.bindPopup(
        `<div class="poi-popup"><div class="poi-popup-name">${escapeHtml(poi.name)}</div>` +
        `<div class="muted">${CATEGORY_LABEL_KO[poi.category] || poi.category}</div>` +
        `<button type="button" class="small poi-add-btn" style="margin-top:6px;" data-poi-id="${idx}">일정에 추가</button></div>`
      );
      marker.addTo(poiLayer);
    });
  } catch (err) {
    // 레이트 리밋 등은 힌트만 유지하고 조용히 넘어간다
  }
}

let poiCache = {};

document.getElementById("plan-map").addEventListener("click", async (e) => {
  const poiBtn = e.target.closest(".poi-add-btn");
  const searchBtn = e.target.closest(".search-add-btn");
  if (!poiBtn && !searchBtn) return;

  const btn = poiBtn || searchBtn;
  const poi = poiBtn ? poiCache[btn.dataset.poiId] : exploreItems[Number(btn.dataset.idx)];
  if (!poi) return;
  btn.disabled = true;
  try {
    await addPlace({ name: poi.name, category: poi.category, lat: poi.lat, lng: poi.lng });
    planMap.closePopup();
    if (poiBtn) refreshPois();
  } catch (err) {
    showToast(err.message, true);
    btn.disabled = false;
  }
});

function showSearchPreview(place) {
  if (!planMap) return;
  if (searchPreviewMarker) searchPreviewMarker.remove();
  searchPreviewMarker = L.circleMarker([place.lat, place.lng], {
    radius: 11, color: "#2b2b29", fillColor: "#2b2b29", fillOpacity: 0.35, weight: 2, dashArray: "3 3",
  })
    .bindTooltip(place.name, { permanent: true, direction: "top" })
    .addTo(planMap);
  planMap.setView([place.lat, place.lng], Math.max(planMap.getZoom(), 16));
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
          <div class="row" style="flex-wrap:nowrap;">
            <button type="button" class="small secondary" data-action="explore">주변</button>
            <button type="button" class="small" data-action="add-searched">추가</button>
          </div>
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
  const row = e.target.closest("[data-idx]");
  if (!row) return;
  const idx = Number(row.dataset.idx);
  const places = JSON.parse(document.getElementById("search-results").dataset.places || "[]");

  if (e.target.closest('button[data-action="explore"]')) {
    exploreArea(places[idx]);  // 동네/장소 주변 음식점·가볼만한 곳 탐색
    return;
  }
  const btn = e.target.closest('button[data-action="add-searched"]');
  if (!btn) {
    showSearchPreview(places[idx]);  // 행 클릭 → 지도에서 위치 미리보기 (FR-502)
    return;
  }
  try {
    await addPlace(places[idx]);
    if (searchPreviewMarker) searchPreviewMarker.remove();
    document.getElementById("place_search").value = "";
    document.getElementById("search-results").innerHTML = "";
  } catch (err) {
    showToast(err.message, true);
  }
});

// ───────── 주변 탐색: 동네 검색 → 음식점/카페/가볼만한 곳 목록 ─────────
const EXPLORE_LABELS = { ATTRACTION: "가볼만한 곳", RESTAURANT: "음식점", CAFE: "카페", SHOPPING: "쇼핑", ETC: "기타" };
const EXPLORE_ORDER = ["ATTRACTION", "RESTAURANT", "CAFE", "SHOPPING", "ETC"];
let exploreItems = [];
let exploreFilter = "ALL";

async function exploreArea(place) {
  showSearchPreview(place);  // 지도 이동 + 미리보기 핀 (줌 16 → 지도에도 POI 점 표시됨)

  const card = document.getElementById("explore-card");
  const resultsEl = document.getElementById("explore-results");
  card.hidden = false;
  document.getElementById("explore-title").textContent = `${place.name} 주변`;
  resultsEl.innerHTML = '<div class="spinner"></div>';

  const fetchNearby = async (dLat, dLng) => {
    const data = await api.get(
      `/api/places/nearby?south=${place.lat - dLat}&west=${place.lng - dLng}&north=${place.lat + dLat}&east=${place.lng + dLng}`
    );
    return data.places;
  };

  try {
    let expanded = false;
    let places = await fetchNearby(0.006, 0.0075); // 약 650m 반경
    if (places.length < 5) {
      places = await fetchNearby(0.012, 0.0145); // 데이터가 적으면 약 1.3km로 확장
      expanded = true;
    }
    exploreItems = places;
    exploreFilter = "ALL";
    renderExplore();
    if (expanded && places.length > 0) {
      resultsEl.insertAdjacentHTML(
        "afterbegin",
        '<p class="muted">가까운 곳에 등록 장소가 적어 반경 약 1.3km까지 넓혀 찾았습니다.</p>'
      );
    }
  } catch (err) {
    resultsEl.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
  }
}

function renderExplore() {
  const resultsEl = document.getElementById("explore-results");
  const filtersEl = document.getElementById("explore-filters");

  const counts = {};
  for (const p of exploreItems) counts[p.category] = (counts[p.category] || 0) + 1;

  filtersEl.innerHTML =
    `<button type="button" class="small ${exploreFilter === "ALL" ? "" : "secondary"}" data-filter="ALL">전체 ${exploreItems.length}</button>` +
    EXPLORE_ORDER.filter((c) => counts[c])
      .map(
        (c) =>
          `<button type="button" class="small ${exploreFilter === c ? "" : "secondary"}" data-filter="${c}">${EXPLORE_LABELS[c]} ${counts[c]}</button>`
      )
      .join("");

  const visible = exploreItems.filter((p) => exploreFilter === "ALL" || p.category === exploreFilter);
  if (visible.length === 0) {
    resultsEl.innerHTML =
      '<p class="muted">이 동네의 OpenStreetMap 등록 장소가 없습니다. 관광지·번화가에서 데이터가 풍부합니다 — 지도를 옮기거나 검색으로 추가해보세요.</p>';
    return;
  }
  resultsEl.innerHTML = visible
    .slice(0, 40)
    .map(
      (p, idx) => `
    <div class="list-item" data-explore-idx="${exploreItems.indexOf(p)}">
      <div>
        <strong>${escapeHtml(p.name)}</strong>
        <span class="badge muted">${EXPLORE_LABELS[p.category] || p.category}</span>
      </div>
      <button type="button" class="small" data-action="add-explored">추가</button>
    </div>
  `
    )
    .join("");
}

document.getElementById("explore-filters").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-filter]");
  if (!btn) return;
  exploreFilter = btn.dataset.filter;
  renderExplore();
});

document.getElementById("explore-results").addEventListener("click", async (e) => {
  const row = e.target.closest("[data-explore-idx]");
  if (!row) return;
  const poi = exploreItems[Number(row.dataset.exploreIdx)];
  if (!poi) return;

  if (e.target.closest('button[data-action="add-explored"]')) {
    try {
      await addPlace(poi);
      row.remove();
    } catch (err) {
      showToast(err.message, true);
    }
    return;
  }
  // 행 클릭 → 지도에서 해당 장소로 이동
  if (planMap) planMap.setView([poi.lat, poi.lng], 18);
});

document.getElementById("explore-close").addEventListener("click", () => {
  document.getElementById("explore-card").hidden = true;
  if (mapSearchLayer) mapSearchLayer.clearLayers();
});

// ───────── 지도 화면 내 키워드 검색 (네이버식 "이 지역에서 검색") ─────────
let mapSearchLayer = null;

async function mapKeywordSearch() {
  const q = document.getElementById("map-search-input").value.trim();
  if (!q || !planMap) return;

  const card = document.getElementById("explore-card");
  const resultsEl = document.getElementById("explore-results");
  card.hidden = false;
  document.getElementById("explore-title").textContent = `'${q}' — 현재 지도 화면`;
  resultsEl.innerHTML = '<div class="spinner"></div>';
  if (mapSearchLayer) mapSearchLayer.clearLayers(); // 이전 검색 마커가 새 결과처럼 보이지 않도록

  const b = planMap.getBounds();
  try {
    const data = await api.get(
      `/api/places/nearby?south=${b.getSouth()}&west=${b.getWest()}&north=${b.getNorth()}&east=${b.getEast()}&q=${encodeURIComponent(q)}`
    );
    if (data.need_zoom) {
      resultsEl.innerHTML = '<p class="muted">검색 범위가 너무 넓습니다 — 지도를 조금 확대한 뒤 다시 검색해주세요.</p>';
      return;
    }
    exploreItems = data.places;
    exploreFilter = "ALL";
    renderExplore();
    renderSearchMarkers(data.places);
    document.getElementById("map-search-clear").hidden = false;
  } catch (err) {
    resultsEl.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
  }
}

function renderSearchMarkers(places) {
  if (!mapSearchLayer) mapSearchLayer = L.layerGroup().addTo(planMap);
  mapSearchLayer.clearLayers();
  if (places.length === 0) return;

  places.forEach((poi, idx) => {
    L.circleMarker([poi.lat, poi.lng], {
      radius: 7, color: "#f6f6f4", fillColor: "#2b2b29", fillOpacity: 0.95, weight: 1.5,
    })
      .bindTooltip(poi.name)
      .bindPopup(
        `<div class="poi-popup"><div class="poi-popup-name">${escapeHtml(poi.name)}</div>` +
        `<div class="muted">${EXPLORE_LABELS[poi.category] || poi.category}</div>` +
        `<button type="button" class="small search-add-btn" style="margin-top:6px;" data-idx="${idx}">일정에 추가</button></div>`
      )
      .addTo(mapSearchLayer);
  });
  planMap.fitBounds(places.map((p) => [p.lat, p.lng]), { padding: [40, 40], maxZoom: 17 });
}

document.getElementById("map-search-btn").addEventListener("click", mapKeywordSearch);
document.getElementById("map-search-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") mapKeywordSearch();
});
document.getElementById("map-search-clear").addEventListener("click", () => {
  document.getElementById("map-search-input").value = "";
  document.getElementById("map-search-clear").hidden = true;
  if (mapSearchLayer) mapSearchLayer.clearLayers();
  document.getElementById("explore-card").hidden = true;
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
    initPlanMap();
    await loadTrip();
    await loadSchedules();
  } catch (err) {
    showToast(err.message, true);
  }
})();
