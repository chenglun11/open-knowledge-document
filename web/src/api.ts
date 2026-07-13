const TOKEN_KEY = 'okd-admin-token'

export function savedToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) || ''
}

export function saveToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': savedToken(),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(payload.detail || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
