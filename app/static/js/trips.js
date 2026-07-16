const STATUS_LABEL = { PLANNING: "예정", ONGOING: "진행 중", DONE: "완료" };

function tripCardHtml(trip) {
  return `
    <div class="card" data-trip-id="${trip.trip_id}">
      <div class="row between">
        <div>
          <h3>${escapeHtml(trip.title)} <span class="badge">${STATUS_LABEL[trip.status] || trip.status}</span></h3>
          <p class="muted">${escapeHtml(trip.region)} · ${trip.start_date} ~ ${trip.end_date}</p>
        </div>
        <div class="row">
          <a class="btn small" href="/trips/${trip.trip_id}/plan">계획 보기</a>
          <button class="secondary small" type="button" data-action="clone">복제</button>
          <button class="secondary small" type="button" data-action="share">공유</button>
          <button class="danger small" type="button" data-action="delete">삭제</button>
        </div>
      </div>
    </div>
  `;
}

async function loadTrips() {
  const container = document.getElementById("trips-list");
  try {
    const data = await api.get("/api/trips");
    if (data.trips.length === 0) {
      container.innerHTML = `<div class="empty-state">아직 여행이 없습니다. <a href="/trips/new">첫 여행을 만들어보세요.</a></div>`;
      return;
    }
    container.innerHTML = data.trips.map(tripCardHtml).join("");
  } catch (err) {
    container.innerHTML = `<div class="error-text">${escapeHtml(err.message)}</div>`;
  }
}

document.getElementById("trips-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const card = btn.closest("[data-trip-id]");
  const tripId = card.dataset.tripId;
  const action = btn.dataset.action;

  try {
    if (action === "delete") {
      if (!confirm("이 여행을 삭제할까요?")) return;
      await api.delete(`/api/trips/${tripId}`);
      showToast("삭제했습니다.");
      loadTrips();
    } else if (action === "clone") {
      await api.post(`/api/trips/${tripId}/clone`);
      showToast("여행을 복제했습니다.");
      loadTrips();
    } else if (action === "share") {
      const data = await api.post(`/api/trips/${tripId}/share/link`);
      const url = `${location.origin}/shared/${data.share_token}`;
      await navigator.clipboard?.writeText(url).catch(() => {});
      showToast(`공유 링크가 생성됐습니다: ${url}`);
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

loadTrips();
