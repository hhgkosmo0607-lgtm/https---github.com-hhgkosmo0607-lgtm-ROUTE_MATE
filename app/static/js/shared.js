(async function init() {
  const el = document.getElementById("shared-content");
  try {
    const trip = await api.get(`/api/shared/${SHARE_TOKEN}`);
    const byDay = {};
    for (const s of trip.schedules) {
      if (s.day_no === 0) continue;
      (byDay[s.day_no] ||= []).push(s);
    }
    const days = Object.keys(byDay)
      .map(Number)
      .sort((a, b) => a - b);

    const dayCards = days
      .map((d) => {
        const items = byDay[d].sort((a, b) => a.order_no - b.order_no);
        const rows = items
          .map(
            (s, idx) => `
          <div class="list-item">
            <div>${idx + 1}. ${escapeHtml(s.place.name)} <span class="badge muted">${s.place.category}</span></div>
            <div class="muted">${s.start_time || "-"} · 체류 ${s.stay_min}분</div>
          </div>
        `
          )
          .join("");
        return `<div class="card"><h3>Day ${d}</h3><div class="stack">${rows}</div></div>`;
      })
      .join("");

    el.innerHTML = `
      <h1>${escapeHtml(trip.title)}</h1>
      <p class="muted">${escapeHtml(trip.region)} · ${trip.start_date} ~ ${trip.end_date} · 읽기 전용 공유 보기</p>
      <div class="stack" style="margin-top:16px;">${dayCards || '<div class="empty-state">아직 배치된 일정이 없습니다.</div>'}</div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
  }
})();
