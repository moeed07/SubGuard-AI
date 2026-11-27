export async function request(path, { method = 'GET', body, csrf, signal } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (csrf && method !== 'GET') headers['X-CSRF-Token'] = csrf;
  const response = await fetch(path, {
    method, headers, credentials: 'same-origin', signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) {
    const error = new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    error.reconnectRequired = data?.reconnect_required === true;
    throw error;
  }
  return data;
}
