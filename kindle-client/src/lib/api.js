const BASE = '/api/v1';

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (res.status === 401) {
    throw new ApiError('unauthenticated', 401);
  }
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch (e) { /* ignore */ }
    throw new ApiError(body?.error || res.statusText, res.status);
  }
  if (res.status === 204) return null;
  return res.json();
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const api = {
  me: () => request('/me'),
  feeds: () => request('/feeds'),
  folders: () => request('/folders'),
  entries: (params = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    }
    const suffix = qs.toString() ? `?${qs}` : '';
    return request('/entries' + suffix);
  },
  pinned: (params = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    }
    const suffix = qs.toString() ? `?${qs}` : '';
    return request('/entries/pinned' + suffix);
  },
  entry: (id) => request(`/entries/${id}`),
  entryContent: (id) => request(`/entries/${id}/content`),
  entryContentPrefetch: (id) => request(`/entries/${id}/content?prefetch=1`),
  pin: (id) => request(`/entries/${id}/pin`, { method: 'PUT' }),
  unpin: (id) => request(`/entries/${id}/pin`, { method: 'DELETE' }),
  favorite: (id) => request(`/entries/${id}/favorite`, { method: 'PUT' }),
  unfavorite: (id) => request(`/entries/${id}/favorite`, { method: 'DELETE' }),
  markViewed: (id) => request(`/entries/${id}/viewed`, { method: 'POST' }),
  sendToKindle: (id) => request(`/entries/${id}/kindle`, { method: 'POST' }),
};
