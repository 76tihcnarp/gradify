export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export const getToken = () => localStorage.getItem("gradify_token") || "";
export const getRole = () => localStorage.getItem("gradify_role") || "";
export const getClassId = () => Number(localStorage.getItem("gradify_class_id") || 0);

export function saveSession({ access_token, role, class_id, profile }) {
  localStorage.setItem("gradify_token", access_token);
  localStorage.setItem("gradify_role", role);
  if (class_id) localStorage.setItem("gradify_class_id", String(class_id));
  if (profile) localStorage.setItem("gradify_profile", JSON.stringify(profile));
}

export function clearSession() {
  ["gradify_token", "gradify_role", "gradify_class_id", "gradify_profile"].forEach((key) => localStorage.removeItem(key));
}

export async function api(path, options = {}) {
  const { token = getToken(), body, form, method = "GET", headers = {} } = options;
  const requestHeaders = { ...headers };
  if (token) requestHeaders.Authorization = `Bearer ${token}`;
  let requestBody;
  if (form) {
    requestBody = form;
  } else if (body !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
    requestBody = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers: requestHeaders, body: requestBody });
  } catch {
    throw new Error(`Cannot reach Gradify backend at ${API_BASE}. Check that FastAPI is running and CORS allows this frontend origin.`);
  }
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" ? data.detail || data.message : data;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || `Request failed (${response.status})`));
  }
  return data;
}

export async function getProtectedImage(path, token = getToken()) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error("Could not load this image.");
  return URL.createObjectURL(await response.blob());
}
