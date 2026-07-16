function splitList(value) {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

document.addEventListener("DOMContentLoaded", async () => {
  if (new URLSearchParams(location.search).get("welcome")) {
    document.getElementById("welcome-banner").style.display = "block";
  }

  ["walk_level", "budget_level", "interest_cafe", "interest_photo", "interest_shopping", "interest_rest"].forEach(
    (id) => {
      const input = document.getElementById(id);
      const out = document.getElementById(id + "_val");
      input.addEventListener("input", () => (out.textContent = input.value));
    }
  );

  try {
    const me = await api.get("/api/users/me");
    document.getElementById("nickname").value = me.nickname;
    document.getElementById("email").value = me.email;
  } catch (err) {
    showToast(err.message, true);
  }

  try {
    const profile = await api.get("/api/users/me/profile");
    if (profile) {
      document.getElementById("travel_style").value = profile.travel_style || "BALANCED";
      document.getElementById("transport").value = profile.transport || "TRANSIT";
      document.getElementById("food_pref").value = (profile.food_pref || []).join(", ");
      document.getElementById("allergy").value = (profile.allergy || []).join(", ");
      document.getElementById("walk_level").value = profile.walk_level || 2;
      document.getElementById("walk_level_val").textContent = profile.walk_level || 2;
      document.getElementById("budget_level").value = profile.budget_level || 3;
      document.getElementById("budget_level_val").textContent = profile.budget_level || 3;
      const interests = profile.interests || {};
      ["cafe", "photo", "shopping", "rest"].forEach((key) => {
        const val = interests[key] ?? 0.5;
        document.getElementById("interest_" + key).value = val;
        document.getElementById("interest_" + key + "_val").textContent = val;
      });
    }
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("account-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { nickname: document.getElementById("nickname").value };
  const password = document.getElementById("password").value;
  if (password) body.password = password;
  try {
    await api.put("/api/users/me", body);
    document.getElementById("password").value = "";
    showToast("계정 정보를 저장했습니다.");
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    travel_style: document.getElementById("travel_style").value,
    transport: document.getElementById("transport").value,
    food_pref: splitList(document.getElementById("food_pref").value),
    allergy: splitList(document.getElementById("allergy").value),
    walk_level: Number(document.getElementById("walk_level").value),
    budget_level: Number(document.getElementById("budget_level").value),
    interests: {
      cafe: Number(document.getElementById("interest_cafe").value),
      photo: Number(document.getElementById("interest_photo").value),
      shopping: Number(document.getElementById("interest_shopping").value),
      rest: Number(document.getElementById("interest_rest").value),
    },
  };
  try {
    await api.put("/api/users/me/profile", body);
    showToast("프로필을 저장했습니다.");
  } catch (err) {
    showToast(err.message, true);
  }
});

document.getElementById("logout-btn-2").addEventListener("click", async () => {
  await api.post("/api/auth/logout");
  window.location.href = "/";
});

document.getElementById("delete-account-btn").addEventListener("click", async () => {
  if (!confirm("정말 탈퇴하시겠습니까? 이 작업은 되돌릴 수 없습니다.")) return;
  try {
    await api.delete("/api/users/me");
    window.location.href = "/";
  } catch (err) {
    showToast(err.message, true);
  }
});
