const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function parseResponse(response) {
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const errorBody = await response.json();
      if (errorBody.detail) {
        message = typeof errorBody.detail === "string" ? errorBody.detail : JSON.stringify(errorBody.detail);
      }
    } catch {
      /* response wasn't JSON */
    }
    const requestError = new Error(message);
    requestError.status = response.status;
    throw requestError;
  }
  return response.json();
}

async function request(path, options) {
  try {
    return await parseResponse(await fetch(`${API}${path}`, options));
  } catch (requestError) {
    // fetch rejects with a TypeError only when the server is unreachable.
    if (requestError instanceof TypeError) {
      throw new Error(`Can't reach the backend at ${API}. Is it running?`);
    }
    throw requestError;
  }
}

export function uploadFiles(files, logFiles, descriptions, datasetDescription, progressId) {
  const form = new FormData();
  for (const tableFile of files) form.append("files", tableFile);
  for (const logFile of logFiles || []) form.append("query_logs", logFile);
  form.append("descriptions", descriptions || "");
  form.append("dataset_description", datasetDescription || "");
  form.append("progress_id", progressId || "");
  // No Content-Type header: the browser sets it, with the correct boundary.
  return request("/upload", { method: "POST", body: form });
}

export function connectDatabase(url, schema, tables, logFiles, descriptions, datasetDescription, progressId) {
  const form = new FormData();
  form.append("connection_url", url);
  form.append("db_schema", schema || "");
  form.append("include_tables", tables || "");
  for (const logFile of logFiles || []) form.append("query_logs", logFile);
  form.append("descriptions", descriptions || "");
  form.append("dataset_description", datasetDescription || "");
  form.append("progress_id", progressId || "");
  return request("/connect", { method: "POST", body: form });
}

export function getBuildProgress(progressId) {
  return request(`/progress/${progressId}`);
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
