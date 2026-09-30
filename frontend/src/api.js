const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* response wasn't JSON */
    }
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function request(path, options) {
  try {
    return await handle(await fetch(`${API}${path}`, options));
  } catch (e) {
    if (e instanceof TypeError) {
      throw new Error(`Can't reach the backend at ${API}. Is it running?`);
    }
    throw e;
  }
}

export function uploadFiles(files, logFiles, descriptions, datasetDescription) {
  const form = new FormData();
  for (const f of files) form.append("files", f); // same field names as the backend
  for (const f of logFiles || []) form.append("query_logs", f);
  form.append("descriptions", descriptions || "");
  form.append("dataset_description", datasetDescription || "");
  // No Content-Type header: the browser sets it, with the correct boundary.
  return request("/upload", { method: "POST", body: form });
}

export function connectDatabase(url, schema, tables, logFiles, descriptions, datasetDescription) {
  const form = new FormData();
  form.append("connection_url", url);
  form.append("db_schema", schema || "");
  form.append("include_tables", tables || "");
  for (const file of logFiles || []) form.append("query_logs", file);
  form.append("descriptions", descriptions || "");
  form.append("dataset_description", datasetDescription || "");
  return request("/connect", { method: "POST", body: form });
}

export function testConnection(url, schema) {
  const form = new FormData();
  form.append("connection_url", url);
  form.append("db_schema", schema || "");
  return request("/connect/test", { method: "POST", body: form });
}

export function askQuestion(sessionId, question) {
  return request("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
  });
}

export function getSuggestions(sessionId) {
  return request(`/suggestions/${sessionId}`);
}

export function getPreview(sessionId) {
  return request(`/preview/${sessionId}`);
}

export function deleteSession(sessionId) {
  return request(`/session/${sessionId}`, { method: "DELETE" });
}
