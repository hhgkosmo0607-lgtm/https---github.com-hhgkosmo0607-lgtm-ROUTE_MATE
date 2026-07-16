const api = {
  async request(method, url, body) {
    const headers = { "Content-Type": "application/json" };
    if (method !== "GET") {
      headers["X-CSRF-Token"] = document.querySelector('meta[name="csrf-token"]').content;
    }
    const resp = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data;
    try {
      data = await resp.json();
    } catch {
      data = { success: false, error: { code: "UNKNOWN", message: "서버 응답을 처리할 수 없습니다." } };
    }
    if (!resp.ok || !data.success) {
      const err = new Error((data.error && data.error.message) || "요청 처리 중 오류가 발생했습니다.");
      err.code = data.error && data.error.code;
      err.status = resp.status;
      throw err;
    }
    return data.data;
  },
  get(url) {
    return this.request("GET", url);
  },
  post(url, body) {
    return this.request("POST", url, body);
  },
  put(url, body) {
    return this.request("PUT", url, body);
  },
  delete(url) {
    return this.request("DELETE", url);
  },
};

function showToast(message, isError) {
  document.querySelectorAll(".toast").forEach((el) => el.remove());
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}
