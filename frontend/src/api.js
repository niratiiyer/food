const TOKEN_KEY = 'leftover-token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function saveToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage can be blocked in private mode
  }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, token, form } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(form)
  } else if (body) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.detail || `Request failed (${res.status})`)
  return data
}

export const api = {
  login: (email, password) => request('/token', { method: 'POST', form: { username: email, password } }),
  me: (token) => request('/me', { token }),
  listings: () => request('/listings'),
  myClaims: (token) => request('/me/claims', { token }),
  claim: (token, listingId) => request(`/listings/${listingId}/claim`, { method: 'POST', token }),
  dailyStats: (days = 30) => request(`/stats/daily?days=${days}`),
}
