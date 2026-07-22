// 모노크롬 디자인: Day 구분은 회색 명도 + 선 패턴(실선/파선/점선) 조합으로
// Day별 식별 색 — trip_plan.js의 PLAN_DAY_COLORS와 동일 팔레트를 사용해 화면 간 색이 일치하도록 한다.
const DAY_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#ea580c", "#7c3aed", "#0891b2", "#ca8a04"];
const DAY_DASHES = [null, "8 6", "2 6"];

function dayDash(dayNo) {
  return DAY_DASHES[(dayNo - 1) % DAY_DASHES.length];
}

let allSchedules = [];
let map = null;
let dayLayers = {}; // day_no -> L.LayerGroup

function groupByDayMap(list) {
  const byDay = {};
  for (const s of list) {
    if (s.day_no === 0) continue;
    (byDay[s.day_no] ||= []).push(s);
  }
  for (const day in byDay) byDay[day].sort((a, b) => a.order_no - b.order_no);
  return byDay;
}

function dayColor(dayNo) {
  return DAY_COLORS[(dayNo - 1) % DAY_COLORS.length];
}

function buildMap(byDay) {
  const allPoints = Object.values(byDay)
    .flat()
    .map((s) => [s.place.lat, s.place.lng]);

  map = L.map("map");
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  if (allPoints.length === 0) {
    map.setView([37.5665, 126.978], 11); // 기본값: 서울
    return;
  }

  for (const [dayNo, items] of Object.entries(byDay)) {
    const color = dayColor(Number(dayNo));
    const layer = L.layerGroup();
    const latlngs = items.map((s) => [s.place.lat, s.place.lng]);

    L.polyline(latlngs, { color, weight: 3, opacity: 0.85, dashArray: dayDash(Number(dayNo)) }).addTo(layer);
    items.forEach((s, idx) => {
      L.circleMarker([s.place.lat, s.place.lng], {
        radius: 9,
        color,
        fillColor: color,
        fillOpacity: 0.9,
        weight: 2,
      })
        .bindTooltip(`${idx + 1}. ${s.place.name}`, { permanent: false })
        .bindPopup(
          `<strong>${escapeHtml(s.place.name)}</strong><br>${s.place.category}<br>${s.start_time || "-"} 시작`
        )
        .addTo(layer);
    });

    dayLayers[dayNo] = layer;
    layer.addTo(map);
  }

  map.fitBounds(allPoints, { padding: [30, 30] });
}

function applyDayFilter(filterValue) {
  for (const [dayNo, layer] of Object.entries(dayLayers)) {
    const visible = filterValue === "all" || filterValue === dayNo;
    if (visible && !map.hasLayer(layer)) layer.addTo(map);
    if (!visible && map.hasLayer(layer)) map.removeLayer(layer);
  }
}

function renderSummary(byDay, filterValue) {
  const days = Object.keys(byDay)
    .map(Number)
    .sort((a, b) => a - b);
  const summaryEl = document.getElementById("day-summary");
  if (days.length === 0) {
    summaryEl.innerHTML = '<div class="empty-state">아직 배치된 일정이 없습니다.</div>';
    return;
  }

  const visibleDays = filterValue === "all" ? days : [Number(filterValue)];
  summaryEl.innerHTML = visibleDays
    .map((d) => {
      const items = byDay[d] || [];
      const totalMove = items.reduce((sum, s) => sum + (s.move_min || 0), 0);
      const rows = items
        .map(
          (s, idx) => `
        <tr>
          <td>${idx + 1}</td>
          <td>${escapeHtml(s.place.name)}</td>
          <td>${s.start_time || "-"}</td>
          <td>${s.place.lat.toFixed(5)}, ${s.place.lng.toFixed(5)}</td>
        </tr>
      `
        )
        .join("");
      return `
        <div class="card">
          <h3><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${dayColor(d)};margin-right:6px;"></span>Day ${d} <span class="badge">총 이동 ${totalMove}분</span></h3>
          <table>
            <thead><tr><th>#</th><th>장소</th><th>시각</th><th>좌표</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    })
    .join("");
}

document.getElementById("day-filter").addEventListener("change", (e) => {
  const byDay = groupByDayMap(allSchedules);
  applyDayFilter(e.target.value);
  renderSummary(byDay, e.target.value);
});

(async function init() {
  try {
    const data = await api.get(`/api/trips/${TRIP_ID}/schedules`);
    allSchedules = data.schedules;
    const byDay = groupByDayMap(allSchedules);
    const days = Object.keys(byDay)
      .map(Number)
      .sort((a, b) => a - b);

    const filterEl = document.getElementById("day-filter");
    filterEl.innerHTML =
      '<option value="all">전체</option>' + days.map((d) => `<option value="${d}">Day ${d}</option>`).join("");

    buildMap(byDay);
    renderSummary(byDay, "all");
  } catch (err) {
    showToast(err.message, true);
  }
})();
